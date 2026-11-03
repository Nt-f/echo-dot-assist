# Home screens: the Echo Local panel, Echo-Wall's preview, import and export

Status: **built** (2026-11-02). Integration side in `custom_components/echo_local/` (`home.py`, `frontend/panel.js`,
`frontend/echowall/` = Echo-Wall built for the web by `tools/echowall-preview.sh`), app side in Echo-Wall
(`lib/home/layout_sync.dart`, `lib/preview.dart`, `lib/io/`). Tested by `tests/ha_real_home.py` (a real Home
Assistant, the panel and the preview in headless Chrome) and Echo-Wall's `test/layout_sync_test.dart`.

An Echo Show's screen has a *Home*: the page of widgets and tiles the screen comes back to. It is drawn by the screen
app (`docs/screen-apps.md`), which is **Echo-Wall** (Flutter, Nt-f/Echo-Wall, package `io.github.nt_f.echowall`).
Its layout (wallpaper, which tiles are on Home and in what order, what is hidden, each room's order, the clocks, where
each tile was dragged on its grid) is kept on the Echo in the app's file and, with this, in Home Assistant, where the
sidebar panel edits it.

The web wall panel of before (`frontend/wall.html` + `wall.js`, shown by hassmic's Java kiosk) is **gone**: Echo-Wall
replaced it. Its layouts were migrated into Echo-Wall's (below), and hassmic's Java kiosk now shows web pages only
(Home Assistant's dashboards, Music Assistant, a page of one's own).

What this adds:

1. **A sidebar entry, "Echo Local"** (`/echo-local`, administrators only): every Echo, its Home edited in a form
   beside **Echo-Wall itself**, running in the panel with this Home Assistant's devices, whose own edit mode (drag,
   ★, −) edits the draft; and the screen's options.
2. **One store for every screen app's Home** (`home.py`), a slot per Echo and app, followed live by the apps and the
   panel.
3. **Export and import**: a Home to a file and back; from another app by what they share; copied to other Echos.
4. **Apps take part over Home Assistant's websocket**, with the login they already have: Echo-Wall sends its layout as
   it changes and follows what the panel saves.

## The pieces

```
                   Home Assistant                                              Echo Show
 ┌───────────────────────────────────────────────────────┐        ┌────────────────────────────────┐
 │ sidebar "Echo Local"  (frontend/panel.js)             │        │ Echo-Wall (Flutter)            │
 │   Echos │ Home screen │ Screen                        │        │   WallView: Home, rooms        │
 │         │  form from the descriptor │ preview: an     │        │   layout.json (its file)       │
 │         │  Import ▾ Export Copy to ▾│ iframe of        │        │   layout_sync.dart             │
 │         │  Save Revert Reset        │ /echo_local/     │        │   the kiosk user's token       │
 │         │                           │ echowall/: the   │        │   (kiosk.py made it)           │
 │         │                           │ same WallView    │        │                                │
 │   admin's websocket                                   │        │                                │
 ├───────────────────────────────────────────────────────┤        │                                │
 │ home.py   echo_local/home/{list,get,set,subscribe,    │◄───────┤  HA's websocket, from the app  │
 │           describe,delete}  echo_local/kiosk/{get,set}│        │  (nothing through hassmic)     │
 │   Store "echo_local.wall" 2.2:                        │        └────────────────────────────────┘
 │     homes[echo][app] = {layout, updated, by}          │
 │     descriptors[echo | "*"][app]                      │
 │   BUILTIN descriptor: Echo-Wall (preview: echowall/)  │
 │ kiosk.py  entry options → hassmic /api/kiosk (sealed) │──── signed settings-page API ───► hassmic
 └───────────────────────────────────────────────────────┘
```

hassmic itself is not involved in layouts. The app reaches Home Assistant with the token `GET /kiosk/config` hands it
(`docs/screen-apps.md`); the Echo's signed settings-page API carries only the screen's options (`kiosk.py` `push`).

**Home in the screen list.** The kiosk options' screen kind `wall` (its id kept for saved options) is now "Home",
sent to the Echo as the URL `hassmic:home`: a screen the app draws itself, like `hassmic:clock`. Echo-Wall always
draws Home and leaves `hassmic:` screens out of its switcher; hassmic's Java kiosk skips them (web pages only).

## The store (`home.py`)

A Home Assistant `Store`, key `echo_local.wall` (the wall panel's of before), version 2.2:

```json
{
  "homes": {
    "echo-show-5-a1b2c3": {
      "io.github.nt_f.echowall": {"layout": {...}, "updated": 1793677390.02, "by": "app"},
      "org.example.screen":      {"layout": {...}, "updated": 1793677325.27, "by": "panel"}
    }
  },
  "descriptors": {
    "echo-show-5-a1b2c3": {"org.example.screen": {"name": "Example", "fields": [...]}},
    "*": {}
  }
}
```

- **A slot is (Echo, app).** The Echo is its node (`echo-show-5-5695c4`, the config entry's unique id); the app its
  Android package. At most 8 apps per Echo.
- **`by`** says who saved last: `panel` (an administrator), `app` (the Echo's own kiosk user), or `migrated`. The panel
  shows it ("Saved 2 min ago by the Echo").
- **Migrations** (`_Store._async_migrate_func`):
  - 1 (`wall.py`: `{"layouts": {echo: wall layout}}`) and 2.1 (this store with the web wall panel's slots under app
    `wall`): each Echo's wall layout becomes its Echo-Wall slot unless Echo-Wall already saved one there
    (`wall_to_echowall`: `theme` → `wallpaper`, `nowplaying` → `now_playing`; `favorites`, `hidden`, `order`, `ambient`
    as they are). The `default` slot (the wall panel opened in a browser without `?echo=`) is dropped.
- **Last writer wins**: the Echo's edit mode and the panel write the same slot. The panel does not overwrite blindly,
  though (below, "Conflicts").

## Descriptors: what a layout holds

An app says what its layout holds with a descriptor; the panel draws its form from it, `home.py` checks layouts by
it, and import between apps maps by it. Echo-Wall's is built in (`home.py` `BUILTIN`):

```json
{
  "name": "Echo-Wall",
  "about": "The Echo Show's Home (Nt-f/Echo-Wall). ...",
  "preview": "/echo_local/echowall/index.html",
  "fields": [
    {"key": "wallpaper", "type": "select", "label": "Wallpaper",
     "options": [["photo", "Photo (Immich)"], ["amber", "Amber"], ["dusk", "Dusk"], ["light", "Light"]],
     "default": "photo", "common": "theme"},
    {"key": "favorites", "type": "entities", "label": "Home's tiles", "ordered": true, "nullable": true, "common": "favorites"},
    {"key": "analog_clock", "type": "bool", "label": "Analog clock", "default": true},
    {"key": "digital_clock", "type": "bool", "label": "Digital clock", "default": true},
    {"key": "date_card", "type": "bool", "label": "Date", "default": true},
    {"key": "now_playing", "type": "bool", "label": "What plays, on Home", "default": true, "common": "nowplaying"},
    {"key": "ambient", "type": "number", "label": "Lock screen after untouched", "min": 0, "max": 86400, "unit": "s", "common": "ambient"},
    {"key": "hidden", "type": "entities", "label": "Hidden everywhere", "ordered": false, "common": "hidden"},
    {"key": "hidden_screens", "type": "strings", "label": "Screens off Home"},
    {"key": "order", "type": "area_order", "label": "Rooms", "common": "order"}
  ]
}
```

| type | value | the panel draws | `home.py` checks |
|---|---|---|---|
| `select` | one of `options` | segmented buttons (≤ 4), else a dropdown | the value is one of them |
| `number` | number | a number box with `unit` | `min`..`max` |
| `bool` | true/false | a switch | a boolean |
| `text` | string | a text box | ≤ 255 characters |
| `entity` | entity id (`none`: the word for none) | a picker filtered by `domain` | ≤ 255 characters |
| `entities` | list of ids; `null` if `nullable` ("the app picks") | a list: drag or ↑↓ to order (`ordered`), × to remove, a picker to add; with `nullable` a switch "The app picks" | ≤ 300 ids |
| `strings` | list of strings | chips | ≤ 300 |
| `area_order` | `{area id: [ids]}` | a fold-out per Home Assistant area with its tiles, drag to order, Reset per room | ≤ 200 areas |
| `dashboard` | a dashboard's url path, "" none | a list of Home Assistant's dashboards (and Overview) | ≤ 255 characters |

- **Keys a descriptor does not name are kept** as they come: Echo-Wall's `place` (where each tile was dragged on its
  grid, `{page group: {widget: [page, column, row]}}`), `home_order`, `player`, `sizes`, `cards`, `exclude`,
  `custom_pages`, `page_order` (below, "Your dashboard"). They are edited in the preview (dragging
  there writes `place`) or in the form's JSON box. The only limit on them is the slot's size, **64 KB** of JSON: the
  Echo's kiosk user writes slots and is not an administrator.
- **`common`** names what apps share: `theme`, `favorites`, `hidden`, `order`, `ambient`, `nowplaying`. It is how a Home
  moves between apps (below). A `select` maps only to a value the target offers.
- **`preview`**: a page of this Home Assistant that draws the Home with the panel's draft (below). Without one, the
  panel shows a sketch of Home's tiles from the `common` fields.
- **Where descriptors come from.** Built in: Echo-Wall's. Any other app sends its own with `echo_local/home/describe`
  (checked: ≤ 40 fields, keys `[a-z][a-z0-9_]*`, at most 32 apps per scope). Sent by an Echo's kiosk user it is kept
  **for that Echo only** (`descriptors[<node>]`); sent by an administrator, for every Echo (`descriptors["*"]`).
  Looked up in that order: built in, the Echo's own, the administrator's. So one Echo's login cannot change how another
  Echo's layouts are checked or edited, and no app can replace a built-in one. An app without a descriptor still gets
  Export, Import, Copy and a JSON editor.

## Who may touch which slot

| who | read | write | list, delete, describe for all, the screen's options |
|---|---|---|---|
| administrator (the panel) | any | any | yes |
| an Echo's kiosk user (`kiosk.py`, `DATA_USER` of its entry) | **its own Echo's**, whatever `echo` it names | the same | no (describe: for its Echo) |
| any other user | any | no | no |

The kiosk user is mapped to its Echo by `connection.user.id` against the entries' `DATA_USER`, so an app never needs to
know which Echo it runs on, and a token leaked from one Echo cannot rewrite another's Home.

## Websocket commands

All on Home Assistant's own websocket (`/api/websocket`). `echo` may be left out where the kiosk user asks (its own);
`app` defaults to Echo-Wall's package.

| command | fields | answer |
|---|---|---|
| `echo_local/home/list` | — | admin. `{echos: [{echo, title, entry_id, kiosk, app, screens, slots: {app: {updated, by}}, descriptors}], descriptors (built in + every Echo's), builtin, common, limits}` |
| `echo_local/home/get` | `echo?`, `app?` | the layout; `{}` if none (the app's own choice) |
| `echo_local/home/set` | `echo?`, `app?`, `layout` | the layout as stored (checked by the descriptor); every subscriber gets it |
| `echo_local/home/subscribe` | `echo?`, `app?` | result, then an event `{layout, echo}` now and at every change of that slot |
| `echo_local/home/describe` | `app`, `descriptor` | `{builtin: false}` stored (for the kiosk user's Echo, or every Echo from an administrator), `{builtin: true}` ignored |
| `echo_local/home/delete` | `echo`, `app` | admin. The slot gone: the app goes back to its own defaults |
| `echo_local/home/apps/set` | `echo?`, `apps: [{package, label, icon}]` | The Echo's Android apps as its screen app lists them (Echo-Wall's `Launchable.kt`; `icon` a base64 PNG, 64 dp; 40 at most), kept per Echo in the store. Echo-Wall sends them at each login and when they change (`layout_sync.dart` `publishApps`). Same rights as `set`: the kiosk user only its own Echo |
| `echo_local/home/apps/get` | `echo?` | `{apps, updated}`, `[]` until the app sent them. The panel's preview draws their tiles, its Apps tab shows their names and icons (hassmic's `/api/apps` knows packages and versions only) |
| `echo_local/kiosk/get` | `echo` | admin. `{options, kinds, music_panel, ha_url}` |
| `echo_local/kiosk/set` | `echo`, `options` | admin. Checked (`kiosk.py`'s keys and kinds), saved into the entry's options, the entry reloaded: its setup sends them on to the Echo as the options flow's Submit does |

App ids are package names (`^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z0-9_]+)+$`); `wall` and anything else is refused. The web
wall panel's `echo_local/wall/*` commands are gone.

## The sidebar panel (`frontend/panel.js`)

Registered by `__init__.py` `async_setup` through `panel_custom.async_register_panel` (`frontend_url_path`
`echo-local`, element `echo-local-panel`, module `/echo_local/panel.js`, icon `mdi:tablet-dashboard`,
`require_admin`). A plain custom element with a shadow root, no build step; it takes Home Assistant's theme through its
CSS variables and talks only over `hass.connection`.

**Left**: the Echos, each with "Screen on/off" and the apps that saved a Home there. On a phone (`narrow`) they become a
row of chips.

**Home screen tab**:

- **App chips**: Echo-Wall always; the screen app the Echo runs (its entry's `kiosk_app`) if another; any app with a
  slot there. A green dot: something saved; "· on the screen": the one the Echo shows now.
- **Bar**: Save (only with changes), Revert, the status ("Unsaved changes" / "Saved 2 min ago by the Echo"), Import ▾,
  Export, Copy to ▾, Reset.
- **Form**: one row per descriptor field, then "All of it, as JSON". Lists drag with the mouse and have ↑ ↓ for touch
  and keyboards. An entity not in this Home Assistant (from another one's export) shows in the warning colour and is
  kept.
- **Preview**: Echo-Wall itself, at the Echo's screen size in Flutter's logical pixels (Show 5: 960×470, the window
  above the light band at density 160; Show 8 1280×790; others 1024×590; picked from the Echo's name, changeable),
  scaled to the column. The switch "Edit on the screen" turns Echo-Wall's own edit mode on: drag a tile to another
  cell, ★ a room's tile onto Home, − to take one off, + Add, its wallpaper swatches; each change lands in the panel's
  draft and the form follows.

A draft change from the form redraws the form and the bar only (`refresh()`): the iframe stays, since an iframe
rebuilt or moved in the DOM loads again and Flutter would start over (2-3 s).

**Conflicts.** Each (Echo, app) the panel opens is subscribed. A change from elsewhere replaces the panel's copy only
while there is no unsaved draft; with one, a banner offers "Take the Echo's" or "Keep mine" (Keep mine: Save then
overwrites). So someone arranging tiles on the Echo while the owner edits in Home Assistant loses nothing silently.

**Apps tab** (Echo Shows; gone where the Echo answers `none`): the owner's Android apps (`apps.py`, the Echo's
`/api/apps`), an internet switch and Remove each, Add from this computer (uploaded to `/api/echo_local/apk/<echo>`,
then sent to the Echo in 256 kB pieces) or from a path Home Assistant may read; the status polled every second while
something runs.

**Screen tab**: the kiosk's options, as the options flow has them, with switches and a reorderable list of screens
(Home first by default); the screen app from a list (Echo-Wall, Echo-Screen, hassmic's kiosk for web pages only, or a
package typed in); its settings (`key=value` lines). Save goes through `echo_local/kiosk/set`. The options flow has
the same first page and no second one any more.

## Your dashboard, drawn natively (Echo-Wall's `lib/lovelace/`)

Asked 2026-11-03 after comparing it with Home Assistant's own UI on the Show (previews:
`build/lovelace-previews/`, made by its `shoot.py` against a demo Home Assistant): Echo-Wall draws a Home Assistant
dashboard itself, in its own glass, instead of Lovelace in a WebView. The layout field **`dashboard`** (the form's
"Dashboard after Home", a list of `lovelace/dashboards/list` plus Overview) names it by url path; empty is a page per
room, as before.

- **Pages.** Home stays Echo-Wall's own (the clocks, date and weather, the favourites, what plays, the screens and apps).
  After it, every section of every view of the dashboard is a page, its heading the page's name (the view's title
  beside it when the dashboard has several views); a section whose heading is an area's name gets that room's chips.
  Then the owner's own pages (edit mode's "+ Page"). `page_order` moves any of them.
- **Reading it.** `LovelaceSource` asks `lovelace/config {url_path}` over Echo-Wall's own websocket (the Echo's kiosk
  user reads any dashboard not limited to administrators) and again on the event `lovelace_updated` for that
  dashboard: a save in Home Assistant's editor shows on the Echo at once. A strategy dashboard (Overview never edited:
  Home Assistant makes it up as it draws) has no views to read: Echo-Wall then shows its room pages.
- **Cards.** tile, button, light, sensor, entity: Echo-Wall's tile. thermostat: its thermostat. media-control: its media
  card on that player (`Kind.media`). picture-entity / picture-glance of a camera: its camera card, live. entities,
  glance, weather-forecast: `NativeCard` (a glass list, a row of readings, the weather). Anything else (HACS cards,
  markdown, graphs) is a tile naming the card that opens that view in Home Assistant's own UI on the Echo
  (`WallView.onDashboard` → `main.dart` `_openPath`); drawing them would take a browser per card, which the Show 5
  cannot afford. Stacks are flattened: their cards become cards of the section.
- **Sizes.** Lovelace's `grid_options` (columns of 12, rows of 56 px) map to Echo-Wall's four sizes (`LCard.cardSize`:
  a half-width one-row tile small, a full-width one wide, three rows or more large, a whole section's worth extra
  large), never Lovelace's half-height strips. Each card then takes the nearest of its own sizes that fits the grid
  (`fitted`). The big cards are placed first, so a thermostat after four tiles still finds its two rows on the page.
- **The Echo's own changes, kept in Echo-Wall's layout, never written into the dashboard** (saving a dashboard needs an
  administrator, the Echo's login is not one, and the owner's dashboard stays as made): per page group
  (`ll:<view path or index>/<section heading or index>`), `place` (where each card was dragged), `sizes`, `exclude`
  (a card taken off this page here), `cards` (one added here: an entity, Echo-Wall's own clock, date, media, an app).
- **Performance.** The same widgets and glass as Echo-Wall's own pages (the wallpaper blurred once, each card copying
  its piece); the config a few kilobytes, read once and on each save; pages built as they are swiped to. No WebView:
  that is what the Show 5 cannot carry (Home Assistant's UI 150–250 MB against Echo-Wall's 62 MB).

**Holding a card** (`_Hold`, an iPhone's way): half a second shows its menu beside it (an overlay, not a route: a
route would cancel the finger still on the card): Controls, its sizes, Move to… (another page), Edit Home Screen,
Remove from this page. Held on to 1.3 s without moving: the edit mode. An empty place held, or the page dots: the edit
mode too. In the edit mode each card has − (off this page), ★ (on Home) and ⤡ (its next size) as 48 px targets, and a
tap shows its menu. The bar has + Add (to this page: devices, Echo-Wall's own cards, a dashboard card taken off
before), + Page, and on an own page Rename and Delete page.

**Thermostats** show what they do: orange heating, blue cooling (the card glows from below in that colour, its line
"Heating to 21°" white over it), "Idle", "Off" dimmed; a heat/cool (dual) one shows its range with the low end orange
and the high blue, "Cooling to 24°" naming the end it works towards, and its arrows move both ends.

**Every card at every size** (`lib/home/gallery.dart`): `test/gallery_test.dart` draws all of them at the Show 5's
cell and fails on any overflow (it found two: the wide media card's buttons, the wide dual thermostat's name);
`test/goldens/cards.png` is the picture, rewritten each run. The panel's preview shows the same gallery with the
Home Assistant's own devices ("Card sizes" under the preview).

## Echo-Wall's preview (`frontend/echowall/`, Echo-Wall's `lib/preview.dart`)

The preview is not a re-drawing of Echo-Wall: it is Echo-Wall's own `WallView`, compiled for the web.

**The build.** `tools/echowall-preview.sh [path to Echo-Wall]` runs `flutter build web -t lib/preview.dart --release
--base-href /echo_local/echowall/ --no-web-resources-cdn --pwa-strategy=none` there and copies what a browser loads
into `custom_components/echo_local/frontend/echowall/` (16 MB: `main.dart.js` 2.5 MB, CanvasKit 7 MB, Inter and the
stock photos 5 MB, licences 1.3 MB), with `BUILT_FROM` naming Echo-Wall's commit. CanvasKit is served by Home
Assistant (a Home Assistant may have no internet), only its build for every browser (Echo-Wall's
`web/flutter_bootstrap.js` asks for `canvasKitVariant: "full"`, so the Chromium-only copy and the wasm renderers stay
out), and no service worker (the page is Home Assistant's origin: nothing of ours should stay behind there). Rerun it
after a change to Echo-Wall's WallView and commit the result with the integration.

**One code base for both.** Echo-Wall's files import `lib/io/io.dart` instead of `dart:io`: on the Echo that is
`dart:io` itself (`io_native.dart`), on the web `io_web.dart`, stand-ins with the same names over the browser's
`fetch` and `WebSocket` (the few members the app uses: `HttpClient.getUrl/openUrl`, headers, `close()`, the response
as a byte stream; `WebSocket.connect/listen/add/close`; a `File` that never exists). Home Assistant is the page's own
origin, so its websocket, camera stills and streams work as on the Echo; Immich (another origin) only if it allows
CORS, else the stock photos, as when Immich is unreachable on the Echo. Method channels (Android's) fail on the web
and the app already treats them as optional.

**`lib/preview.dart`** is the web entry point: a `WallView` with `preview: true` (never the lock screen) and an
`editMode` notifier (the panel's switch; the bar's Done turns the switch back off). It takes from the panel, through
`window.parent.echoLocalPreview` (same origin):

| from | what | |
|---|---|---|
| `token()` | the panel's own access token (refreshed by `hass.auth` when expired) | asked again when Home Assistant refuses it |
| `layout()` | the draft to start with | |
| `info()` | `{h24, screens, settings, editing, gallery, apps}`: Home Assistant's clock format, the other screens' names (their tiles on Home), the edit switch, the card sizes switch, the Echo's Android apps (`echo_local/home/apps/get`) | |
| message `echo-local-apps` | those apps, when the panel has them after the preview started | |
| posts `echo-local-pages` | the pages after Home as the WallView made them, taken off ones too: `[{group, title, kind: own\|room\|dashboard, hidden}]` | the form's "Pages after Home": order (`page_order`), add, rename and delete one's own (`custom_pages`, its `cards`/`place`/`sizes` with it), take a room or dashboard section off and show it again (`hidden_pages`) |
| message `echo-local-layout` | a new draft (the form changed) | applied without being sent back |
| message `echo-local-editmode` | the switch | |
| posts `echo-local-edit` | the layout after an edit in the preview (Echo-Wall's own save, 500 ms after the last change) | the panel's draft |

Objects of the panel's frame are read through `JSON.stringify` (`dartify()` and `isA<JSObject>()` know only the
frame's own `Object`), and every message is checked against `location.origin`. The preview turns on Flutter's
semantics tree, so the browser's accessibility nodes name what is drawn (and the test finds the tiles by name).

## Export and import

**The file** (`<Echo>-<App>.echohome.json`):

```json
{
  "format": "echo-local-home",
  "version": 1,
  "app": "io.github.nt_f.echowall",
  "app_name": "Echo-Wall",
  "echo": "echo-show-5-a1b2c3",
  "echo_name": "Echo Show 5 a1b2c3",
  "exported": "2026-11-02T22:43:01.512Z",
  "layout": { "wallpaper": "light", "favorites": ["light.kitchen_lights"], "place": {"home": {"clock": [0, 0, 0]}} },
  "common": { "theme": "light", "favorites": ["light.kitchen_lights"] }
}
```

`layout` is the app's whole layout, its own keys included; `common` the shared part by common name, so that another
app can take it without knowing this one's descriptor.

**Import ▾**: **from a file** (`.echohome.json` up to 256 KB; the same app: its layout as it is; another: what both
share), **another app on this Echo**, or **another Echo**'s slot. Import fills the **draft** only; Save sends it.
Entities the file names that this Home Assistant lacks are counted in the message and kept.

**Between apps** (`take()` in panel.js, `home.from_common` in Python): the source's fields with a `common` name (and the
file's `common`) give the shared values; each target field with that `common` name gets the value, a `select` only if
the target offers it. Everything else of the target's draft stays (Echo-Wall's `place` included).

**Copy to ▾**: the draft saved as it is into the same app's slot on another Echo, or every other Echo. **Reset**: the
slot deleted; the app starts again from its own choice (Echo-Wall picks a thermostat, a camera, scenes, locks).

## Apps: taking part

A screen app with a Home of its own takes part with three commands on Home Assistant's websocket, logged in with the
token from `/kiosk/config`:

```
→ {"id": 7, "type": "echo_local/home/describe", "app": "org.example.screen", "descriptor": {...}}   (once, optional)
→ {"id": 8, "type": "echo_local/home/subscribe", "app": "org.example.screen"}
← {"id": 8, "type": "result", "success": true}
← {"id": 8, "type": "event", "event": {"layout": {...}, "echo": "echo-show-5-a1b2c3"}}           now, then at every save
→ {"id": 9, "type": "echo_local/home/set", "app": "org.example.screen", "layout": {...}}          after the app's own edits
```

No `echo`: Home Assistant knows the Echo from the token. Subscriptions end with the link, so subscribe again after
every login. Echo-Wall's `LayoutSync` (`lib/home/layout_sync.dart`) is the reference:

- **At each login**, subscribe. The first event is what Home Assistant has: empty → send ours (the first start with
  Echo Local); different from ours → take theirs (the panel saved while the app was not running), unless ours was
  changed since this start and never got through (then ours goes: the last change wins).
- **After each save of its own** (500 ms after the last change): send it, unless it is what just came in.
- **Each later event**: take it, draw it, write it to the file (`Layout.apply`) without sending it back.
- **Without Echo Local** (the command unknown) or Home Assistant: the app's file alone, as before.

An app that wants a real preview in the panel too names a page in its descriptor's `preview` that speaks the protocol
in the table above.

## What was decided and why

- **The preview is the app**, its WallView compiled for the web, not a second renderer in the panel: what the owner sees
  is what the Echo shows (the same packing on the same 960×470 logical pixels, the same glass), and Echo-Wall's own
  edit mode is the graphical editor, grid and all. The price: 16 MB in the integration, rebuilt with Echo-Wall.
- **The web wall panel removed** (asked 2026-11-02: "everything should've been switched to the Flutter UI"): two Homes
  to keep alike was one too many. Its layouts carry over into Echo-Wall's.
- **Home Assistant's websocket, not hassmic.** The app already has a Home Assistant token and a websocket to it. Going
  through hassmic would add a hop, a second store and a sync problem, for no gain in safety.
- **The user decides the Echo, not a parameter.** The kiosk user is per Echo (`kiosk.py`), so `connection.user` is a
  proof of which Echo is asking.
- **Descriptors instead of a fixed schema.** A fixed schema drops unknown keys and would throw away Echo-Wall's tile
  placement. A descriptor checks what it names and keeps the rest under a size cap; new apps need no integration
  release.
- **A draft and Save**, not saving each change as the Echo's edit mode does: the owner tries things against the preview
  and the Echo should not flicker through them.
- **One Store key kept** (`echo_local.wall`, now 2.2) so an update keeps every layout. A downgrade to a release with
  `wall.py` finds no `layouts` and its wall panels fall back to their own choice; the export file is the backup.

## Limits and open ends

- 64 KB a slot, 8 apps an Echo, 300 ids a list, 32 described apps per Echo.
- The preview's photos: Echo-Wall's stock ones (Immich only if it answers the browser with CORS headers). Cameras
  play what the browser can (HLS where the browser has it).
- Flutter's web engine asks fonts.gstatic.com for a fallback font for glyphs Inter lacks; offline it logs a warning and
  draws without it.
- No undo beyond Revert; the export file is the backup.
- The panel is administrators only, like the options it changes. Others arrange Home on the Echo itself (hold the
  page dots).
