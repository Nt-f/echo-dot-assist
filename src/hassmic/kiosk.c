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
 *   app <package>            the screen app (docs/screen-apps.md): hassmic's Java kiosk by default, or one of the
 *                            owner's (the Flutter template, hassmic-screen), started by its SCREEN intent
 *
 * The app reads it as JSON from 127.0.0.1 (web.c), and only that app: the connection's owner (its uid in
 * /proc/net/tcp6 or tcp) is the screen app's (the owner of its data folder), as anyone may install apps of their own on
 * the Echo now, and the token is a Home Assistant login. */
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "kiosk.h"
#include "core.h"
#include "statefile.h"
#include <arpa/inet.h>
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
#define APP_DEFAULT "org.hassmic.kiosk"
#define APP_MAX 150
static char app[APP_MAX + 1] = APP_DEFAULT;
static long long front_at, seen_at, started_at;

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

/* parses text into the given places; 0 ok */
/* a package name as Android takes it: letters, digits, _ and dots */
static int is_pkg(const char *s)
{
    size_t n = strlen(s);
    if (!n || n > APP_MAX || s[0] == '.' || strstr(s, "..")) return 0;
    for (; *s; s++) if (!((*s >= 'a' && *s <= 'z') || (*s >= 'A' && *s <= 'Z') || (*s >= '0' && *s <= '9') || *s == '_' || *s == '.')) return 0;
    return 1;
}

static int parse(const char *text, struct screen *sc, int *ns, int *d, int *r, char *h, char *t, char *ap, char *err, size_t cap)
{
    *ns = 0; *d = 0; *r = 120; h[0] = t[0] = 0; snprintf(ap, APP_MAX + 1, "%s", APP_DEFAULT);
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
            if (!is_url(tab)) { snprintf(err, cap, "screen %s: not an http(s) address", v); return -1; }
            snprintf(sc[*ns].name, sizeof sc[*ns].name, "%s", v); snprintf(sc[*ns].url, sizeof sc[*ns].url, "%s", tab); (*ns)++;
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
    struct screen sc[KIOSK_SCREENS]; int ns, d, r; char h[URL_MAX + 1], t[TOKEN_MAX + 1], ap[APP_MAX + 1];
    if (parse(text, sc, &ns, &d, &r, h, t, ap, err, sizeof err)) { fprintf(stderr, "kiosk: state/kiosk refused (%s)\n", err); return; }
    pthread_mutex_lock(&lock);
    memcpy(screens, sc, sizeof sc); nscreens = ns; def = d; ret_s = r; snprintf(ha, sizeof ha, "%s", h); snprintf(token, sizeof token, "%s", t);
    snprintf(app, sizeof app, "%s", ap);
    pthread_mutex_unlock(&lock);
    fprintf(stderr, "kiosk: %d screen%s%s\n", ns, ns == 1 ? "" : "s", t[0] ? ", with a login" : "");
}

int kiosk_store(const char *text, char *err, size_t cap)
{
    struct screen sc[KIOSK_SCREENS]; int ns, d, r; char h[URL_MAX + 1], t[TOKEN_MAX + 1], p[300], ap[APP_MAX + 1];
    if (parse(text, sc, &ns, &d, &r, h, t, ap, err, cap)) return -1;
    /* written back as parsed: only what was taken */
    size_t cap_ = 16384, n = 0; char *o = malloc(cap_);
    if (!o) { snprintf(err, cap, "out of memory"); return -1; }
    if (h[0]) n += (size_t)snprintf(o + n, cap_ - n, "ha %s\n", h);
    if (t[0]) n += (size_t)snprintf(o + n, cap_ - n, "token %s\n", t);
    for (int i = 0; i < ns; i++) n += (size_t)snprintf(o + n, cap_ - n, "screen %s\t%s\n", sc[i].name, sc[i].url);
    n += (size_t)snprintf(o + n, cap_ - n, "default %d\nreturn %d\napp %s\n", d, r, ap);
    path(p, sizeof p);
    int bad = statefile_write(p, 0600, o, n);
    free(o);
    if (bad) { snprintf(err, cap, "cannot write state/kiosk"); return -1; }
    pthread_mutex_lock(&lock);
    int other = strcmp(app, ap) != 0;
    memcpy(screens, sc, sizeof sc); nscreens = ns; def = d; ret_s = r; snprintf(ha, sizeof ha, "%s", h); snprintf(token, sizeof token, "%s", t);
    snprintf(app, sizeof app, "%s", ap);
    if (other) { front_at = seen_at = started_at = 0; }        /* another app: started at once, the old one's polls refused */
    pthread_mutex_unlock(&lock);
    fprintf(stderr, "kiosk: %d screen%s from Home Assistant%s, screen app %s\n", ns, ns == 1 ? "" : "s", t[0] ? ", with a login" : "", ap);
    return 0;
}

char *kiosk_json(int with_token, int enabled, size_t *len)
{
    size_t cap = 8192 + TOKEN_MAX, n = 0; char *o = malloc(cap);
    if (!o) return NULL;
    pthread_mutex_lock(&lock);
    /* every string passed clean(): nothing in it to escape */
    n += (size_t)snprintf(o + n, cap - n, "{\"enabled\":%s,\"ha\":\"%s\",\"has_token\":%s,", enabled ? "true" : "false", ha, token[0] ? "true" : "false");
    if (with_token) n += (size_t)snprintf(o + n, cap - n, "\"token\":\"%s\",", token);
    n += (size_t)snprintf(o + n, cap - n, "\"app\":\"%s\",\"default\":%d,\"return\":%d,\"screens\":[", app, def, ret_s);
    for (int i = 0; i < nscreens; i++) n += (size_t)snprintf(o + n, cap - n, "%s{\"name\":\"%s\",\"url\":\"%s\"}", i ? "," : "", screens[i].name, screens[i].url);
    n += (size_t)snprintf(o + n, cap - n, "]}");
    pthread_mutex_unlock(&lock);
    if (len) *len = n;
    return o;
}

void kiosk_polled(int front)
{
    pthread_mutex_lock(&lock);
    seen_at = mono_ms();
    if (front) front_at = seen_at;
    else front_at = 0;                  /* paused: the screen went off (or something else is in front) */
    pthread_mutex_unlock(&lock);
}

int kiosk_front(void)
{
    pthread_mutex_lock(&lock);
    int r = front_at && mono_ms() - front_at < FRONT_MS;
    pthread_mutex_unlock(&lock);
    return r;
}

int kiosk_configured(void) { pthread_mutex_lock(&lock); int r = nscreens > 0; pthread_mutex_unlock(&lock); return r; }

int kiosk_tick(int enabled)
{
    if (!enabled || !kiosk_configured()) return 0;
    if (kiosk_front()) return 1;
    long long now = mono_ms();
    pthread_mutex_lock(&lock);
    /* started only when gone (not since the boot, or it crashed): a paused app (the screen dark) still polls, and an
     * am start a minute all night long would be an app_process launch a minute on the Show's CPU */
    int go = (!seen_at || now - seen_at >= ALIVE_MS) && (!started_at || now - started_at >= START_MS);
    if (go) started_at = now;
    pthread_mutex_unlock(&lock);
    if (go) {
        /* not running (not started since the boot, or it crashed): by the contract's intent, which the screen app's
         * activity declares (docs/screen-apps.md); the package alone names it */
        char pkg[APP_MAX + 1];
        pthread_mutex_lock(&lock); snprintf(pkg, sizeof pkg, "%s", app); pthread_mutex_unlock(&lock);
        char *argv[] = { "/system/bin/am", "start", "-a", "org.hassmic.action.SCREEN", "-c", "android.intent.category.DEFAULT", pkg, NULL };
        fprintf(stderr, "kiosk: starting the screen app %s\n", pkg);
        core_spawn(argv);
    }
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
