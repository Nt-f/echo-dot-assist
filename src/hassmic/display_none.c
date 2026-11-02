/* No screen (the Dots, the Echo Input, the PC build of a Dot): display.h's calls do nothing, its settings are not
 * listed (settings.c asks display_present) */
#include "display.h"
#include <limits.h>

const char *const display_modes[DISPLAY_MODES] = { "off", "awake", "always", "always_dim" };
int  display_setting(enum display_setting which, int set) { (void)which; (void)set; return 0; }
int  display_present(void) { return 0; }
void display_start(void) {}
void display_heard(const char *text) { (void)text; }
void display_reply(const char *text) { (void)text; }
void display_run(int active) { (void)active; }
void display_ringing(const char *what) { (void)what; }
void display_changed(void) {}
int  display_screen_timeout(int stock_ms) { return stock_ms; }
int  display_keeps_awake(void) { return 0; }
void display_link(int linked) { (void)linked; }
int  display_splash(const char *file) { (void)file; return 1; }
#include <stdio.h>
size_t   display_state_json(char *out, size_t cap) { return (size_t)snprintf(out, cap, "{\"v\":0}"); }
unsigned display_wait(unsigned since, int ms) { (void)since; (void)ms; return 0; }
