# Screen apps: what the Echo Show's screen shows

hassmic owns the Echo Show's screen only for its own pictures: the start's status, the words of a request, a ringing
alarm, the clock. Everything else is a **screen app's**: an ordinary Android app that hassmic starts and gives the
screen to. hassmic ships one, the Java kiosk (`tools/kiosk`, `org.hassmic.kiosk`: web pages in a WebView, a switcher,
a keyboard). Anyone can write another and install it with `adb install`; the hassmic integration in Home Assistant
names which one the Echo uses (Configure › "Screen app": its package). A Flutter template that does what the Java
kiosk does lives at [Nt-f/hassmic-screen](https://github.com/Nt-f/hassmic-screen).

This is the whole contract between hassmic and a screen app.

## Being started

The app's main activity declares

```xml
<intent-filter>
    <action android:name="org.hassmic.action.SCREEN" />
    <category android:name="android.intent.category.DEFAULT" />
</intent-filter>
```

and hassmic starts it with `am start -a org.hassmic.action.SCREEN -c android.intent.category.DEFAULT <package>` once
"Home Assistant on the screen" is on and the Echo is linked to Home Assistant, and again whenever the app has not
asked for its config (below) for 90 seconds (it crashed, or was never started since the boot), at most once a minute.
It is not a home screen: Android 7 starts the home before the user is unlocked, when no WebView may run.
`singleTask` keeps one copy.

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
  "app": "org.hassmic.kiosk",
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

While the app polls `/front`, hassmic takes its own layer off the screen whenever it has nothing to show, and puts
it back over the app for a request's words, a ringing alarm (a tap snoozes it: the app sees that tap too) or the
status after Home Assistant went away. The app needs to do nothing for that.

## What the Echo lacks

- **No keyboard.** Fire OS's input method went with Amazon's apps; the Echo has none. A screen app that offers text
  fields brings its own on-screen keyboard (the Java kiosk types into its WebView with key events).
- **No navigation bar, no system UI.** The app is all there is: give a way between screens.
- **Memory.** The Echo Show 5 has 1 GB for Android, hassmic and the app; the Java kiosk with Home Assistant's
  login page takes 91 MB, a Flutter UI 62 MB (measured, 2026-11-02). One heavy page at a time.
- **GPU.** Mali-T720, OpenGL ES 3.1, no Vulkan: Flutter runs on Skia (GLES) at 60 fps; a full-screen live blur
  costs 25-43 fps.
- **Android 7.1 (API 25), 32-bit ARM only** (`armeabi-v7a`).

## Installing one

```sh
adb install my-screen.apk
```

then in Home Assistant: hassmic › Configure on the Echo › "Screen app": its package. The Java kiosk stays
installed and comes back when the field is empty.
