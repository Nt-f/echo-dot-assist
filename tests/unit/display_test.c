/* display_screen.c on the PC against a stand-in for ringbar.dex's "screen" mode (HASSMIC_FAKE_BAND: says "ready 320
 * <180 - band rows>", keeps every frame): the clock idle, a request's words, a ring, night in always_dim, the screen's
 * power and backlight through the settings tool, the screen switched off.  build/display.ppm shows the last frames for
 * the eye.  The text checks need a TrueType font (the PC's DejaVu); without one only the rest is checked. */
#define _GNU_SOURCE
#include "display.h"
#include "alarms.h"
#include "board.h"
#include "kiosk.h"
#include "ring.h"
#include <limits.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

const struct board board = { .volume_steps = 100 };
int clock_synced(void) { return 1; }
int core_muted(void) { return 0; }
int core_dnd(int set) { (void)set; return 0; }
int core_led_brightness(int set) { (void)set; return 100; }
static float lux = NAN;
float core_lux(void) { return lux; }
void core_touch(int held) { (void)held; }
const char *core_name = "Echo Show 5 3fce9a";
int core_oobe(void) { return 0; }
static int last_brightness = -1, wakes, am_starts, shell_starts, monkeys;
static char last_start[200];
void core_run(char *const argv[], char *out, size_t n) { (void)argv; if (n) out[0] = 0; }
void core_spawn(char *const argv[])
{
    if (!strcmp(argv[0], "/system/bin/am") && !strcmp(argv[1], "startservice")) shell_starts++;
    else if (!strcmp(argv[0], "/system/bin/am")) { am_starts++; snprintf(last_start, sizeof last_start, "%s", argv[argv[1] && !strcmp(argv[1], "start") ? 6 : 1]); }
    if (!strcmp(argv[0], "/system/bin/monkey")) { monkeys++; snprintf(last_start, sizeof last_start, "%s", argv[2]); }
    if (!strcmp(argv[0], "/system/bin/settings") && !strcmp(argv[3], "screen_brightness")) last_brightness = atoi(argv[4]);
    if (!strcmp(argv[0], "/system/bin/service") && !strcmp(argv[3], "9")) wakes++;
}

static int fails;
static void check(int ok, const char *what) { printf("%s %s\n", ok ? "ok  " : "FAIL", what); if (!ok) fails++; }
static void ms(int n) { usleep(n * 1000); }
#define WAIT(cond) for (int w_ = 0; w_ < 200 && !(cond); w_++) ms(20)

#define W 320
#define H 170                           /* 180 - the band's 10 */
static char frames[300];
static unsigned char fr[W * H * 4];

static long nframes(void) { struct stat st; return stat(frames, &st) ? 0 : st.st_size / (W * H * 4); }
static int last_frame(void)
{
    FILE *f = fopen(frames, "rb"); long n = nframes();
    if (!f || !n) { if (f) fclose(f); return -1; }
    fseek(f, (n - 1) * (long)sizeof fr, SEEK_SET);
    int ok = fread(fr, 1, sizeof fr, f) == sizeof fr;
    fclose(f);
    return ok ? 0 : -1;
}
static unsigned pix(int x, int y) { const unsigned char *p = fr + (y * W + x) * 4; return (unsigned)p[2] << 16 | p[1] << 8 | p[0]; }
/* lit pixels in rows y0..y1 (percent of the height); *red: of them, how many are red rather than white or grey */
static int lit(int y0, int y1, int *red)
{
    int n = 0, r = 0;
    for (int y = H * y0 / 100; y < H * y1 / 100; y++) for (int x = 0; x < W; x++) {
        unsigned v = pix(x, y); int R = v >> 16 & 255, G = v >> 8 & 255, B = v & 255;
        if (R + G + B > 60) { n++; if (R > 2 * G && R > 2 * B) r++; }
    }
    if (red) *red = r;
    return n;
}
static void ppm(void)
{
    FILE *f = fopen("build/display.ppm", "wb");
    if (!f) return;
    fprintf(f, "P6 %d %d 255\n", W, H);
    for (int i = 0; i < W * H; i++) { unsigned char c[3] = { fr[i * 4 + 2], fr[i * 4 + 1], fr[i * 4] }; fwrite(c, 1, 3, f); }
    fclose(f);
}

int main(void)
{
    char dir[] = "/tmp/display_XXXXXX", script[300], st[300];
    if (!mkdtemp(dir)) return 1;
    snprintf(frames, sizeof frames, "%s/frames", dir);
    snprintf(script, sizeof script, "%s/ringbar", dir);
    FILE *f = fopen(script, "w");
    fprintf(f, "#!/bin/sh\nif [ \"$1\" = screen ]; then echo \"ready %d $((180 - $2))\"; echo \"screen $2\" >> %s/log; exec cat >> %s; fi\n"
               "echo \"ready %d $1\"; exec cat > /dev/null\n", W, dir, frames, W);
    fclose(f); chmod(script, 0755);
    setenv("HASSMIC_FAKE_BAND", script, 1);
    snprintf(st, sizeof st, "%s/state", dir); mkdir(st, 0700);
    setenv("HASSMIC_STATE", st, 1);
    setenv("TZ", "UTC", 1); tzset();
    int font = 0;
    { const char *d[] = { "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf", "/usr/share/fonts/TTF/DejaVuSans.ttf" };
      for (size_t i = 0; i < 3; i++) font |= !access(d[i], R_OK); }
    if (!font) printf("note: no DejaVu font on this PC, the text checks are skipped\n");

    check(display_present() == 1, "a screen");
    check(display_setting(DS_MODE, INT_MIN) == DISPLAY_AWAKE, "awake by default: the clock while the screen is on");
    check(display_screen_timeout(300000) == 300000, "awake: stock's timeout left as it is");
    display_start();
    WAIT(nframes() >= 1);
    check(nframes() >= 1 && !last_frame(), "a frame of 320 x 170 above a band of 10");
    check(last_brightness == 80 * 255 / 100, "the backlight at the day level (80 %)");
    check(pix(5, 0) == 0x00caff, "before Home Assistant: the boot's status (the bar along the top)");
    if (font) check(lit(35, 65, NULL) > 200, "the status: what the Echo waits for");
    { long k = nframes(); ms(2300); check(nframes() >= k + 2, "the status: drawn again each second (its dots)"); }
    display_link(1);
    WAIT((last_frame(), pix(5, 0) != 0x00caff));
    check(pix(5, 0) != 0x00caff, "Home Assistant there: the status gone");
    int red;
    if (font) check(lit(25, 65, NULL) > 300 && lit(0, 15, NULL) == 0, "idle: the clock big in the middle, nothing at the top");

    long n0 = nframes();
    display_run(1);
    display_heard("turn on the kitchen lights");
    display_reply("Okay, the kitchen lights are on. The living room lights were already on, and the hallway is dark.");
    WAIT(nframes() > n0 + 2);
    ms(100); last_frame();
    if (font) check(lit(0, 15, NULL) > 20 && lit(35, 95, NULL) > 300, "a request: the clock small at the top, the reply below");
    display_setting(DS_TEXT_S, 3);
    display_run(0);
    ms(200); n0 = nframes();
    WAIT(nframes() > n0); ms(100);
    WAIT((last_frame(), lit(0, 15, NULL) == 0) || !font);
    if (font) { last_frame(); check(lit(0, 15, NULL) == 0 && lit(25, 65, NULL) > 300, "its words go after display_text_seconds: the clock again"); }

    display_ringing("Alarm 7 AM");
    WAIT((last_frame(), pix(5, 0) == 0x00caff));
    check(pix(5, 0) == 0x00caff, "a ring: the bar along the top in stock's cyan");
    if (font) check(lit(25, 60, NULL) > 300, "a ring: what rings, big");
    ppm();
    display_ringing(NULL);
    WAIT((last_frame(), pix(5, 0) != 0x00caff));
    check(pix(5, 0) != 0x00caff, "the ring over: no bar");

    struct alarm a = { .hour = 7, .min = 30, .days = DAYS_DAILY, .enabled = 1 };
    alarms_put(&a);
    display_changed();
    n0 = nframes(); WAIT(nframes() > n0); ms(100); last_frame();
    if (font) check(lit(85, 97, NULL) > 50, "the next alarm under the date");

    /* always_dim, at night: the hour now inside the night's hours */
    time_t now = time(NULL); struct tm tm; localtime_r(&now, &tm);
    display_setting(DS_NIGHT_START, tm.tm_hour); display_setting(DS_NIGHT_END, (tm.tm_hour + 1) % 24);
    display_setting(DS_MODE, DISPLAY_DIM);
    check(display_screen_timeout(300000) == INT_MAX && display_keeps_awake(), "always_dim: the screen never sleeps");
    WAIT(last_brightness == 10 * 255 / 100);
    check(last_brightness == 10 * 255 / 100, "night: the backlight at the night level (10 %)");
    check(wakes >= 1, "always on: the screen woken");
    ms(200); last_frame();
    if (font) { lit(25, 65, &red); check(red > 200, "night: the clock in a dim red"); }
    ppm();
    display_setting(DS_NIGHT_START, (tm.tm_hour + 2) % 24); display_setting(DS_NIGHT_END, (tm.tm_hour + 3) % 24);
    WAIT(last_brightness == 80 * 255 / 100);
    check(last_brightness == 80 * 255 / 100, "day again: the day level");
    lux = 1;
    display_setting(DS_DARK_ROOM, 1); display_changed();
    WAIT(last_brightness == 10 * 255 / 100);
    check(last_brightness == 10 * 255 / 100, "a dark room (1 lux) is night too");
    lux = NAN;

    display_setting(DS_MODE, DISPLAY_ALWAYS);
    check(display_screen_timeout(60000) == INT_MAX, "always: never sleeps, muted or not");
    display_setting(DS_MODE, DISPLAY_OFF);
    check(display_screen_timeout(300000) == 300000 && !display_keeps_awake(), "off: stock's timeout");
    ms(400); n0 = nframes(); display_changed(); display_reply("nobody sees this"); ms(400);
    check(nframes() == n0, "off: no frames");
    display_setting(DS_MODE, DISPLAY_AWAKE);
    WAIT(nframes() > n0);
    check(nframes() > n0, "on again: the renderer started anew");

    /* off and Home Assistant gone: the status anyway */
    display_setting(DS_MODE, DISPLAY_OFF); ms(400);
    display_link(0); n0 = nframes();
    WAIT(nframes() > n0);
    WAIT((last_frame(), pix(5, 0) == 0x00caff));
    check(nframes() > n0 && pix(5, 0) == 0x00caff, "off, Home Assistant gone: the status shows anyway");
    display_link(1); ms(400); n0 = nframes(); ms(1200);
    check(nframes() == n0, "off again once it is back");
    display_setting(DS_MODE, DISPLAY_AWAKE);

    /* the kiosk: the app started, the screen its while it is in front and nothing of ours shows */
    char err[100];
    check(!kiosk_store("ha http://192.168.1.5:8123\nscreen Home\thttp://192.168.1.5:8123/echo_local/wall.html\nscreen Music\thttp://192.168.1.5:8123/music\n", err, sizeof err), "kiosk: two screens stored");
    check(kiosk_store("screen Bad\tjavascript:alert(1)\n", err, sizeof err) && strstr(err, "http"), "kiosk: only http(s) screens");
    check(kiosk_configured(), "kiosk: still the two screens after a refused config");
    { size_t jn; char *j = kiosk_json(0, 1, &jn); check(j && strstr(j, "\"name\":\"Music\"") && !strstr(j, "\"token\":\""), "kiosk: its JSON, no token unless asked"); free(j); }
    /* the screen app's own settings: to the app on loopback only */
    check(!kiosk_store("ha http://192.168.1.5:8123\nscreen Home\thttp://192.168.1.5:8123/\nset immich.url http://192.168.1.9:2283\nset immich.key abc123\n", err, sizeof err),
          "kiosk: settings stored");
    { size_t jn; char *j = kiosk_json(1, 1, &jn), *k = kiosk_json(0, 1, &jn);
      check(j && strstr(j, "\"settings\":{\"immich.url\":\"http://192.168.1.9:2283\",\"immich.key\":\"abc123\"}"), "kiosk: settings in the app's config");
      check(k && !strstr(k, "abc123"), "kiosk: not in the signed API's answer"); free(j); free(k); }
    check(kiosk_store("set Bad/Key x\n", err, sizeof err) && strstr(err, "key"), "kiosk: a key of a-z 0-9 . _ - only");
    check(!kiosk_store("ha http://192.168.1.5:8123\nscreen Home\thttp://192.168.1.5:8123/echo_local/wall.html\nscreen Music\thttp://192.168.1.5:8123/music\n", err, sizeof err), "kiosk: back to two screens");
    display_setting(DS_KIOSK, 1);
    WAIT(am_starts > 0);
    check(am_starts == 1, "kiosk on: the app started");
    kiosk_polled(1, 0); display_changed();
    ms(600); n0 = nframes(); ms(1500);
    check(nframes() == n0, "the app in front: our layer gone (no frames)");
    display_ringing("Alarm 7 AM");
    WAIT(nframes() > n0);
    check(nframes() > n0, "a ring over the kiosk: our layer back");
    display_ringing(NULL); ms(600); n0 = nframes(); ms(1500);
    check(nframes() == n0, "the ring over: the kiosk's again");
    kiosk_polled(0, 0); display_changed();
    WAIT(nframes() > n0);
    check(nframes() > n0 && am_starts == 1, "the app paused: the clock, the app not started again within the minute");
    /* an app that draws the words and a ring itself (its poll says /front/draws): the screen stays its; the state feed */
    kiosk_polled(1, KIOSK_DRAWS_WORDS | KIOSK_DRAWS_RING); display_changed();
    ms(600); n0 = nframes();
    char js[4600]; display_state_json(js, sizeof js);
    unsigned v0 = (unsigned)atoi(strstr(js, "\"v\":") + 4);
    display_ringing("Alarm 7 AM"); ms(1500);
    check(nframes() == n0, "an app that draws: a ring leaves the screen to it");
    display_state_json(js, sizeof js);
    check(strstr(js, "\"ringing\":\"Alarm 7 AM\"") && strstr(js, "\"ringing_alarm\":true"), "the state: what rings");
    unsigned v1 = (unsigned)atoi(strstr(js, "\"v\":") + 4);
    check(v1 != v0, "the state: a new version");
    display_ringing(NULL);
    long long t0 = 0; { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); t0 = t.tv_sec * 1000LL + t.tv_nsec / 1000000; }
    unsigned v2 = display_wait(v1, 3000);             /* already newer: at once */
    display_heard("what time is it"); display_state_json(js, sizeof js);
    check(v2 != v1 && strstr(js, "\"heard\":\"what time is it\"") && strstr(js, "\"words\":true"), "the state: the words");
    unsigned v3 = (unsigned)atoi(strstr(js, "\"v\":") + 4);
    { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); long long t1 = t.tv_sec * 1000LL + t.tv_nsec / 1000000; unsigned v4 = display_wait(v3, 400);
      clock_gettime(CLOCK_MONOTONIC, &t); long long t2 = t.tv_sec * 1000LL + t.tv_nsec / 1000000;
      check(v4 == v3 && t2 - t1 >= 350 && t1 - t0 < 1000, "the long poll: nothing new, it waits its time"); }
    /* the screen lent to another app (a video client the screen app started): our layer stays off as while the app is
     * in front, but a ring comes over the other app (it draws none), and /front ends it */
    display_heard(NULL);
    check(kiosk_lent("org.schabi.newpipe") == 0 && kiosk_lent("a;b") == -1, "lent: a package name only");
    display_changed(); ms(600); n0 = nframes(); ms(1500);
    check(nframes() == n0 && kiosk_front(), "lent: our layer stays off over the other app");
    display_ringing("Alarm 7 AM");
    WAIT(nframes() > n0);
    check(nframes() > n0, "lent: a ring over the other app (it draws none)");
    display_ringing(NULL); ms(600); n0 = nframes(); ms(1500);
    check(nframes() == n0, "lent: the ring over, the other app's again");
    kiosk_polled(0, 0); display_changed();
    WAIT(nframes() > n0);
    check(nframes() > n0 && !kiosk_front(), "lent ends with a /back poll: the clock");
    /* what an app takes over, as its poll says (docs/screen-apps.md "What an app takes over") */
    check(kiosk_draws_parse("") == 0 && kiosk_draws_parse("/draws") == (KIOSK_DRAWS_WORDS | KIOSK_DRAWS_RING)
          && kiosk_draws_parse("/draws/ring") == KIOSK_DRAWS_RING && kiosk_draws_parse("/draws/words+ring") == (KIOSK_DRAWS_WORDS | KIOSK_DRAWS_RING)
          && kiosk_draws_parse("/draws/home,words,later") == KIOSK_DRAWS_WORDS && kiosk_draws_parse("/drawsx") == 0, "draws: the list in the poll's path");
    kiosk_polled(1, KIOSK_DRAWS_RING); display_changed(); ms(600); n0 = nframes();
    display_ringing("Alarm 7 AM"); ms(1500);
    check(nframes() == n0, "an app that draws the ring only: the ring left to it");
    display_ringing(NULL); display_heard("lights on"); WAIT(nframes() > n0);
    check(nframes() > n0, "... the request's words drawn by us over it");
    display_heard(NULL); ms(600);

    /* on Android: what is in front, from /proc (a stand-in here): any of the owner's apps has the screen without
     * polling; hassmic's home in front (nothing) for 5 s: the screen app started again; the shell started when gone */
    char proc[300]; snprintf(proc, sizeof proc, "%s/proc", dir);
    #define PROC(pid, cmd, adj) do { char f_[400]; snprintf(f_, sizeof f_, "%s/%d", proc, pid); mkdir(f_, 0755); \
        snprintf(f_, sizeof f_, "%s/%d/cmdline", proc, pid); FILE *o_ = fopen(f_, "w"); fwrite(cmd, 1, strlen(cmd) + 1, o_); fclose(o_); \
        snprintf(f_, sizeof f_, "%s/%d/oom_score_adj", proc, pid); o_ = fopen(f_, "w"); fprintf(o_, "%d\n", adj); fclose(o_); } while (0)
    mkdir(proc, 0755);
    PROC(100, "org.schabi.newpipe", 0); PROC(101, "io.github.gamer92000.echodotassist.kiosk", 700); PROC(102, "com.amazon.webview.chromium:sandboxed_process0", 0);
    setenv("HASSMIC_PROC", proc, 1);
    kiosk_polled(0, 0);                                 /* the screen app's poll says it is paused: Android's word counts */
    ms(1200); display_changed(); ms(600); n0 = nframes(); ms(1500);
    { char fg[160]; int f = kiosk_in_front(fg, sizeof fg);
      check(f == 1 && !strcmp(fg, "org.schabi.newpipe") && kiosk_front(), "Android: the app in front by /proc (the screen app's polls no matter)"); }
    check(nframes() == n0, "Android: our layer off over it");
    WAIT(shell_starts > 0);
    check(shell_starts == 1, "Android: the shell started (its process not there)");
    PROC(103, "io.github.gamer92000.echodotassist.kiosk:shell", 200);
    display_ringing("Timer"); WAIT(nframes() > n0);
    check(nframes() > n0, "Android: a ring over another app (it draws none, whatever the screen app said)");
    display_ringing(NULL);
    int am0 = am_starts;
    PROC(100, "org.schabi.newpipe", 700); PROC(104, "org.hassmic.home", 0);
    ms(1200);
    check(kiosk_in_front(NULL, 0) == 0 && !kiosk_front(), "Android: hassmic's home in front: no app");
    for (int i = 0; i < 90 && am_starts == am0; i++) { display_changed(); ms(100); }
    check(am_starts == am0 + 1 && !strcmp(last_start, "io.github.gamer92000.echodotassist.kiosk"), "Android: nothing in front for 5 s: the screen app started again");
    PROC(104, "org.hassmic.home", 700); PROC(101, "io.github.gamer92000.echodotassist.kiosk", 0);
    ms(1200);
    { char sj[600]; size_t sn; char *j = kiosk_shell_json(1, &sn); snprintf(sj, sizeof sj, "%s", j ? j : ""); free(j);
      check(strstr(sj, "\"app\":\"io.github.gamer92000.echodotassist.kiosk\"") && strstr(sj, "\"screens\":[\"Home\",\"Music\"]")
            && strstr(sj, "\"front\":\"io.github.gamer92000.echodotassist.kiosk\""), "the shell's config: the screen app, the screens, what is in front"); }
    /* /proc hiding the others' processes (hidepid=2 without the readproc group): no app seen at all is not known,
     * not "nothing in front" (which would start the screen app every 15 s) */
    { char c2[600]; snprintf(c2, sizeof c2, "chmod 000 '%s'/*/oom_score_adj", proc); if (system(c2)) {} }
    ms(1200);
    check(kiosk_in_front(NULL, 0) == -1, "Android: the apps seen, their oom_score_adj not readable (Fire OS 7): not known");
    { char c2[600]; snprintf(c2, sizeof c2, "chmod -R u+rwx '%s'; rm -rf '%s'/*", proc, proc); if (system(c2)) {} }
    ms(1200);
    check(kiosk_in_front(NULL, 0) == -1, "Android: no app's process visible (hidepid): not known, the polls decide");
    unsetenv("HASSMIC_PROC"); ms(1200);
    /* the shell's watcher (an accessibility service) says what is in front where /proc cannot (Fire OS 7) */
    check(kiosk_shell_front("a;b") == -1, "watcher: a package name only");
    kiosk_shell_front("org.schabi.newpipe");
    { char fg[160]; int f = kiosk_in_front(fg, sizeof fg);
      check(f == 1 && !strcmp(fg, "org.schabi.newpipe") && kiosk_front(), "watcher: its word is what is in front"); }
    display_ringing("Timer"); n0 = nframes(); WAIT(nframes() > n0);
    check(nframes() > n0, "watcher: a ring over the app it reported (it draws none)");
    display_ringing(NULL);
    /* a swipe in from an edge, seen by hassmic's touch reader: the shell's long poll has it (and waits for the next) */
    { char o[200]; kiosk_shell_wait(0xffffffffu, 0, o, sizeof o);
      unsigned v0 = (unsigned)atoi(strstr(o, "\"v\":") + 4);
      kiosk_shell_pull("x1", .5f);
      kiosk_shell_wait(v0, 2000, o, sizeof o);
      check(strstr(o, "\"edge\":\"x1\"") && strstr(o, "\"at\":0.500") && (unsigned)atoi(strstr(o, "\"v\":") + 4) == v0 + 1, "pull: the shell's long poll has the edge and where along it");
      struct timespec a1, a2; clock_gettime(CLOCK_MONOTONIC, &a1); kiosk_shell_wait(v0 + 1, 300, o, sizeof o); clock_gettime(CLOCK_MONOTONIC, &a2);
      check((a2.tv_sec - a1.tv_sec) * 1000 + (a2.tv_nsec - a1.tv_nsec) / 1000000 >= 250, "pull: nothing new, it waits its time"); }
    kiosk_shell_front("org.hassmic.home"); ms(50);
    check(kiosk_in_front(NULL, 0) == 0, "watcher: hassmic's home reported: no app in front");
    kiosk_polled(1, 0);
    display_setting(DS_KIOSK, 0);

    char c[400]; snprintf(c, sizeof c, "rm -rf '%s'", dir); if (system(c)) {}
    printf(fails ? "display: %d FAILED\n" : "display: all ok\n", fails);
    return fails != 0;
}
