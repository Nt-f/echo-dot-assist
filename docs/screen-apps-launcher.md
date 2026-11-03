# Proposal: other Android apps beside the screen app (a launcher)

Status: **proposed, nothing built** (2026-11-02). Goal: install ordinary Android apps (a YouTube client, a music app)
on an Echo Show next to the screen app, have them appear in the template's switcher (Echo-Screen) and as cards on
Echo-Wall's Home automatically, open them with a tap and come back to the screen app afterwards.

Measured on the Show 5 (checkers, Fire OS 7, API 25), 2026-11-02:

| | |
|---|---|
| Google Play services | none (`pm list packages \| grep google`: 0) |
| Input methods | none (`ime list -a -s`: empty) |
| RAM | 998 MB, 190 MB free with hassmic + Echo-Wall resident |
| Home activity | `org.hassmic.home` (the pre-rename build: deploy the renamed APKs before testing) |

## What stands in the way today

1. **The egress lock drops them.** `scripts/device/lockdown.sh` `rules()`: only sockets carrying `NET_GID` (hassmic's
   own) may leave for non-local addresses; everything else ends at `-A hassmic_out -j DROP`. A sideloaded app draws
   its UI and fetches nothing. This is deliberate (Amazon's daemons stay local), so an app's way out has to be an
   explicit, per-package exception.
2. **hassmic takes the screen back when the screen app is paused.** The screen app polls `/kiosk/config/back` once
   another app is in front; `kiosk_polled(0)` clears `front_at`, `kiosk_front()` is 0, `display_screen.c` sets
   `to_kiosk` 0 and opens its own layer: hassmic's clock would be drawn over the app.
3. **No way back.** No navigation bar, no system UI, and the screen app cannot see touches on another app. The
   physical buttons are spoken for (action button, hold stages, Vol+/Vol- pairing).
4. **No keyboard.** The templates type into their own WebView with key events; other apps need an Android input
   method, and the Echo has none. A video client without search is of little use.
5. **No Google Play services.** YouTube's own app does not run. What does: GMS-free clients such as NewPipe or
   SmartTube (armeabi-v7a builds, minSdk at or below 25). "Apps like YouTube" means those.
6. **Memory.** 190 MB free. A video client with hardware decoding wants most of it; the screen app has to let go of
   what it holds while another app is in front, and may be killed by the low-memory killer anyway.
7. **The template ignores anything that is not a web page.** `ScreenConfig.parse` keeps only `http(s)://` and the
   `hassmic:` screens it draws; Echo-Wall's `_offered` filters further.

## The design

### Discovery: on the Echo, by the screen app

The screen app lists launchable apps itself: `PackageManager.queryIntentActivities(MAIN + LAUNCHER)` (API 25 has no
package visibility rules, so no `<queries>` needed), keeping only non-system packages (`FLAG_SYSTEM` clear) minus
itself and the Java kiosk. Label and icon (rendered to PNG bytes) go to Dart over the existing `echo_screen/keys`
MethodChannel (`apps` -> `[{package, label, icon}]`), refreshed on `ACTION_PACKAGE_ADDED/REMOVED`. Installing an
app is then all it takes for the card and the pill to appear: no Home Assistant round trip.

Starting one: `startActivity(getLaunchIntentForPackage(pkg))` with `FLAG_ACTIVITY_NEW_TASK`.

The integration may still name apps as screens, as `app:<package>` URLs (a new kind beside `hassmic:`), so that one can
be the default screen or be ordered among the web screens. Discovery does not depend on it.

### The contract: a "lent" state (hassmic, `kiosk.c`, `display_screen.c`)

```
GET /kiosk/config/lent/<package>    every 5 s while the app the screen app started is in front
```

The screen app knows it handed the screen over (it called `startActivity`), and its Dart timers keep running while
paused (it already polls `/back` that way). hassmic treats `lent` as front for the layer decision with `draws` 0: its
own layer stays off, but a ringing alarm and a request's words still come over the other app (hassmic draws them, as
for the Java kiosk). The package goes through the same charset check as `hassmic:` names (`kiosk.c` line 77).

When the screen app is back in front it polls `/front` again and `lent` ends. If the lent app is closed some other
way, the screen app's `onResume` ends it too.

### The way back (hassmic)

- **A gesture read by hassmic.** `display_screen.c` `touch_thread` already reads the panel's evdev beside Android
  (taps snooze, holds stop). Extended with `ABS_MT_POSITION_X/Y`: a pull down from the top edge (start in the top 5 %,
  move past 15 %) while lent -> `am start` the screen app's intent; `singleTask` brings the existing one to front. No
  permission, works with any app, and the pull mirrors the switcher's handle.
- **Return after untouched.** `return` seconds also apply while lent, timed by hassmic from the same touches. Off per
  app by default: a video plays untouched.
- **Alternative: an overlay handle** drawn by the screen app over the other app (`TYPE_PHONE` window; root grants
  `appops set <pkg> SYSTEM_ALERT_WINDOW allow`). Visible and discoverable, but it covers the app's own top edge and
  needs a service in the screen app. Not recommended as the first step.
- The action button could also mean "back" while lent, but it already answers Drop In and approves logins.

### Internet for an app (root, `lockdown.sh`, `main.sh`)

- The owner allows an app on the settings page (approved browser; a firewall hole is not something Home Assistant
  should be able to open by itself). hassmic writes `state/apps-net` (package names, `statefile_write`).
- Root resolves each to its uid from `/data/system/packages.list` (as `update_uid()` already does for the updaters)
  and `rules()` gains `-A hassmic_out -m owner --uid-owner <uid> -j RETURN` before the final DROP. `rules()` must stay a
  pure function of files on disk: `lockdown.sh check` compares `iptables -S hassmic_out` against it every 5-10 s.
- `main.sh`'s watcher reloads the rules when the file changes or a package is (re)installed (its uid can change).
- Amazon's own packages can never be named: root refuses packages under `/system` (code path from `packages.list`'s
  data dir / `pm path`), so the invariant "Amazon's daemons stay local" holds; apps the owner installed are the
  exception, one by one.

### Installing (later)

First `adb install`. Later: an APK uploaded on the settings page, staged like an artifact
(`state/artifacts/<stage>`), installed by root's watcher with `pm install` (32-bit, minSdk <= 25 checked first).

### The keyboard

The template's keyboard (`lib/keyboard.dart`) becomes, in the APK, an `InputMethodService` as well: same layout,
drawn natively (Flutter cannot be the IME window cheaply on 1 GB), enabled by root (`ime enable`,
`settings put secure default_input_method`). Without it only apps that need no typing are usable.

### Memory

While lent the screen app drops its WebView (the `_stop()` shape) and Echo-Wall its camera streams and photo
wallpaper. If the low-memory killer takes it anyway, the pull back starts it fresh (`am start`); Echo-Wall's layout
is already kept in Home Assistant (`wall.py`), so nothing is lost but a second.

## Where each part lives

| Repo | Changes |
|---|---|
| echo-dot-assist | `kiosk.c`: `lent` poll, `app:` screens, return timer while lent. `display_screen.c`: `to_kiosk` honours lent; touch positions and the edge pull. `web.c` + `web/app.js`: "Apps" card (installed apps, Internet toggle per app; later the APK upload). `lockdown.sh` + `main.sh`: per-uid allow from `state/apps-net`. `docs/screen-apps.md`: the contract's new parts. |
| Echo-Screen (template) | `MainActivity`: `apps`, `launch`, package broadcasts. `hassmic.dart`: `lent` polling, `app:` screens kept. `main.dart`: app pills after the web screens in the switcher (icon + label). Later the IME. |
| Echo-Wall | `Kind.app` cards with the app's icon, auto-added to Home from discovery, a `hiddenApps` set beside `hiddenScreens` (and in `+ Add`); let go of streams while lent. |
| Echo Local integration | Optional: `app:<package>` as a screen kind in the options flow. |

## Open choices

- Which apps first (decides the memory and network work: a video client vs. a music app).
- The keyboard now, or apps that need no typing first.
- Way back: hassmic's edge pull (recommended) or the screen app's overlay handle.
- Internet per app by the owner's toggle (recommended), or every app installed by adb allowed automatically.
