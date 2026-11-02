/* The kiosk: Home Assistant (or Music Assistant, or any page) on the Echo Show's screen, in hassmic's own app
 * (tools/kiosk/: org.hassmic.kiosk, a WebView on the firmware's Amazon WebView, Chromium 118), set up from Home
 * Assistant by the hassmic integration (custom_components/hassmic: the screens, the address, a login of its own).
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
void  kiosk_polled(int front);                  /* the app asked for its config; front: its activity is resumed */
int   kiosk_front(void);                        /* 1: the app is in front (a poll within the last 20 s) */
int   kiosk_configured(void);                   /* 1: at least one screen */
/* the display thread's, with the kiosk switched on: the app started when it is gone (no poll for 90 s; at most once a
 * minute); 1 when it is in front */
int   kiosk_tick(int enabled);
#endif
