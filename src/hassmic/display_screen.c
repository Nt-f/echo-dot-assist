/*
 * The screen above the light band (display.h), the Echo Show's: since the install takes Amazon's apps off the system
 * partition the screen was black but for the band.  Now it shows
 *
 *   idle       the clock (Amazon Ember Display, as stock's home screen), the date, the next alarm
 *   a request  what speech to text heard and what the assistant answered, display_text_seconds after it ends, the
 *              clock small above them; the Echo's own answers (alarms) too
 *   a ring     an alarm or timer ringing, big, with what stops it: a tap snoozes an alarm, a long press stops it
 *
 * How it gets there: ring_band_screen (ring_band.c) starts a second ringbar.dex in its "screen" mode, a SurfaceFlinger
 * layer over everything above the band, and this thread draws whole frames into it (width x height ARGB) only when the
 * picture changes: once a minute for the clock.  Text is drawn here with stb_truetype from the firmware's own fonts
 * (/system/fonts: Amazon Ember, Roboto where a model lacks it); nothing of Android's text stack is needed.
 *
 * The screen's power: off and awake leave stock's timeouts (ring_band.c's: 5 min, 1 min muted or in Do not disturb);
 * always and always_dim keep it on (screen_off_timeout INT_MAX), always_dim with the backlight at its night level and
 * the clock in a dim red between display_night_start and _end, or while the room is dark (the light sensor, under
 * 3 lux).  The backlight is Android's screen_brightness, set through the settings tool as the band's timeout is.
 *
 * Touch: the panel's evdev device (board.touch, read beside Android's input, never grabbed): a tap while an alarm
 * rings snoozes it (a timer: stops it), a press of 1.5 s stops it (core_touch).
 */
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "display.h"
#include "alarms.h"
#include "board.h"
#include "core.h"
#include "kiosk.h"
#include "ring.h"
#include "statefile.h"
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <ifaddrs.h>
#include <net/if.h>
#include <netinet/in.h>
#include <signal.h>
#include <limits.h>
#include <linux/input.h>
#include <math.h>
#include <poll.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <time.h>
#include <unistd.h>
#define STB_TRUETYPE_IMPLEMENTATION
#include "../third_party/stb_truetype.h"

const char *const display_modes[DISPLAY_MODES] = { "off", "awake", "always", "always_dim" };

#define NIGHT_LUX   3.0f                /* the room is dark: a lamp across the room still reads 10 and more */
#define TAP_MS      800                 /* a press shorter than this is a tap */
#define HOLD_MS     1500                /* one this long stops a ring */

static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t cv = PTHREAD_COND_INITIALIZER;
static int ds[DS_COUNT] = { [DS_MODE] = DISPLAY_AWAKE, [DS_TEXT] = 1, [DS_TEXT_S] = 20, [DS_BRIGHT] = 80, [DS_NIGHT_BRIGHT] = 10,
                            [DS_NIGHT_START] = 22, [DS_NIGHT_END] = 7, [DS_DARK_ROOM] = 1, [DS_KIOSK] = 0 };
static const int ds_min[DS_COUNT] = { 0, 0, 3, 1, 0, 0, 0, 0, 0 }, ds_max[DS_COUNT] = { DISPLAY_MODES - 1, 1, 120, 100, 100, 23, 23, 1, 1 };
static char heard[600], reply[1200], ringing[160];          /* lock held */
static int running, dirty, started;                         /* lock held */
static int linked, ever_linked;                             /* lock held: Home Assistant's link now, ever since the start */
static long long words_until;                               /* lock held: mono ms the words go (0: while running) */

static long long mono_ms(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return t.tv_sec * 1000LL + t.tv_nsec / 1000000; }
static unsigned ver = 1;                                    /* lock held: bumps with every change a screen app may draw */
static void poke(void) { dirty = 1; ver++; pthread_cond_broadcast(&cv); }  /* lock held; broadcast: display_wait waits too */

int display_present(void) { return 1; }

int display_setting(enum display_setting which, int set)
{
    if (which < 0 || which >= DS_COUNT) return 0;
    pthread_mutex_lock(&lock);
    if (set != INT_MIN && set >= ds_min[which] && set <= ds_max[which]) { ds[which] = set; poke(); }
    int v = ds[which];
    pthread_mutex_unlock(&lock);
    return v;
}

static void set_text(char *dst, size_t cap, const char *t)
{
    pthread_mutex_lock(&lock);
    snprintf(dst, cap, "%s", t ? t : "");
    if (!running) words_until = mono_ms() + ds[DS_TEXT_S] * 1000LL;   /* an answer given outside a run (alarms) */
    poke();
    pthread_mutex_unlock(&lock);
}
void display_heard(const char *text) { set_text(heard, sizeof heard, text); }
void display_reply(const char *text) { set_text(reply, sizeof reply, text); }

void display_run(int active)
{
    pthread_mutex_lock(&lock);
    if (active && !running) { heard[0] = reply[0] = 0; }            /* a new request: last one's words go */
    running = active;
    words_until = active ? 0 : mono_ms() + ds[DS_TEXT_S] * 1000LL;
    poke();
    pthread_mutex_unlock(&lock);
}

void display_ringing(const char *what)
{
    pthread_mutex_lock(&lock);
    snprintf(ringing, sizeof ringing, "%s", what ? what : "");
    poke();
    pthread_mutex_unlock(&lock);
}

void display_changed(void) { pthread_mutex_lock(&lock); poke(); pthread_mutex_unlock(&lock); }

void display_link(int up)
{
    pthread_mutex_lock(&lock);
    if (up != linked) { linked = up; if (up) ever_linked = 1; poke(); }
    pthread_mutex_unlock(&lock);
}

/* ---------------------------------------------------------------- for a screen app that draws these itself */

static size_t jesc_(char *o, size_t cap, const char *s)
{
    size_t n = 0;
    for (; *s && n + 7 < cap; s++) {
        unsigned char c = (unsigned char)*s;
        if (c == '"' || c == '\\') { o[n++] = '\\'; o[n++] = (char)c; }
        else if (c < 0x20) n += (size_t)snprintf(o + n, cap - n, "\\u%04x", c);
        else o[n++] = (char)c;
    }
    o[n] = 0;
    return n;
}

size_t display_state_json(char *out, size_t cap)
{
    static char h[1300], r[2500], g[340];
    pthread_mutex_lock(&lock);
    unsigned v = ver; int run = running;
    int words = ds[DS_TEXT] && (running || words_until || heard[0] || reply[0]);
    jesc_(h, sizeof h, heard); jesc_(r, sizeof r, reply); jesc_(g, sizeof g, ringing);
    int mode = ds[DS_MODE];
    pthread_mutex_unlock(&lock);
    int h24 = alarms_h24();
    char next[700] = "null";
    struct alarm a; time_t nx = alarms_next(&a);
    if (nx) {
        char f[96], t[200], te[400];
        if (nx == a.snoozed) { struct tm tm; localtime_r(&nx, &tm); alarms_time_text(tm.tm_hour, tm.tm_min, h24, f, sizeof f); snprintf(t, sizeof t, "Snoozed until %s", f); }
        else { alarms_format(&a, alarms_now(), h24, f, sizeof f); snprintf(t, sizeof t, "Alarm %s", f); }
        jesc_(te, sizeof te, t); char le[120]; jesc_(le, sizeof le, a.label);
        snprintf(next, sizeof next, "{\"at\":%lld,\"text\":\"%s\",\"label\":\"%s\"}", (long long)nx, te, le);
    }
    return (size_t)snprintf(out, cap, "{\"v\":%u,\"running\":%s,\"words\":%s,\"heard\":\"%s\",\"reply\":\"%s\",\"ringing\":\"%s\","
                            "\"ringing_alarm\":%s,\"h24\":%s,\"clock_set\":%s,\"next_alarm\":%s,\"display\":\"%s\"}",
                            v, run ? "true" : "false", words ? "true" : "false", h, r, g, strstr(ringing, "Alarm") ? "true" : "false",
                            h24 ? "true" : "false", alarms_clock_ok() ? "true" : "false", next, display_modes[mode]);
}

unsigned display_wait(unsigned since, int ms)
{
    struct timespec ts; clock_gettime(CLOCK_REALTIME, &ts);
    ts.tv_sec += ms / 1000; ts.tv_nsec += (long)(ms % 1000) * 1000000L;
    if (ts.tv_nsec >= 1000000000L) { ts.tv_sec++; ts.tv_nsec -= 1000000000L; }
    pthread_mutex_lock(&lock);
    while (ver == since && pthread_cond_timedwait(&cv, &lock, &ts) == 0) {}
    unsigned v = ver;
    pthread_mutex_unlock(&lock);
    return v;
}

int display_keeps_awake(void)
{
    pthread_mutex_lock(&lock);
    int r = ds[DS_MODE] == DISPLAY_ALWAYS || ds[DS_MODE] == DISPLAY_DIM || ringing[0];
    pthread_mutex_unlock(&lock);
    return r;
}

int display_screen_timeout(int stock_ms)
{
    pthread_mutex_lock(&lock);
    int on = ds[DS_MODE] == DISPLAY_ALWAYS || ds[DS_MODE] == DISPLAY_DIM;
    pthread_mutex_unlock(&lock);
    return on ? INT_MAX : stock_ms;
}

/* ---------------------------------------------------------------- text */

struct font { stbtt_fontinfo info; unsigned char *data; int ok; };
static struct font f_clock, f_text, f_bold;

static int font_load(struct font *f, const char *const *names)
{
    static const char *const dirs[] = { NULL, "/system/fonts", "/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu-sans-fonts",
                                        "/usr/share/fonts/TTF", "/usr/share/fonts/dejavu" };
    for (const char *const *n = names; *n; n++) for (size_t d = 0; d < sizeof dirs / sizeof *dirs; d++) {
        const char *dir = d ? dirs[d] : getenv("HASSMIC_FONT_DIR");
        char p[300]; FILE *fp; long len;
        if (!dir) continue;
        snprintf(p, sizeof p, "%s/%s", dir, *n);
        if (!(fp = fopen(p, "rb"))) continue;
        fseek(fp, 0, SEEK_END); len = ftell(fp); rewind(fp);
        unsigned char *b = len > 0 && len < (32 << 20) ? malloc((size_t)len) : NULL;
        if (b && fread(b, 1, (size_t)len, fp) == (size_t)len && stbtt_InitFont(&f->info, b, stbtt_GetFontOffsetForIndex(b, 0))) {
            fclose(fp); f->data = b; f->ok = 1;
            fprintf(stderr, "display: font %s\n", p);
            return 0;
        }
        free(b); fclose(fp);
    }
    return -1;
}

static uint32_t *px; static int W, H;                      /* the canvas: the display thread's */

static unsigned utf8_next(const char **s)
{
    const unsigned char *p = (const unsigned char *)*s; unsigned c = *p++;
    int n = c < 0x80 ? 0 : c >= 0xf0 ? 3 : c >= 0xe0 ? 2 : c >= 0xc0 ? 1 : -1;
    if (n < 0) { *s = (const char *)p; return 0xfffd; }
    c &= n ? 0x3f >> n : 0x7f;
    for (int i = 0; i < n; i++) { if ((*p & 0xc0) != 0x80) { *s = (const char *)p; return 0xfffd; } c = c << 6 | (*p++ & 0x3f); }
    *s = (const char *)p;
    return c;
}

/* width in pixels of `s` (its first `bytes`, -1 all) at `size` px */
static float text_w(const struct font *f, float size, const char *s, int bytes)
{
    if (!f->ok) return 0;
    float sc = stbtt_ScaleForPixelHeight(&f->info, size), x = 0; unsigned prev = 0;
    const char *end = bytes < 0 ? s + strlen(s) : s + bytes;
    while (s < end && *s) {
        unsigned c = utf8_next(&s); int adv, lsb;
        if (prev) x += sc * stbtt_GetCodepointKernAdvance(&f->info, (int)prev, (int)c);
        stbtt_GetCodepointHMetrics(&f->info, (int)c, &adv, &lsb);
        x += sc * adv; prev = c;
    }
    return x;
}

static uint32_t blend(uint32_t bg, uint32_t fg, int a)     /* a 0..255 */
{
    uint32_t r = ((bg >> 16 & 255) * (255 - a) + (fg >> 16 & 255) * a) / 255, g = ((bg >> 8 & 255) * (255 - a) + (fg >> 8 & 255) * a) / 255,
             b = ((bg & 255) * (255 - a) + (fg & 255) * a) / 255;
    return 0xff000000u | r << 16 | g << 8 | b;
}

/* `s` with its baseline at y, from x; returns where it ended */
static float text(const struct font *f, float size, float x, int y, const char *s, uint32_t rgb)
{
    if (!f->ok) return x;
    float sc = stbtt_ScaleForPixelHeight(&f->info, size); unsigned prev = 0;
    static unsigned char *g; static size_t gcap;
    while (*s) {
        unsigned c = utf8_next(&s); int adv, lsb, x0, y0, x1, y1;
        if (prev) x += sc * stbtt_GetCodepointKernAdvance(&f->info, (int)prev, (int)c);
        stbtt_GetCodepointHMetrics(&f->info, (int)c, &adv, &lsb);
        float sx = x - floorf(x);
        stbtt_GetCodepointBitmapBoxSubpixel(&f->info, (int)c, sc, sc, sx, 0, &x0, &y0, &x1, &y1);
        int gw = x1 - x0, gh = y1 - y0;
        if (gw > 0 && gh > 0) {
            if ((size_t)(gw * gh) > gcap) { free(g); gcap = (size_t)(gw * gh); g = malloc(gcap); if (!g) { gcap = 0; return x; } }
            stbtt_MakeCodepointBitmapSubpixel(&f->info, g, gw, gh, gw, sc, sc, sx, 0, (int)c);
            int ox = (int)floorf(x) + x0, oy = y + y0;
            for (int j = 0; j < gh; j++) {
                int yy = oy + j; if (yy < 0 || yy >= H) continue;
                for (int i = 0; i < gw; i++) {
                    int xx = ox + i, a = g[j * gw + i];
                    if (xx < 0 || xx >= W || !a) continue;
                    px[yy * W + xx] = blend(px[yy * W + xx], rgb, a);
                }
            }
        }
        x += sc * adv; prev = c;
    }
    return x;
}

static void centred(const struct font *f, float size, int y, const char *s, uint32_t rgb) { text(f, size, (W - text_w(f, size, s, -1)) / 2, y, s, rgb); }

static void fill(int x, int y, int w, int h, uint32_t rgb)
{
    for (int j = y < 0 ? 0 : y; j < y + h && j < H; j++) for (int i = x < 0 ? 0 : x; i < x + w && i < W; i++) px[j * W + i] = 0xff000000u | rgb;
}

/* `s` wrapped into lines of width `maxw`, at most `lines` (the last with an ellipsis if more is left); drawn from
 * baseline y down, `lh` apart, centred or from x.  Returns the baseline after the last */
static int wrapped(const struct font *f, float size, int x, int y, int maxw, int lines, int lh, int centre, const char *s, uint32_t rgb)
{
    char line[600];
    while (*s == ' ') s++;
    for (int n = 0; *s && n < lines; n++) {
        const char *p = s, *cut = NULL;
        while (*p) {                                        /* the longest run of words that fits */
            const char *q = p; while (*q == ' ') q++;
            const char *e = q; while (*e && *e != ' ') e++;
            if (text_w(f, size, s, (int)(e - s)) > maxw) break;
            cut = e; p = e;
        }
        if (!cut) {                                         /* one word wider than the line: cut it by characters */
            cut = s; while (*cut) { const char *nx = cut; utf8_next(&nx); if (text_w(f, size, s, (int)(nx - s)) > maxw) break; cut = nx; }
            if (cut == s) utf8_next(&cut);
        }
        int last = n == lines - 1 && *cut;
        size_t len = (size_t)(cut - s); if (len > sizeof line - 4) len = sizeof line - 4;
        memcpy(line, s, len); line[len] = 0;
        if (last) {                                         /* more than fits: an ellipsis, words taken off for it */
            while (len && text_w(f, size, line, -1) + text_w(f, size, "\xe2\x80\xa6", -1) > maxw) { while (len && (line[len - 1] & 0xc0) == 0x80) len--; if (len) len--; line[len] = 0; }
            strcat(line, "\xe2\x80\xa6");
        }
        if (centre) centred(f, size, y, line, rgb); else text(f, size, x, y, line, rgb);
        y += lh; s = cut; while (*s == ' ') s++;
    }
    return y;
}

/* ---------------------------------------------------------------- the picture */

#define WHITE 0xffffff
#define GREY  0x9aa0a6
#define CYAN  0x00caff                  /* stock's attention colour */
#define NIGHT 0x9a2a10                  /* a red that leaves the night dark */

struct look { int night, mode; int h24; time_t now; struct tm tm; char heard[600], reply[1200], ringing[160]; int words, running;
              int status, oobe, ever, tick; char ip[48], line[200]; };

/* the Wi-Fi's IPv4 address (the first not loopback's), "" without one */
static void local_ip(char *out, size_t cap)
{
    struct ifaddrs *ifs, *i; out[0] = 0;
    if (getifaddrs(&ifs)) return;
    for (i = ifs; i; i = i->ifa_next)
        if (i->ifa_addr && i->ifa_addr->sa_family == AF_INET && !(i->ifa_flags & IFF_LOOPBACK) && (i->ifa_flags & IFF_UP)) {
            inet_ntop(AF_INET, &((struct sockaddr_in *)i->ifa_addr)->sin_addr, out, (socklen_t)cap); break;
        }
    freeifaddrs(ifs);
}

static void clock_text(const struct look *l, char *hm, size_t cap, char *ampm, size_t acap)
{
    if (l->h24) { snprintf(hm, cap, "%02d:%02d", l->tm.tm_hour, l->tm.tm_min); ampm[0] = 0; return; }
    snprintf(hm, cap, "%d:%02d", l->tm.tm_hour % 12 ? l->tm.tm_hour % 12 : 12, l->tm.tm_min);
    snprintf(ampm, acap, "%s", l->tm.tm_hour < 12 ? "AM" : "PM");
}

static void draw(const struct look *l)
{
    static const char *const wd[7] = { "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday" };
    static const char *const mo[12] = { "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December" };
    char hm[16], ap[4], date[48], buf[160];
    for (int i = 0; i < W * H; i++) px[i] = 0xff000000u;
    uint32_t main_c = l->night ? NIGHT : WHITE, dim = l->night ? 0x5a1a0a : GREY, accent = l->night ? NIGHT : CYAN;
    int clock_ok = alarms_clock_ok();
    clock_text(l, hm, sizeof hm, ap, sizeof ap);
    snprintf(date, sizeof date, "%s, %s %d", wd[l->tm.tm_wday], mo[l->tm.tm_mon], l->tm.tm_mday);
    float u = H / 100.0f;                                   /* a hundredth of the height */
    int margin = (int)(W * 0.06f);

    if (l->ringing[0]) {                                    /* a ring: what rings, big, and what stops it */
        fill(0, 0, W, (int)(1.2f * u), accent);
        if (clock_ok) centred(&f_text, 9 * u, (int)(16 * u), hm, dim);
        int y = wrapped(&f_bold, 15 * u, margin, (int)(46 * u), W - 2 * margin, 2, (int)(17 * u), 1, l->ringing, main_c);
        (void)y;
        centred(&f_text, 7 * u, (int)(80 * u), strstr(l->ringing, "Alarm") ? "Tap to snooze  \xc2\xb7  hold or say \xe2\x80\x9cstop\xe2\x80\x9d" : "Tap or say \xe2\x80\x9cstop\xe2\x80\x9d", dim);
        return;
    }
    if (l->words && (l->heard[0] || l->reply[0] || l->running)) {      /* a request: its words, the clock small above */
        if (clock_ok) text(&f_text, 8 * u, margin, (int)(12 * u), hm, dim);
        int y = (int)(30 * u);
        if (l->heard[0]) y = wrapped(&f_text, 8 * u, margin, y, W - 2 * margin, 2, (int)(10 * u), 0, l->heard, dim) + (int)(4 * u);
        else if (l->running) { text(&f_text, 8 * u, margin, y, "Listening\xe2\x80\xa6", accent); y += (int)(14 * u); }
        if (l->reply[0]) wrapped(&f_text, 10 * u, margin, y + (int)(2 * u), W - 2 * margin, (int)((92 * u - y) / (12.5f * u)), (int)(12.5f * u), 0, l->reply, main_c);
        return;
    }
    if (l->status) {                                        /* the boot's status: what the Echo waits for */
        static const char *const dots[4] = { "", ".", "..", "..." };
        char t[240];
        fill(0, 0, W, (int)(1.2f * u), accent);
        if (l->line[0]) {                                   /* main.sh's (the splash, hassmic -Y) */
            centred(&f_bold, 11 * u, (int)(44 * u), "Starting", main_c);
            snprintf(t, sizeof t, "%s%s", l->line, dots[l->tick & 3]);
            centred(&f_text, 7 * u, (int)(62 * u), t, dim);
        } else if (l->oobe) {
            centred(&f_bold, 10 * u, (int)(30 * u), "Set up in Home Assistant", main_c);
            snprintf(t, sizeof t, "Settings \xe2\x80\xba Devices & services: add \xe2\x80\x9c%s\xe2\x80\x9d (ESPHome)", core_name ? core_name : "this Echo");
            wrapped(&f_text, 6.5f * u, margin, (int)(50 * u), W - 2 * margin, 2, (int)(9 * u), 1, t, dim);
            if (l->ip[0]) { snprintf(t, sizeof t, "Its settings: http://%s:28931", l->ip); centred(&f_text, 6.5f * u, (int)(72 * u), t, dim); }
            else centred(&f_text, 6.5f * u, (int)(72 * u), "Not on Wi-Fi yet: set it up with a phone (Improv) or the setup script", dim);
        } else if (!l->ip[0]) {
            centred(&f_bold, 10 * u, (int)(44 * u), "Waiting for Wi-Fi", main_c);
            snprintf(t, sizeof t, "No network%s", dots[l->tick & 3]); centred(&f_text, 7 * u, (int)(62 * u), t, dim);
        } else {
            centred(&f_bold, 10 * u, (int)(44 * u), l->ever ? "Home Assistant went away" : "Connecting to Home Assistant", main_c);
            snprintf(t, sizeof t, "Waiting%s", dots[l->tick & 3]); centred(&f_text, 7 * u, (int)(60 * u), t, accent);
        }
        if (!l->line[0] && l->ip[0]) {
            snprintf(t, sizeof t, "%s  \xc2\xb7  %s", core_name ? core_name : "", l->ip);
            centred(&f_text, 5.5f * u, (int)(90 * u), t, dim);
        }
        return;
    }
    /* idle: the clock */
    if (!clock_ok) { centred(&f_text, 8 * u, (int)(55 * u), "Waiting for Home Assistant to set the clock", dim); return; }
    float big = 46 * u, small = 11 * u, w = text_w(&f_clock, big, hm, -1), aw = ap[0] ? text_w(&f_text, small, ap, -1) + 2 * u : 0;
    float x = (W - w - aw) / 2;
    int base = (int)(60 * u);
    float e = text(&f_clock, big, x, base, hm, main_c);
    if (ap[0]) text(&f_text, small, e + 2 * u, base, ap, dim);
    centred(&f_text, 8 * u, (int)(76 * u), date, dim);
    struct alarm a; time_t nx = alarms_next(&a);
    if (nx) {
        if (nx == a.snoozed) { struct tm t; localtime_r(&nx, &t); char tt[16]; alarms_time_text(t.tm_hour, t.tm_min, l->h24, tt, sizeof tt); snprintf(buf, sizeof buf, "Snoozed until %s", tt); }
        else { char f[96]; alarms_format(&a, l->now, l->h24, f, sizeof f); snprintf(buf, sizeof buf, "Alarm %s%s%s", f, a.label[0] ? "  \xc2\xb7  " : "", a.label); }
        centred(&f_text, 6.5f * u, (int)(90 * u), buf, accent);
    }
}

/* ---------------------------------------------------------------- the screen's power */

static void spawn_settings(const char *name, int v)
{
    char s[16]; snprintf(s, sizeof s, "%d", v);
    char *argv[] = { "/system/bin/settings", "put", "system", (char *)name, s, NULL };
    core_spawn(argv);
}

static void screen_wake(void)
{
    char ms[24]; snprintf(ms, sizeof ms, "%lld", mono_ms());
    char *wake[] = { "/system/bin/service", "call", "power", "9", "i64", ms, "s16", "hassmic", "s16", "android", NULL };
    core_spawn(wake);
}

static int is_night(const struct look *l, int dark_room)
{
    int h = l->tm.tm_hour, s = ds[DS_NIGHT_START], e = ds[DS_NIGHT_END];
    int by_hour = s == e ? 0 : s < e ? h >= s && h < e : h >= s || h < e;
    float lux = dark_room ? core_lux() : NAN;
    return by_hour || (lux == lux && lux < NIGHT_LUX);
}

/* ---------------------------------------------------------------- touch */

static void *touch_thread(void *arg)
{
    const char *spec = arg; int fd = -1;
    if (!strncmp(spec, "name:", 5)) {
        const char *dir = getenv("HASSMIC_INPUT_DIR");
        for (int i = 0; i < 32 && fd < 0; i++) {
            char p[160], name[128] = ""; snprintf(p, sizeof p, "%s/event%d", dir ? dir : "/dev/input", i);
            if ((fd = open(p, O_RDONLY)) < 0) continue;
            if (ioctl(fd, EVIOCGNAME(sizeof name - 1), name) < 0 || strcmp(name, spec + 5)) { close(fd); fd = -1; }
        }
    } else fd = open(spec, O_RDONLY);
    if (fd < 0) { fprintf(stderr, "display: no touch screen (%s)\n", spec); return NULL; }
    fprintf(stderr, "display: touches from %s\n", spec);
    /* the panel's own axes, for the swipe in from an edge (the shell's bar, docs/screen-apps.md "The shell"): seen here
     * beside Android, so no window over the apps has to take the touch, and the app under the finger gets it all */
    struct input_absinfo ax = { 0 }, ay = { 0 };
    int axes = board.touch_top && !ioctl(fd, EVIOCGABS(ABS_MT_POSITION_X), &ax) && !ioctl(fd, EVIOCGABS(ABS_MT_POSITION_Y), &ay)
               && ax.maximum > ax.minimum && ay.maximum > ay.minimum;
    long long down = 0; struct input_event ev;
    /* the kernel drops a position equal to the last one sent, so a finger down where the last one was lifted sends none:
     * start from the panel's current values (EVIOCGABS gave them) */
    int x = axes ? ax.value : -1, y = axes ? ay.value : -1, sx = -1, sy = -1, pulled = 0;
    while (read(fd, &ev, sizeof ev) == (ssize_t)sizeof ev) {
        if (axes && ev.type == EV_ABS && ev.code == ABS_MT_POSITION_X) { x = ev.value; continue; }
        if (axes && ev.type == EV_ABS && ev.code == ABS_MT_POSITION_Y) { y = ev.value; continue; }
        if (axes && ev.type == EV_SYN && ev.code == SYN_REPORT && down && x >= 0 && y >= 0) {
            if (sx < 0) { sx = x; sy = y; }
            if (!pulled) {
                /* started within 4 % of an edge, moved in by 10 % of that axis: a pull from that edge */
                float fx = (float)(sx - ax.minimum) / (float)(ax.maximum - ax.minimum), fy = (float)(sy - ay.minimum) / (float)(ay.maximum - ay.minimum);
                float dx = (float)(x - sx) / (float)(ax.maximum - ax.minimum), dy = (float)(y - sy) / (float)(ay.maximum - ay.minimum);
                const char *edge = fx < .04f && dx > .10f ? "x0" : fx > .96f && dx < -.10f ? "x1" : fy < .04f && dy > .10f ? "y0" : fy > .96f && dy < -.10f ? "y1" : NULL;
                if (edge) { pulled = 1; kiosk_shell_pull(edge, edge[0] == 'x' ? fy : fx); }
            }
            continue;
        }
        /* BTN_TOUCH, or a multitouch (protocol B) driver's tracking id alone: >= 0 a finger down, -1 lifted */
        int v;
        if (ev.type == EV_KEY && ev.code == BTN_TOUCH) v = ev.value;
        else if (ev.type == EV_ABS && ev.code == ABS_MT_TRACKING_ID) v = ev.value >= 0;
        else continue;
        if (v == 1) { if (!down) { down = mono_ms(); sx = sy = -1; pulled = 0; } }
        else if (v == 0 && down) {
            long long held = mono_ms() - down; down = 0;
            if (pulled) continue;                           /* a pull for the bar: no tap, no hold */
            if (held < TAP_MS) core_touch(0); else if (held >= HOLD_MS) core_touch(1);
        }
    }
    fprintf(stderr, "display: the touch screen went away\n");
    close(fd);
    return NULL;
}

/* ---------------------------------------------------------------- the thread */

static int write_all_(int fd, const void *p, size_t n)
{
    const char *c = p;
    while (n) { ssize_t w = write(fd, c, n); if (w < 0 && errno == EINTR) continue; if (w <= 0) return -1; c += w; n -= (size_t)w; }
    return 0;
}

static void state_path(char *out, size_t cap, const char *file)
{
    const char *e = getenv("HASSMIC_STATE");
    snprintf(out, cap, "%s/%s", e ? e : "/data/local/hassmic/state", file);
}

/* the splash (hassmic -Y, main.sh) ends once this display has the screen: its layer goes with it */
static void splash_end(void)
{
    char p[300]; FILE *f; int pid = 0;
    state_path(p, sizeof p, "splash.pid");
    if (!(f = fopen(p, "r"))) return;
    if (fscanf(f, "%d", &pid) != 1) pid = 0;
    fclose(f); unlink(p);
    /* only a splash: a pid file left by one that died may name a process of the same user by now */
    char cl[300], cmd[256] = ""; snprintf(cl, sizeof cl, "/proc/%d/cmdline", pid);
    if ((f = fopen(cl, "r"))) { size_t n = fread(cmd, 1, sizeof cmd - 1, f); fclose(f); for (size_t i = 0; i < n; i++) if (!cmd[i]) cmd[i] = ' '; cmd[n] = 0; }
    if (!strstr(cmd, " -Y ")) return;
    if (pid > 1 && pid != getpid() && !kill(pid, SIGTERM)) fprintf(stderr, "display: the boot's splash ended\n");
}

static int tick;

static void fonts_load(void)
{
    static const char *const clock_fonts[] = { "AmazonEmberDisplay_Lt.ttf", "AmazonEmberDisplay_Rg.ttf", "Amazon-Ember-Light.ttf", "Roboto-Light.ttf", "DejaVuSans-ExtraLight.ttf", "DejaVuSans.ttf", NULL };
    static const char *const text_fonts[] = { "Amazon-Ember-Regular.ttf", "Roboto-Regular.ttf", "DroidSans.ttf", "DejaVuSans.ttf", NULL };
    static const char *const bold_fonts[] = { "Amazon-Ember-Bold.ttf", "Roboto-Bold.ttf", "DroidSans-Bold.ttf", "DejaVuSans-Bold.ttf", NULL };
    if (font_load(&f_text, text_fonts)) fprintf(stderr, "display: no font found: the screen stays black\n");
    if (font_load(&f_clock, clock_fonts)) f_clock = f_text;
    if (font_load(&f_bold, bold_fonts)) f_bold = f_text;
}

int display_splash(const char *file)
{
    char p[300]; int fd = -1, w = 0, h = 0, rows = ring_band_rows(-1);
    if (rows < 0) rows = 0;
    signal(SIGPIPE, SIG_IGN);
    fonts_load();
    if (ring_band_screen(rows, &fd, &w, &h) < 0 || w <= 0 || h <= 0 || w > 4096 || h > 4096) return 1;
    if (!(px = malloc((size_t)w * h * 4))) return 1;
    W = w; H = h;
    state_path(p, sizeof p, "splash.pid");
    { char t[16]; int n = snprintf(t, sizeof t, "%d\n", (int)getpid()); statefile_write(p, 0644, t, (size_t)n); }
    for (long long until = mono_ms() + 180000; mono_ms() < until; ) {
        struct look l; memset(&l, 0, sizeof l);
        FILE *f = fopen(file, "r");
        if (f) { if (!fgets(l.line, sizeof l.line, f)) l.line[0] = 0; fclose(f); }
        l.line[strcspn(l.line, "\r\n")] = 0;
        if (!l.line[0]) snprintf(l.line, sizeof l.line, "Starting the voice satellite");
        l.status = 1; l.tick = tick++;
        draw(&l);
        if (write_all_(fd, px, (size_t)W * H * 4) < 0) break;
        usleep(500000);
    }
    close(fd);
    return 0;
}

static void *display_thread(void *arg)
{
    (void)arg;
    int fd = -1, have_rows = -1, have_mode = -1, light = -1, night_was = -1, fails = 0;
    long long next_try = 0;
    fonts_load();
    for (;;) {
        struct look l; memset(&l, 0, sizeof l);
        pthread_mutex_lock(&lock);
        int mode = ds[DS_MODE], dark = ds[DS_DARK_ROOM], bright = ds[DS_BRIGHT], nbright = ds[DS_NIGHT_BRIGHT];
        long long now_ms_ = mono_ms();
        if (words_until && now_ms_ >= words_until) { words_until = 0; heard[0] = reply[0] = 0; ver++; pthread_cond_broadcast(&cv); }
        l.running = running; l.words = ds[DS_TEXT] && (running || words_until || heard[0] || reply[0]);
        snprintf(l.heard, sizeof l.heard, "%s", heard); snprintf(l.reply, sizeof l.reply, "%s", reply);
        snprintf(l.ringing, sizeof l.ringing, "%s", ringing);
        int lk = linked, kiosk_on = ds[DS_KIOSK];
        l.ever = ever_linked;
        dirty = 0;
        pthread_mutex_unlock(&lock);
        l.oobe = core_oobe();
        l.status = !lk && !l.ringing[0];
        if (l.status) local_ip(l.ip, sizeof l.ip);
        l.tick = tick++;
        /* until Home Assistant is there the screen says what the Echo waits for, whatever the setting */
        int show = l.status && mode == DISPLAY_OFF ? DISPLAY_AWAKE : mode;
        /* the kiosk app has the screen while nothing of ours is to show: a ring, a request's words, the status */
        int kiosk = kiosk_on && lk && !l.oobe && mode != DISPLAY_OFF;     /* off: black, the app blank too (web.c) */
        /* an app has the screen while nothing of ours is to show; a screen app that draws the request's words or a ring
         * itself (docs/screen-apps.md "What an app takes over") keeps it for those */
        int dr = kiosk_draws();
        int to_kiosk = kiosk && kiosk_tick(1) && (!l.ringing[0] || (dr & KIOSK_DRAWS_RING)) && (!l.words || (dr & KIOSK_DRAWS_WORDS));
        int rows = ring_band_rows(-1); if (rows < 0) rows = 0;
        if (show == DISPLAY_OFF || to_kiosk || rows != have_rows) {
            if (fd >= 0) { close(fd); fd = -1; fprintf(stderr, "display: %s\n", to_kiosk ? "the kiosk's" : "off"); }
            have_rows = -1;
        }
        if (mode != have_mode) {
            if (mode == DISPLAY_ALWAYS || mode == DISPLAY_DIM) screen_wake();
            if (mode != DISPLAY_OFF && have_mode <= DISPLAY_OFF) light = -1;      /* the backlight set anew */
            fprintf(stderr, "display: %s\n", display_modes[mode]);
            have_mode = mode;
        }
        if (show != DISPLAY_OFF && !to_kiosk && fd < 0 && now_ms_ >= next_try) {
            int w = 0, h = 0;
            if (ring_band_screen(rows, &fd, &w, &h) < 0 || w <= 0 || h <= 0 || w > 4096 || h > 4096) {
                if (fd >= 0) close(fd);
                fd = -1; next_try = now_ms_ + 30000;
                if (!fails++) fprintf(stderr, "display: no renderer, trying again every 30 s\n");
            } else {
                fails = 0; have_rows = rows;
                if (w != W || h != H) { free(px); px = malloc((size_t)w * h * 4); W = w; H = h; }
                if (!px) { close(fd); fd = -1; W = H = 0; }
                else { fprintf(stderr, "display: %d x %d above the band\n", W, H); splash_end(); }
            }
        }
        l.now = alarms_now();
        localtime_r(&l.now, &l.tm);
        l.h24 = alarms_h24(); l.mode = mode;
        int night = mode == DISPLAY_DIM && is_night(&l, dark);
        l.night = night && !l.ringing[0] && !(l.words && (l.reply[0] || l.running));    /* a ring and an answer are read in full light */
        if (show != DISPLAY_OFF) {                          /* the backlight: Android's, in its 0..255 */
            int want = (night && !l.ringing[0] ? nbright : bright) * 255 / 100;
            if (want < 1) want = 1;
            if (want != light) { if (light < 0) spawn_settings("screen_brightness_mode", 0); spawn_settings("screen_brightness", want); light = want; }
            if (night != night_was && night_was >= 0) fprintf(stderr, "display: %s\n", night ? "night" : "day");
            night_was = night;
        }
        if (fd >= 0 && px) {
            draw(&l);
            if (write_all_(fd, px, (size_t)W * H * 4) < 0) { fprintf(stderr, "display: the renderer is gone, starting it again\n"); close(fd); fd = -1; have_rows = -1; }
        }
        /* until something changes or the minute turns (a second for a ring's clock, the words' end) */
        pthread_mutex_lock(&lock);
        if (!dirty) {
            struct timespec ts; clock_gettime(CLOCK_REALTIME, &ts);
            long wait_s = 60 - l.tm.tm_sec; if (wait_s < 1) wait_s = 1;
            if (words_until) { long left = (long)((words_until - mono_ms() + 999) / 1000); if (left < wait_s) wait_s = left < 1 ? 1 : left; }
            if (fd < 0 && mode != DISPLAY_OFF && wait_s > 30) wait_s = 30;
            if (l.status) wait_s = 1;                           /* the status's dots */
            else if (kiosk && wait_s > 5) wait_s = 5;           /* whether the app is in front, from its polls */
            ts.tv_sec += wait_s;
            pthread_cond_timedwait(&cv, &lock, &ts);
        }
        pthread_mutex_unlock(&lock);
    }
    return NULL;
}

void display_start(void)
{
    pthread_mutex_lock(&lock);
    int go = !started; started = 1;
    pthread_mutex_unlock(&lock);
    if (!go) return;
    pthread_t t;
    if (!pthread_create(&t, NULL, display_thread, NULL)) pthread_detach(t);
    if (board.touch && !pthread_create(&t, NULL, touch_thread, (void *)board.touch)) pthread_detach(t);
}
