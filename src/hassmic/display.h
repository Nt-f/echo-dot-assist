/* The screen's own picture on models with one (display_screen.c; display_none.c elsewhere, picked in device.mk as the
 * ring is): a clock with the date and the next alarm, what was said and what the assistant answered, a ringing alarm
 * or timer.  Above the light band, on a layer of its own drawn by ringbar.dex in its "screen" mode.
 *
 * Every function: any thread, core_lock held or not.  The display has its own lock and calls nothing of the core's
 * that takes core_lock. */
#ifndef DISPLAY_H
#define DISPLAY_H
#include <stddef.h>

/* what the screen does: off (black, as before), awake (the clock while the screen is on; it sleeps as stock's does),
 * always (never sleeps), always_dim (never sleeps, dimmed at night) */
enum { DISPLAY_OFF, DISPLAY_AWAKE, DISPLAY_ALWAYS, DISPLAY_DIM, DISPLAY_MODES };
extern const char *const display_modes[DISPLAY_MODES];

/* the settings it keeps (settings.c reads and sets them through display_setting) */
enum display_setting { DS_MODE, DS_TEXT, DS_TEXT_S, DS_BRIGHT, DS_NIGHT_BRIGHT, DS_NIGHT_START, DS_NIGHT_END, DS_DARK_ROOM,
                       DS_KIOSK,       /* 1: the kiosk app (kiosk.h) has the screen while nothing of ours is to show */
                       DS_COUNT };
int  display_setting(enum display_setting which, int set);     /* set < 0 (INT_MIN for none): reads */

int  display_present(void);                     /* 1: a screen to draw on */
void display_start(void);                       /* after settings_load: the renderer, the touch reader */
void display_heard(const char *text);           /* what speech to text understood ("" clears) */
void display_reply(const char *text);           /* what the assistant answered */
void display_run(int active);                   /* a request runs (1) or is over (0): its words stay a while after */
void display_ringing(const char *what);         /* an alarm or timer rings ("Alarm 7:30 AM", "Pasta"); NULL: none */
void display_changed(void);                     /* alarms, the clock's format, a setting: draw again */
/* Home Assistant's link (core_link): until the first, and while it is down, the screen says what the Echo waits for
 * (the boot's status), whatever the display setting; the kiosk only once it is up */
void display_link(int linked);
/* hassmic -Y: the boot's status before hassmic runs (main.sh satellite's ~20 s of stopping Amazon's services): the
 * text of `file` (one line, rewritten by main.sh) on the screen until the real display takes the screen (it ends this
 * process through state/splash.pid) or 180 s.  0 when it showed anything */
int  display_splash(const char *file);
/* ring_band.c: the screen_off_timeout the band's power policy is to set, given stock's for now (ms) */
int  display_screen_timeout(int stock_ms);
int  display_keeps_awake(void);
/* what the screen shows, for a screen app that draws it itself (web.c GET /kiosk/state): JSON, "v" its version */
size_t   display_state_json(char *out, size_t cap);
unsigned display_wait(unsigned since, int ms);  /* until the version is not `since` any more, or ms: the version */                 /* 1: the screen must not sleep now (always on, or something rings) */
#endif
