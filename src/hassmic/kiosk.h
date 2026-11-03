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
/* the app asked for its config; front: its activity is resumed; draws: it draws the request's words and a ring itself
 * (its poll's path says so, docs/screen-apps.md) */
void  kiosk_polled(int front, int draws);
int   kiosk_draws(void);
int   kiosk_front(void);                        /* 1: the app is in front (a poll within the last 20 s) */
int   kiosk_configured(void);                   /* 1: at least one screen */
/* the display thread's, with the kiosk switched on: the app started when it is gone (no poll for 90 s; at most once a
 * minute); 1 when it is in front */
int   kiosk_tick(int enabled);
/* 1: the connection on fd (loopback) is the screen app's own: its uid owns the app's data folder */
int   kiosk_peer_ok(int fd);
#endif
