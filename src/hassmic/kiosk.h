/* The kiosk: Home Assistant (or Music Assistant, or any page) on the Echo Show's screen, in hassmic's own app
 * (tools/kiosk/: io.github.gamer92000.echodotassist.kiosk, a WebView on the firmware's Amazon WebView, Chromium 118), set up from Home
 * Assistant by the Echo Local integration (custom_components/echo_local: the screens, the address, a login of its own).
 *
 * This side keeps what the integration sent (state/kiosk, 0600: it holds the login's token) and hands it to the app
 * over loopback only (web.c GET /kiosk/config); the app tells by its polls whether it is in front, and the display
 * (display_screen.c) gives the screen to it while nothing of its own is to be shown.
 *
 * Every function: any thread; kiosk has its own lock and calls nothing that takes core_lock. */
#ifndef KIOSK_H
#define KIOSK_H
#include <stddef.h>

void  kiosk_load(void);                         /* at start: state/kiosk */
/* the integration's config, "key value" lines (token plain here: web.c unsealed it), checked and stored; 0 ok, else
 * err says what was refused */
int   kiosk_store(const char *text, char *err, size_t cap);
/* malloc'd JSON: the screens, the address, the default, the return; with_token for the app on loopback alone */
char *kiosk_json(int with_token, int enabled, size_t *len);
/* what a screen app draws itself in place of hassmic (docs/screen-apps.md "What an app takes over"): its poll's path
 * /front/draws (both, as before) or /front/draws/<list>, the list's words comma- or plus-separated */
#define KIOSK_DRAWS_WORDS 1             /* the request's words: what was heard and the reply */
#define KIOSK_DRAWS_RING  2             /* a ringing alarm or timer */
int   kiosk_draws_parse(const char *after_front);   /* the path after "/front": "", "/draws", "/draws/words,ring" */
/* the app asked for its config; front: its activity is resumed; draws: a KIOSK_DRAWS_* set */
void  kiosk_polled(int front, int draws);
/* what the app in front draws itself (0 unless the screen app is in front and said so) */
int   kiosk_draws(void);
/* the app started another one and lent it the screen (/kiosk/config/lent/<package>): hassmic's layer stays off for it
 * until the screen app polls /front or /back again; -1: not a package name */
int   kiosk_lent(const char *pkg);
/* 1: an app has the screen.  On an Echo with Android: any app the owner installed, by what Android says is in front
 * (its process's oom_score_adj is 0: no help from the app needed); elsewhere (the PC) the screen app by its polls (in
 * the last 20 s), or the app it lent the screen to */
int   kiosk_front(void);
/* the package in front, by /proc (out empty: none of the owner's apps, hassmic's own home or nothing); -1: not known
 * here (no Android) */
int   kiosk_in_front(char *out, size_t cap);
int   kiosk_configured(void);                   /* 1: at least one screen */
/* the display thread's, with the kiosk switched on: the app started when it is gone (no poll for 90 s; at most once a
 * minute); 1 when it is in front */
int   kiosk_tick(int enabled);
/* 1: the connection on fd (loopback) is the screen app's own: its uid owns the app's data folder */
int   kiosk_peer_ok(int fd);
/* the shell (hassmic's own kiosk app's service: the bar of apps over every app, its keyboard; tools/kiosk Shell.java):
 * 1 when the connection is that app's (whichever app is the screen app); its config: the screen app, the screens' names */
int   kiosk_shell_peer_ok(int fd);
/* the shell's watcher says which package's activity is in front (GET /kiosk/shell/front/<package>); believed for a
 * minute, ahead of /proc; -1: not a package name */
int   kiosk_shell_front(const char *pkg);
char *kiosk_shell_json(int enabled, size_t *len);
#endif
