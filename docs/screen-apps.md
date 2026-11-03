# Screen apps: what the Echo Show's screen shows

hassmic owns the Echo Show's screen only for its own pictures: the start's status, the words of a request, a ringing
alarm, the clock. Everything else is a **screen app's**: an Android app that hassmic starts and gives the screen to.
Any installed app can be it (a browser, Home Assistant's own app); an app made for hassmic speaks the contract below
and gets Home Assistant's address and a login from it. hassmic ships one, the Java kiosk (`tools/kiosk`,
`io.github.gamer92000.echodotassist.kiosk`: web pages in a WebView). Echo Local in Home Assistant names which app the
Echo uses (Echo Local in the sidebar › Screen › "App", or Configure › "Screen app": its package).

Whatever the screen app is, hassmic's **shell** runs beside it ("The shell" below): the bar of places pulled down from
the top edge over any app (Home, the screen app's screens, the apps you installed), the Echo's keyboard, and the watcher
that tells hassmic which app is in front.
The Echo Show's Home is [Nt-f/Echo-Wall](https://github.com/Nt-f/Echo-Wall)'s (Flutter); a template that does what the
Java kiosk does lives at [Nt-f/Echo-Screen](https://github.com/Nt-f/Echo-Screen).

This is the whole contract between hassmic and a screen app.

## Being started

The app's main activity declares

```xml
<intent-filter>
    <action android:name="io.github.gamer92000.echodotassist.action.SCREEN" />
    <category android:name="android.intent.category.DEFAULT" />
</intent-filter>
```

and hassmic starts it with `am start -a io.github.gamer92000.echodotassist.action.SCREEN -c android.intent.category.DEFAULT <package>` once
"Home Assistant on the screen" is on and the Echo is linked to Home Assistant, and again whenever no app has been in
front for 5 seconds (an app closed or crashed: the shell's watcher says so), at most every 15 s. An app without the
intent (any other app) is started as Android's launcher starts it (`monkey -p <package> -c
android.intent.category.LAUNCHER 1`): hassmic tries the intent first and remembers which way brought the app. Where
hassmic cannot tell what is in front (no watcher), it goes by the app's polls as before: started when it has not asked
for its config for 90 seconds, at most once a minute. It is not a home screen: Android 7 starts the home before the
user is unlocked, when no WebView may run. `singleTask` keeps one copy.

The shell starts it with the same intent and an extra: `screen` (a screen's name, from the bar) or `home` (true: the
bar's Home). An app that has several screens shows that one; others ignore the extras.

## The config, and telling hassmic it is in front

```
GET http://127.0.0.1:28931/kiosk/config/front    while the activity is resumed: every 5 s
GET http://127.0.0.1:28931/kiosk/config/back     once when it is paused, then every 30 s while paused
GET http://127.0.0.1:28931/kiosk/config          the config alone
```

hassmic answers only connections from 127.0.0.1 whose owner (the uid in `/proc/net/tcp6`) is the screen app's, the
owner of `/data/data/<package>`; anyone else gets a 404. No CORS headers: pages the app shows cannot read it.

```json
{
  "enabled": true,
  "ha": "http://192.168.1.211:8123",
  "has_token": true,
  "token": "<a long-lived access token>",
  "app": "io.github.gamer92000.echodotassist.kiosk",
  "default": 0,
  "return": 120,
  "screens": [
    {"name": "Home Assistant", "url": "http://192.168.1.211:8123/lovelace"},
    {"name": "Music", "url": "http://192.168.1.211:8123/d5369777_music_assistant"}
  ]
}
```

- `enabled`: false while "Home Assistant on the screen" or the screen itself is off: show nothing (black), free what
  can be freed (no WebView).
- `ha`, `token`: Home Assistant's address as the Echo reaches it (local addresses only: the Echo's firewall) and a
  long-lived token of a Home Assistant user made for this Echo by the integration (local only, not an administrator
  unless the owner chose so). For Home Assistant's own frontend, put it into the origin's `localStorage` as
  `hassTokens` (`{"access_token", "token_type": "Bearer", "expires_in", "hassUrl", "clientId", "expires": far
  future, "refresh_token": ""}`) before its first page; for the websocket API, `{"type": "auth", "access_token"}`.
- `screens`, `default`, `return`: what to offer, where to start, and after how many seconds untouched on another
  screen to go back to the default one (0: never).
- `settings`: the app's own, as the owner typed them into the integration's options ("Screen app settings", one
  `key=value` a line: keys of a-z 0-9 . _ -, 16 at most, values up to 400 characters), e.g. the HomeView's
  `immich.url`, `immich.key`, `immich.album`. They travel sealed with the token (secrets may be among them) and are
  only in this answer, never in the signed API's.

While the app polls `/front`, hassmic takes its own layer off the screen whenever it has nothing to show, and puts
it back over the app for a request's words, a ringing alarm (a tap snoozes it: the app sees that tap too) or the
status after Home Assistant went away. The app needs to do nothing for that.

## What an app takes over: the words, the alarms

An app that would rather draw these in its own look says so in the path it polls: `/kiosk/config/front/draws/<list>`,
the list comma- or plus-separated of `words` (what was heard and the reply) and `ring` (a ringing alarm or timer);
`/kiosk/config/front/draws` alone means both (the contract of before). Words not known yet are ignored, so an app may
name more. hassmic then leaves the screen to it for what it named (the start's status and Home
Assistant going away stay hassmic's: the app has nothing to show then). What to draw comes from

```
GET http://127.0.0.1:28931/kiosk/state           now
GET http://127.0.0.1:28931/kiosk/state/<v>       a long poll: answers once the version is not <v> any more, or after 25 s
```

(the same rule: 127.0.0.1 and the screen app's uid only)

```json
{
  "v": 42,
  "running": true,
  "words": true,
  "heard": "turn on the kitchen lights",
  "reply": "Turned on the kitchen lights.",
  "ringing": "Alarm 7:30 AM",
  "ringing_alarm": true,
  "h24": false,
  "clock_set": true,
  "next_alarm": {"at": 1793689800, "text": "Alarm 7:30 AM on weekdays", "label": "Gym"},
  "display": "always"
}
```

- `running`: a request is under way (listening, thinking, answering); `words`: show `heard` (what speech to text
  understood) and `reply` now (hassmic's "Show what you said and the reply" and "Words stay for" are applied).
- `ringing`: what rings, empty when nothing does; `ringing_alarm`: an alarm (snoozes) rather than a timer. Taps and
  long presses on the screen reach hassmic itself (it reads the touch screen beside Android): a tap snoozes an alarm
  or stops a timer, a press of 1.5 s stops, whoever draws the ring. Draw what stops it; do not act on it.
- `h24`, `next_alarm`, `clock_set` (the Echo's clock came from Home Assistant): for a clock of the app's own.

Screens whose `url` is `hassmic:<name>` are the app's to draw: `hassmic:home`, the app's own Home (the integration's
"Home" screen; Echo-Wall's WallView), and `hassmic:clock`, the clock as idle screen (the integration's "Clock"
screen). An app that cannot draw one leaves it out (hassmic's own kiosk does: it shows web pages only).

Being the **Home** is not a declaration: the screen app is the Home (the bar's first place, what comes back when no
app is in front). The idle **clock** is hassmic's only while no app has the screen at all (the screen app off, or
"Home Assistant on the screen" off); an app with a clock of its own (Echo-Wall's lock screen) just draws it.

## The shell

hassmic's kiosk app (`io.github.gamer92000.echodotassist.kiosk`) runs, beside whatever app is the screen app, in a
process of its own (`:shell`):

- **The bar** (`Shell.java`): an invisible strip over the middle of the top edge; a swipe down there opens the bar over
  any app: Home (the screen app), the screen app's web screens, then the apps the owner installed. A touch elsewhere,
  a swipe up or 8 s close it. hassmic starts it (`am startservice`) when it has not polled `GET /kiosk/shell` for a
  minute; that answer (`{enabled, app, front, contract, screens: [names]}`) goes to this app's uid only.
- **The watcher** (`Watcher.java`): an accessibility service that tells hassmic, `GET /kiosk/shell/front/<package>`,
  which app's activity comes to the front (and again every 20 s). hassmic believes it for a minute; it lets hassmic's
  clock and band keep out of any app's way and brings the screen app back when an app closes. Android 7 tells hassmic
  no other way (its `/proc` hides the others' processes: `hidepid=2`; with the group `readproc`, which hassmic has, it
  sees them, but which is in front is in `oom_score_adj`, 0400 on Fire OS 7; Fire OS keeps no usage statistics).
- **The keyboard** (`Keyboard.java`): an input method for every app (the Echo has none). The kiosk's own WebView keeps
  its keyboard of key events.

Root's `main.sh` (`screen_grants`) lets the app draw over others, switches the watcher and the keyboard on, and makes
the keyboard the one in use. A screen app needs none of this any more: no bar of its own, no keyboard, no permission.

## A Home of the app's own

The layout an app draws on its Home (tiles, a wallpaper, an order of rooms) is the app's own business: hassmic and Echo
Local only say which app shows the screen and give it Home Assistant's address and a login (the token above, a user
per Echo that is no administrator). Echo-Wall keeps its Home in Home Assistant through an integration of its own
(Nt-f/Echo-Wall, `custom_components/echo_wall`, its `docs/integration.md`): the app registers itself there with that
login, which binds the device to it, and follows its layout over Home Assistant's websocket. Another app can do the
same with its own integration, or keep its layout to itself.

## What the Echo lacks

- **No keyboard of Fire OS's.** Its input method went with Amazon's apps; the shell's keyboard stands in for every app.
- **No navigation bar, no system UI.** The shell's bar is the way between apps; an app with several screens of its own
  can offer them in the bar (its config's `screens`) or give a way between them itself.
- **Memory.** The Echo Show 5 has 1 GB for Android, hassmic and the app; the Java kiosk with Home Assistant's
  login page takes 91 MB, a Flutter UI 62 MB (measured, 2026-11-02). One heavy page at a time.
- **GPU.** Mali-T720, OpenGL ES 3.1, no Vulkan: Flutter runs on Skia (GLES) at 60 fps; a full-screen live blur
  costs 25-43 fps.
- **Android 7.1 (API 25), 32-bit ARM only** (`armeabi-v7a`).

## Installing one

```sh
adb install my-screen.apk
```

then in Home Assistant: the sidebar's Echo Local › the Echo › Screen › "App" (or Configure on the Echo › "Screen
app"): its package. The Java kiosk stays
installed and comes back when the field is empty.
