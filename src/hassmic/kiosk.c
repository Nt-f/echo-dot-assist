/* The kiosk's config and whether its app is in front (kiosk.h).
 *
 * state/kiosk, written by POST /api/kiosk (web.c, signed, the token sealed with the browser's K as a Wi-Fi password
 * is): lines of
 *
 *   ha <url>                 Home Assistant's address as the integration sees it (get_url: the one the LAN reaches)
 *   token <token>            a long-lived access token of the kiosk's own user, made by the integration
 *   screen <name>\t<url>     up to KIOSK_SCREENS, in the order the app's switcher shows them
 *   default <i>              the screen it starts on and goes back to
 *   return <s>               after this long untouched on another screen, back to the default (0: never)
 *   set <key> <value>        a setting of the screen app's own (its Immich address and key, ...), for it alone:
 *                            only in the app's config on loopback, never in the signed API's answer
 *   app <package>            the screen app (docs/screen-apps.md): hassmic's Java kiosk by default, or one of the
 *                            owner's (the Flutter template, Echo-Screen), started by its SCREEN intent
 *
 * The app reads it as JSON from 127.0.0.1 (web.c), and only that app: the connection's owner (its uid in
 * /proc/net/tcp6 or tcp) is the screen app's (the owner of its data folder), as anyone may install apps of their own on
 * the Echo now, and the token is a Home Assistant login. */
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "kiosk.h"
#include "board.h"
#include "core.h"
#include "statefile.h"
#include <arpa/inet.h>
#include <dirent.h>
#include <unistd.h>
#include <netinet/in.h>
#include <pthread.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define KIOSK_SCREENS 8
#define URL_MAX       400
#define NAME_MAX_     40
#define TOKEN_MAX     600
#define FRONT_MS      20000             /* the app polls every 5 s while resumed */
#define ALIVE_MS      90000             /* and every 30 s while paused (the screen off): alive, not to be started */
#define START_MS      60000             /* am start at most this often: ART's start of it takes a second of CPU */

static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
struct screen { char name[NAME_MAX_ + 1], url[URL_MAX + 1]; };
static struct screen screens[KIOSK_SCREENS];
static int nscreens, def, ret_s = 120;
static char ha[URL_MAX + 1], token[TOKEN_MAX + 1];
#define APP_DEFAULT "io.github.gamer92000.echodotassist.kiosk"
#define APP_MAX 150
static char app[APP_MAX + 1] = APP_DEFAULT;
#define SETS 16
#define SET_KEY 40
#define SET_VAL 400
struct set { char key[SET_KEY + 1], val[SET_VAL + 1]; };
static struct set sets[SETS];
static int nsets;
static long long front_at, seen_at, started_at;
static int draws;                       /* the app in front draws the request's words and a ring itself */
/* the screen app started another app (a video client, docs/screen-apps.md "Other apps") and polls /lent/<package>
 * meanwhile: the screen is that app's, so hassmic's layer stays off as while the screen app is in front.  Kept until the
 * screen app polls /front or /back, or is started again (gone for ALIVE_MS): a screen app killed for memory while a
 * video plays must not let hassmic's clock come up over the video */
static char lent[APP_MAX + 1];
/* the screen app's way in: by the contract's SCREEN intent (an app made for hassmic) or, where that started nothing, as
 * Android's launcher would (any app: a browser, Home Assistant's own app); `answered`: it polled since it was picked */
static int answered, via_launcher, launcher_works;
static long long shell_started;
#define SHELL_PKG APP_DEFAULT              /* the shell is hassmic's own kiosk app's service, whichever app is the screen app */
#define HOME_PKG  "org.hassmic.home"       /* hassmic's codeless black home (tools/mkhome.py): in front = no app */
#define GONE_MS   5000                     /* nothing in front this long (an app closed, crashed): the screen app again */
#define LAUNCH_MS 15000                    /* and started again at most this often */
#define SHELL_GONE_MS 40000                /* the shell polls every 15 s: two missed, its bar is gone (no touch held for it) */

static long long mono_ms(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return t.tv_sec * 1000LL + t.tv_nsec / 1000000; }
static void path(char *out, size_t cap)
{
    const char *e = getenv("HASSMIC_STATE");
    snprintf(out, cap, "%s/kiosk", e ? e : "/data/local/hassmic/state");
}

/* printable, no quotes or backslashes to escape for anyone: what a URL, a name and a token are made of */
static int clean(const char *s, size_t max, int tabs)
{
    size_t n = strlen(s);
    if (n > max) return 0;
    for (const unsigned char *c = (const unsigned char *)s; *c; c++)
        if (*c < 0x20 || *c == 0x7f || *c == '"' || *c == '\\' || (!tabs && *c == '\t')) return 0;
    return 1;
}
static int is_url(const char *u) { return (!strncmp(u, "http://", 7) || !strncmp(u, "https://", 8)) && !strchr(u, ' ') && clean(u, URL_MAX, 0); }
/* a screen the app draws itself: "hassmic:clock" (docs/screen-apps.md), lower-case letters and dashes after the colon */
static int is_own(const char *u)
{
    if (strncmp(u, "hassmic:", 8) || !u[8] || strlen(u) > 40) return 0;
    for (const char *c = u + 8; *c; c++) if (!((*c >= 'a' && *c <= 'z') || *c == '-')) return 0;
    return 1;
}

/* ---------------------------------------------------------------- what is in front

 * Android gives the process of the activity in front oom_score_adj 0 (FOREGROUND_APP_ADJ); every other app's is higher
 * (measured on the Show 5, Fire OS 7: Echo-Wall 0 in front, 700 behind NewPipe, its overlay service 200; NewPipe 0 in
 * front).  So hassmic sees which app has the screen without the app's help and without running anything: a scan of
 * /proc (about 120 processes on the Show), as system, at most once a second.  Apps' uids from 10000; isolated
 * processes (the WebView's sandboxes, 99000 on) and an app's other processes ("pkg:service") are not the app.  Fire OS
 * keeps no usage statistics (dumpsys usagestats lists no app's events), so Android's own API for this is no help. */
static int is_pkg(const char *s);

static const char *proc_root(void)
{
    const char *e = getenv("HASSMIC_PROC");                 /* tests: a folder standing for /proc */
    if (e) return e;
    return access("/system/bin/am", X_OK) ? NULL : "/proc";  /* not on Android (the PC): not known */
}

static int read_small(const char *p, char *out, size_t cap)
{
    FILE *f = fopen(p, "r"); if (!f) return -1;
    size_t n = fread(out, 1, cap - 1, f); fclose(f); out[n] = 0; return (int)n;
}

/* the app in front (1, its package in out), none of the owner's (0), not known (-1); `shell`: whether the shell runs */
static int scan_front(char *out, size_t cap, int *shell)
{
    const char *root = proc_root();
    out[0] = 0; if (shell) *shell = 0;
    if (!root) return -1;
    int fake = getenv("HASSMIC_PROC") != NULL;              /* tests: their files are the test's uid's */
    DIR *d = opendir(root); if (!d) return -1;
    struct dirent *e; char p[300], b[200];
    int found = 0, apps = 0, adjs = 0;
    while ((e = readdir(d))) {
        if (e->d_name[0] < '0' || e->d_name[0] > '9') continue;
        struct stat st;
        snprintf(p, sizeof p, "%s/%s", root, e->d_name);
        if (stat(p, &st) || (!fake && (st.st_uid < 10000 || st.st_uid >= 90000))) continue;
        snprintf(p, sizeof p, "%s/%s/cmdline", root, e->d_name);
        if (read_small(p, b, sizeof b) <= 0) continue;
        apps++;
        if (shell && !strcmp(b, SHELL_PKG ":shell")) *shell = 1;
        if (found || strchr(b, ':') || !is_pkg(b)) continue;
        snprintf(p, sizeof p, "%s/%s/oom_score_adj", root, e->d_name);
        char a[16];
        if (read_small(p, a, sizeof a) <= 0) continue;
        adjs++;
        if (a[0] != '0' || atoi(a) != 0) continue;
        if (!strcmp(b, HOME_PKG)) continue;                 /* hassmic's black home: nothing of the owner's */
        snprintf(out, cap, "%.150s", b); found = 1;
    }
    closedir(d);
    /* no app's process seen at all: not that none runs (the Echo always has some: the WebView's, Amazon's providers)
     * but that /proc hides them from us (Android 7 mounts it hidepid=2: only group readproc sees others' processes,
     * device.conf DAEMON_GROUPS).  Not known, then: the screen app's polls decide, as before */
    if (!apps) return -1;
    /* the apps seen, their oom_score_adj not (Fire OS 7: 0400, the app's own; Android 9: 0644): not known by /proc */
    if (!adjs) return -1;
    return found;
}

/* what the shell's watcher (tools/kiosk Watcher.java: an accessibility service, told of every activity that comes
 * forward) last reported, and when: where /proc cannot say (Fire OS 7: an app's oom_score_adj is its own, 0400), its
 * word counts for a minute (it says it again every 20 s) */
#define REPORT_MS 60000
static long long reported_at; static char reported[APP_MAX + 1];
int kiosk_shell_front(const char *pkg)
{
    if (!is_pkg(pkg)) return -1;
    pthread_mutex_lock(&lock);
    if (strcmp(reported, pkg)) fprintf(stderr, "kiosk: in front: %s\n", pkg);
    snprintf(reported, sizeof reported, "%s", pkg); reported_at = mono_ms();
    pthread_mutex_unlock(&lock);
    return 0;
}

static long long scanned_at; static int scanned = -1, shell_runs; static char scanned_pkg[APP_MAX + 1];
int kiosk_in_front(char *out, size_t cap)
{
    long long now = mono_ms();
    pthread_mutex_lock(&lock);
    if (reported_at && now - reported_at < REPORT_MS) {
        int r = strcmp(reported, HOME_PKG) != 0;           /* hassmic's black home in front: no app */
        if (out && cap) snprintf(out, cap, "%s", r ? reported : "");
        if (!scanned_at || now - scanned_at >= 1000) {      /* /proc still for the shell's own process */
            pthread_mutex_unlock(&lock);
            char pk[APP_MAX + 1]; int sh = 0; scan_front(pk, sizeof pk, &sh);
            pthread_mutex_lock(&lock); shell_runs = sh; scanned_at = now;
        }
        pthread_mutex_unlock(&lock);
        return r;
    }
    if (!scanned_at || now - scanned_at >= 1000) {
        int sh = 0; char pk[APP_MAX + 1];
        pthread_mutex_unlock(&lock);
        int r = scan_front(pk, sizeof pk, &sh);
        pthread_mutex_lock(&lock);
        scanned = r; shell_runs = sh; scanned_at = now; snprintf(scanned_pkg, sizeof scanned_pkg, "%s", pk);
    }
    int r = scanned;
    if (out && cap) snprintf(out, cap, "%s", scanned_pkg);
    pthread_mutex_unlock(&lock);
    return r;
}

int kiosk_draws_parse(const char *t)
{
    if (strncmp(t, "/draws", 6)) return 0;
    if (!t[6]) return KIOSK_DRAWS_WORDS | KIOSK_DRAWS_RING;   /* /front/draws: both, the contract of before */
    if (t[6] != '/') return 0;
    int m = 0; const char *w = t + 7;
    while (*w) {
        size_t n = strcspn(w, ",+");
        if (n == 5 && !strncmp(w, "words", 5)) m |= KIOSK_DRAWS_WORDS;
        else if (n == 4 && !strncmp(w, "ring", 4)) m |= KIOSK_DRAWS_RING;
        w += n; if (*w) w++;                                /* a word not known here (a later contract's): left out */
    }
    return m;
}

/* parses text into the given places; 0 ok */
/* a package name as Android takes it: letters, digits, _ and dots */
static int is_pkg(const char *s)
{
    size_t n = strlen(s);
    if (!n || n > APP_MAX || s[0] == '.' || strstr(s, "..")) return 0;
    for (; *s; s++) if (!((*s >= 'a' && *s <= 'z') || (*s >= 'A' && *s <= 'Z') || (*s >= '0' && *s <= '9') || *s == '_' || *s == '.')) return 0;
    return 1;
}

static int is_key(const char *s)
{
    size_t n = strlen(s);
    if (!n || n > SET_KEY) return 0;
    for (; *s; s++) if (!((*s >= 'a' && *s <= 'z') || (*s >= '0' && *s <= '9') || *s == '_' || *s == '.' || *s == '-')) return 0;
    return 1;
}

static int parse(const char *text, struct screen *sc, int *ns, int *d, int *r, char *h, char *t, char *ap, struct set *st, int *nst,
                 char *err, size_t cap)
{
    *ns = 0; *d = 0; *r = 120; h[0] = t[0] = 0; snprintf(ap, APP_MAX + 1, "%s", APP_DEFAULT); *nst = 0;
    const char *p = text;
    while (p && *p) {
        const char *e = strchr(p, '\n'); size_t n = e ? (size_t)(e - p) : strlen(p);
        char line[1100];
        if (n >= sizeof line) { snprintf(err, cap, "a line too long"); return -1; }
        memcpy(line, p, n); line[n] = 0; if (n && line[n - 1] == '\r') line[n - 1] = 0;
        p = e ? e + 1 : NULL;
        char *v = strchr(line, ' ');
        if (!line[0]) continue;
        if (!v) { snprintf(err, cap, "not \"key value\": %.40s", line); return -1; }
        *v++ = 0;
        if (!strcmp(line, "ha")) { if (!is_url(v)) { snprintf(err, cap, "ha: not an http(s) address"); return -1; } snprintf(h, URL_MAX + 1, "%s", v); }
        else if (!strcmp(line, "token")) { if (!clean(v, TOKEN_MAX, 0) || strchr(v, ' ')) { snprintf(err, cap, "token: not a token"); return -1; } snprintf(t, TOKEN_MAX + 1, "%s", v); }
        else if (!strcmp(line, "screen")) {
            char *tab = strchr(v, '\t');
            if (!tab) { snprintf(err, cap, "screen: \"name<tab>url\""); return -1; }
            *tab++ = 0;
            if (*ns >= KIOSK_SCREENS) { snprintf(err, cap, "more than %d screens", KIOSK_SCREENS); return -1; }
            if (!v[0] || !clean(v, NAME_MAX_, 0)) { snprintf(err, cap, "screen: a name of 1 to %d characters", NAME_MAX_); return -1; }
            if (!is_url(tab) && !is_own(tab)) { snprintf(err, cap, "screen %s: not an http(s) address", v); return -1; }
            snprintf(sc[*ns].name, sizeof sc[*ns].name, "%s", v); snprintf(sc[*ns].url, sizeof sc[*ns].url, "%s", tab); (*ns)++;
        }
        else if (!strcmp(line, "set")) {
            char *sp = strchr(v, ' ');
            if (!sp) { snprintf(err, cap, "set: \"key value\""); return -1; }
            *sp++ = 0;
            if (!is_key(v)) { snprintf(err, cap, "set: a key of a-z 0-9 . _ -, 40 at most"); return -1; }
            if (!clean(sp, SET_VAL, 0)) { snprintf(err, cap, "set %s: a value of printable characters, %d at most", v, SET_VAL); return -1; }
            if (*nst >= SETS) { snprintf(err, cap, "more than %d settings", SETS); return -1; }
            snprintf(st[*nst].key, sizeof st[*nst].key, "%s", v); snprintf(st[*nst].val, sizeof st[*nst].val, "%s", sp); (*nst)++;
        }
        else if (!strcmp(line, "app")) { if (!is_pkg(v)) { snprintf(err, cap, "app: not a package name"); return -1; } snprintf(ap, APP_MAX + 1, "%s", v); }
        else if (!strcmp(line, "default")) *d = atoi(v);
        else if (!strcmp(line, "return")) { *r = atoi(v); if (*r < 0 || *r > 86400) { snprintf(err, cap, "return: 0 to 86400 s"); return -1; } }
        /* other keys: a newer integration's; left out */
    }
    if (*d < 0 || *d >= (*ns ? *ns : 1)) *d = 0;
    return 0;
}

void kiosk_load(void)
{
    char p[300], err[100]; FILE *f; static char text[16384];
    path(p, sizeof p);
    if (!(f = fopen(p, "r"))) return;
    size_t n = fread(text, 1, sizeof text - 1, f); fclose(f); text[n] = 0;
    struct screen sc[KIOSK_SCREENS]; int ns, d, r, nst; char h[URL_MAX + 1], t[TOKEN_MAX + 1], ap[APP_MAX + 1]; static struct set st[SETS];
    if (parse(text, sc, &ns, &d, &r, h, t, ap, st, &nst, err, sizeof err)) { fprintf(stderr, "kiosk: state/kiosk refused (%s)\n", err); return; }
    pthread_mutex_lock(&lock);
    memcpy(sets, st, sizeof sets); nsets = nst;
    memcpy(screens, sc, sizeof sc); nscreens = ns; def = d; ret_s = r; snprintf(ha, sizeof ha, "%s", h); snprintf(token, sizeof token, "%s", t);
    snprintf(app, sizeof app, "%s", ap);
    pthread_mutex_unlock(&lock);
    fprintf(stderr, "kiosk: %d screen%s%s\n", ns, ns == 1 ? "" : "s", t[0] ? ", with a login" : "");
}

int kiosk_store(const char *text, char *err, size_t cap)
{
    struct screen sc[KIOSK_SCREENS]; int ns, d, r, nst; char h[URL_MAX + 1], t[TOKEN_MAX + 1], p[300], ap[APP_MAX + 1];
    static struct set st[SETS];
    if (parse(text, sc, &ns, &d, &r, h, t, ap, st, &nst, err, cap)) return -1;
    /* written back as parsed: only what was taken */
    size_t cap_ = 16384, n = 0; char *o = malloc(cap_);
    if (!o) { snprintf(err, cap, "out of memory"); return -1; }
    if (h[0]) n += (size_t)snprintf(o + n, cap_ - n, "ha %s\n", h);
    if (t[0]) n += (size_t)snprintf(o + n, cap_ - n, "token %s\n", t);
    for (int i = 0; i < ns; i++) n += (size_t)snprintf(o + n, cap_ - n, "screen %s\t%s\n", sc[i].name, sc[i].url);
    n += (size_t)snprintf(o + n, cap_ - n, "default %d\nreturn %d\napp %s\n", d, r, ap);
    for (int i = 0; i < nst; i++) n += (size_t)snprintf(o + n, cap_ - n, "set %s %s\n", st[i].key, st[i].val);
    path(p, sizeof p);
    int bad = statefile_write(p, 0600, o, n);
    free(o);
    if (bad) { snprintf(err, cap, "cannot write state/kiosk"); return -1; }
    pthread_mutex_lock(&lock);
    int other = strcmp(app, ap) != 0;
    char old[APP_MAX + 1]; snprintf(old, sizeof old, "%s", app);
    memcpy(sets, st, sizeof sets); nsets = nst;
    memcpy(screens, sc, sizeof sc); nscreens = ns; def = d; ret_s = r; snprintf(ha, sizeof ha, "%s", h); snprintf(token, sizeof token, "%s", t);
    snprintf(app, sizeof app, "%s", ap);
    if (other) { front_at = seen_at = started_at = 0; lent[0] = 0; answered = via_launcher = launcher_works = 0; }   /* another app: started at once, the old one's polls refused */
    pthread_mutex_unlock(&lock);
    fprintf(stderr, "kiosk: %d screen%s from Home Assistant%s, screen app %s\n", ns, ns == 1 ? "" : "s", t[0] ? ", with a login" : "", ap);
    if (other) {
        /* the one before stopped: Android would keep it in memory (a Flutter app with a WebView: 200 MB) until it needs
         * the room, and it would go on polling */
        char *argv[] = { "/system/bin/am", "force-stop", old, NULL };
        core_spawn(argv);
    }
    return 0;
}

char *kiosk_json(int with_token, int enabled, size_t *len)
{
    size_t cap = 8192 + TOKEN_MAX + SETS * (SET_KEY + SET_VAL + 8), n = 0; char *o = malloc(cap);
    if (!o) return NULL;
    pthread_mutex_lock(&lock);
    /* every string passed clean(): nothing in it to escape */
    n += (size_t)snprintf(o + n, cap - n, "{\"enabled\":%s,\"ha\":\"%s\",\"has_token\":%s,", enabled ? "true" : "false", ha, token[0] ? "true" : "false");
    if (with_token) {
        n += (size_t)snprintf(o + n, cap - n, "\"token\":\"%s\",\"settings\":{", token);
        for (int i = 0; i < nsets; i++) n += (size_t)snprintf(o + n, cap - n, "%s\"%s\":\"%s\"", i ? "," : "", sets[i].key, sets[i].val);
        n += (size_t)snprintf(o + n, cap - n, "},");
    }
    n += (size_t)snprintf(o + n, cap - n, "\"app\":\"%s\",\"default\":%d,\"return\":%d,\"screens\":[", app, def, ret_s);
    for (int i = 0; i < nscreens; i++) n += (size_t)snprintf(o + n, cap - n, "%s{\"name\":\"%s\",\"url\":\"%s\"}", i ? "," : "", screens[i].name, screens[i].url);
    n += (size_t)snprintf(o + n, cap - n, "]}");
    pthread_mutex_unlock(&lock);
    if (len) *len = n;
    return o;
}

void kiosk_polled(int front, int draws_)
{
    pthread_mutex_lock(&lock);
    if (front) draws = draws_;
    seen_at = mono_ms(); answered = 1; via_launcher = 0;
    if (front) front_at = seen_at;
    else front_at = 0;                  /* paused: the screen went off (or something else is in front) */
    if (lent[0]) fprintf(stderr, "kiosk: the screen back from %s\n", lent);
    lent[0] = 0;
    pthread_mutex_unlock(&lock);
}

int kiosk_lent(const char *pkg)
{
    if (!is_pkg(pkg)) return -1;
    pthread_mutex_lock(&lock);
    seen_at = mono_ms(); front_at = 0;
    draws = 0;                          /* the other app draws no ring and no words: hassmic does, over it */
    if (strcmp(lent, pkg)) fprintf(stderr, "kiosk: the screen lent to %s\n", pkg);
    snprintf(lent, sizeof lent, "%s", pkg);
    pthread_mutex_unlock(&lock);
    return 0;
}

int kiosk_front(void)
{
    int f = kiosk_in_front(NULL, 0);
    if (f >= 0) return f;                                   /* Android says which app has the screen */
    pthread_mutex_lock(&lock);
    long long now = mono_ms();
    int r = (front_at && now - front_at < FRONT_MS) || (lent[0] && now - seen_at < ALIVE_MS);
    pthread_mutex_unlock(&lock);
    return r;
}

int kiosk_configured(void) { pthread_mutex_lock(&lock); int r = nscreens > 0; pthread_mutex_unlock(&lock); return r; }

/* the shell (tools/kiosk Shell.java: the bar of apps pulled down over any app, the keyboard): hassmic's own kiosk app's
 * service, running whichever app is the screen app; started when its process is not there, at most once a minute */
static long long shell_seen_at;          /* the bar's service polled /kiosk/shell (every 15 s while it runs) */
static void shell_tick(long long now)
{
    pthread_mutex_lock(&lock);
    /* by its polls, not by its process: the watcher (an accessibility service, started by Android) lives in the same
     * ":shell" process, which runs without the bar's service after an update of the app */
    int go = proc_root() && (!shell_seen_at || now - shell_seen_at >= START_MS) && (!shell_started || now - shell_started >= START_MS);
    if (go) shell_started = now;
    pthread_mutex_unlock(&lock);
    if (!go) return;
    char *argv[] = { "/system/bin/am", "startservice", "-n", SHELL_PKG "/.Shell", NULL };
    fprintf(stderr, "kiosk: starting the shell (the bar of apps)\n");
    core_spawn(argv);
}

/* the screen app started: by the contract's intent, which an app made for hassmic declares (docs/screen-apps.md); one
 * that never answered to it (any other app: a browser, Home Assistant's own app) as Android's launcher starts it */
static void start_app(void)
{
    char pkg[APP_MAX + 1];
    pthread_mutex_lock(&lock);
    snprintf(pkg, sizeof pkg, "%s", app);
    int launcher = answered ? 0 : launcher_works ? 1 : via_launcher;
    if (!answered && !launcher_works) via_launcher = !via_launcher;   /* nothing came of this way: the other one next time */
    pthread_mutex_unlock(&lock);
    fprintf(stderr, "kiosk: starting the screen app %s%s\n", pkg, launcher ? " (as the launcher does)" : "");
    if (launcher) {
        char *argv[] = { "/system/bin/monkey", "-p", pkg, "-c", "android.intent.category.LAUNCHER", "1", NULL };
        core_spawn(argv);
    } else {
        char *argv[] = { "/system/bin/am", "start", "-a", "io.github.gamer92000.echodotassist.action.SCREEN", "-c", "android.intent.category.DEFAULT", pkg, NULL };
        core_spawn(argv);
    }
}

static long long nothing_since;
int kiosk_tick(int enabled)
{
    if (!enabled || !kiosk_configured()) return 0;
    long long now = mono_ms();
    char fg[APP_MAX + 1];
    int f = kiosk_in_front(fg, sizeof fg);
    shell_tick(now);                                        /* on Android: the bar's service, whatever is known */
    if (f >= 0) {
        /* Android says what is in front: any app of the owner's has the screen; none (an app closed or crashed, hassmic's
         * home) for GONE_MS: the screen app again */
        pthread_mutex_lock(&lock);
        if (f && !strcmp(fg, app) && !answered && !via_launcher) launcher_works = 1;   /* the launcher's way brought it (toggled after) */
        if (f) nothing_since = 0; else if (!nothing_since) nothing_since = now;
        int go = !f && now - nothing_since >= GONE_MS && (!started_at || now - started_at >= LAUNCH_MS);
        if (go) { started_at = now; lent[0] = 0; }
        pthread_mutex_unlock(&lock);
        if (go) start_app();
        return f;
    }
    if (kiosk_front()) return 1;
    pthread_mutex_lock(&lock);
    /* the PC (no /proc of Android's): by the app's polls.  Started only when gone (not since the boot, or it crashed): a
     * paused app (the screen dark) still polls, and an am start a minute all night long would be an app_process launch
     * a minute on the Show's CPU */
    int go = (!seen_at || now - seen_at >= ALIVE_MS) && (!started_at || now - started_at >= START_MS);
    if (go) { started_at = now; lent[0] = 0; }      /* gone: it comes back in front, over the app it lent the screen to */
    pthread_mutex_unlock(&lock);
    if (go) start_app();
    return 0;
}

/* the uid of the process at the other end of a loopback TCP connection: the kernel's table of sockets has the
 * client's own entry (local = its address and port, remote = ours) with its owner */
static long peer_uid(int fd)
{
    struct sockaddr_storage a, b; socklen_t na = sizeof a, nb = sizeof b;
    if (getpeername(fd, (struct sockaddr *)&a, &na) || getsockname(fd, (struct sockaddr *)&b, &nb)) return -1;
    unsigned pp = ntohs(a.ss_family == AF_INET6 ? ((struct sockaddr_in6 *)&a)->sin6_port : ((struct sockaddr_in *)&a)->sin_port);
    unsigned lp = ntohs(b.ss_family == AF_INET6 ? ((struct sockaddr_in6 *)&b)->sin6_port : ((struct sockaddr_in *)&b)->sin_port);
    static const char *const tabs[] = { "/proc/net/tcp6", "/proc/net/tcp" };
    for (int i = 0; i < 2; i++) {
        FILE *f = fopen(tabs[i], "r"); char line[512];
        if (!f) continue;
        if (!fgets(line, sizeof line, f)) { fclose(f); continue; }          /* the header */
        while (fgets(line, sizeof line, f)) {
            char loc[64], rem[64]; unsigned st; long uid;
            /* sl local rem st tx:rx tr:when retrnsmt uid */
            if (sscanf(line, "%*s %63s %63s %x %*s %*s %*s %ld", loc, rem, &st, &uid) != 4) continue;
            char *lc = strrchr(loc, ':'), *rc = strrchr(rem, ':');
            if (!lc || !rc) continue;
            if (strtoul(lc + 1, NULL, 16) == pp && strtoul(rc + 1, NULL, 16) == lp) { fclose(f); return uid; }
        }
        fclose(f);
    }
    return -1;
}

int kiosk_peer_ok(int fd)
{
    char p[300], pkg[APP_MAX + 1]; struct stat st;
    const char *root = getenv("HASSMIC_APP_DATA");          /* tests: a folder standing for /data/data */
    pthread_mutex_lock(&lock); snprintf(pkg, sizeof pkg, "%s", app); pthread_mutex_unlock(&lock);
    snprintf(p, sizeof p, "%s/%s", root ? root : "/data/data", pkg);
    if (stat(p, &st)) return 0;                             /* not installed */
    long uid = peer_uid(fd);
    if (uid < 0 || (long)st.st_uid != uid) {
        static long last = -2;
        if (uid != last) { fprintf(stderr, "kiosk: config refused to uid %ld (the screen app %s is %ld)\n", uid, pkg, (long)st.st_uid); last = uid; }
        return 0;
    }
    return 1;
}

int kiosk_draws(void)
{
    /* only the screen app says what it draws: another app in front (one it started, or the owner's) draws neither */
    char fg[APP_MAX + 1];
    int f = kiosk_in_front(fg, sizeof fg);
    pthread_mutex_lock(&lock);
    int r = f > 0 && strcmp(fg, app) ? 0 : draws;
    pthread_mutex_unlock(&lock);
    return r;
}

/* swipes in from an edge (display_screen.c touch_thread), for the shell's long poll: the latest one and a version */
static pthread_cond_t pulled = PTHREAD_COND_INITIALIZER;
static unsigned pull_v; static char pull_edge[4]; static float pull_at;
void kiosk_shell_pull(const char *edge, float at)
{
    pthread_mutex_lock(&lock);
    snprintf(pull_edge, sizeof pull_edge, "%.2s", edge); pull_at = at; pull_v++;
    pthread_cond_broadcast(&pulled);
    pthread_mutex_unlock(&lock);
}

/* the shell's word of the screen's orientation (GET /kiosk/shell/orientation/land|port, at its start, on every turn and
 * with each poll) and whether its bar is on: the touch gate holds a touch at the top edge only while both are known */
static int shell_land = -1, shell_on;
int kiosk_shell_orientation(const char *o)
{
    int land = !strcmp(o, "land") ? 1 : !strcmp(o, "port") ? 0 : -1;
    if (land < 0) return -1;
    pthread_mutex_lock(&lock); shell_land = land; shell_seen_at = mono_ms(); pthread_mutex_unlock(&lock);
    return 0;
}

const char *kiosk_shell_top(void)
{
    static char edge[2][3];
    const char *t = board.touch_top;
    if (!t || strlen(t) != 5 || t[2] != ' ') return NULL;
    pthread_mutex_lock(&lock);
    int land = shell_land, ok = shell_on && shell_seen_at && mono_ms() - shell_seen_at < SHELL_GONE_MS;
    pthread_mutex_unlock(&lock);
    if (!ok || land < 0) return NULL;
    memcpy(edge[0], t, 2); memcpy(edge[1], t + 3, 2);
    return edge[land ? 0 : 1];
}

size_t kiosk_shell_wait(unsigned v, int ms, char *out, size_t cap)
{
    struct timespec ts; clock_gettime(CLOCK_REALTIME, &ts);
    ts.tv_sec += ms / 1000; ts.tv_nsec += (long)(ms % 1000) * 1000000L;
    if (ts.tv_nsec >= 1000000000L) { ts.tv_sec++; ts.tv_nsec -= 1000000000L; }
    pthread_mutex_lock(&lock);
    while (pull_v == v) if (pthread_cond_timedwait(&pulled, &lock, &ts)) break;
    size_t n = (size_t)snprintf(out, cap, "{\"v\":%u,\"edge\":\"%s\",\"at\":%.3f,\"top\":\"%s\"}", pull_v, pull_edge, pull_at,
                                board.touch_top ? board.touch_top : "");
    pthread_mutex_unlock(&lock);
    return n;
}

int kiosk_shell_peer_ok(int fd)
{
    char p[300]; struct stat st;
    const char *root = getenv("HASSMIC_APP_DATA");
    snprintf(p, sizeof p, "%s/%s", root ? root : "/data/data", SHELL_PKG);
    if (stat(p, &st)) return 0;
    long uid = peer_uid(fd);
    return uid >= 0 && (long)st.st_uid == uid;
}

/* the shell's config: no token (it logs in nowhere), the screen app (the bar's Home) and the screens' names (the
 * screen app opens one by its SCREEN intent's extra "screen") */
char *kiosk_shell_json(int enabled, size_t *len)
{
    pthread_mutex_lock(&lock); shell_seen_at = mono_ms(); shell_on = enabled; pthread_mutex_unlock(&lock);
    size_t cap = 4096, n = 0; char *o = malloc(cap);
    if (!o) return NULL;
    char fg[APP_MAX + 1]; int f = kiosk_in_front(fg, sizeof fg);
    pthread_mutex_lock(&lock);
    n += (size_t)snprintf(o + n, cap - n, "{\"enabled\":%s,\"app\":\"%s\",\"front\":\"%s\",\"contract\":%s,\"pulls\":%s,\"top\":\"%s\",\"screens\":[",
                          enabled ? "true" : "false", app, f > 0 ? fg : "", answered && !via_launcher ? "true" : "false",
                          board.touch && board.touch_top ? "true" : "false", board.touch_top ? board.touch_top : "");
    for (int i = 0; i < nscreens; i++)
        if (strncmp(screens[i].url, "hassmic:", 8))         /* the app's own Home and clock: the bar's Home */
            n += (size_t)snprintf(o + n, cap - n, "%s\"%s\"", n && o[n - 1] != '[' ? "," : "", screens[i].name);
    n += (size_t)snprintf(o + n, cap - n, "]}");
    pthread_mutex_unlock(&lock);
    if (len) *len = n;
    return o;
}
