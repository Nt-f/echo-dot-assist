# Home screens: the Echo Local panel, layouts per app, import and export

Status: **built** (2026-11-02). Integration side in `custom_components/echo_local/` (`home.py`, `frontend/panel.js`,
the preview hooks in `frontend/wall.js`), app side in Echo-Wall (`lib/home/layout_sync.dart`), tested by
`tests/ha_real_home.py` (a real Home Assistant, headless Chrome) and Echo-Wall's `test/layout_sync_test.dart`.

An Echo Show's screen has a *Home*: the page of widgets and tiles the screen comes back to. Who draws it depends on the
screen app (`docs/screen-apps.md`): hassmic's Java kiosk shows the wall panel (`frontend/wall.html`), Echo-Wall draws
its own in Flutter, another app may draw another. Each Home has a layout (wallpaper, which tiles on Home and in what
order, what is hidden, each room's order, the idle clock, the app's own extras). Before this, the wall panel's layout
lived in Home Assistant (`wall.py`, one per Echo) and could be edited only on the Echo or through a form in the options
flow; Echo-Wall's lived only in a file on the Echo, out of Home Assistant's reach.

What this adds:

1. **A sidebar entry, "Echo Local"** (`/echo-local`, administrators only): every Echo, the Home of every app on it,
   edited graphically beside a live preview, and the screen's options (which screens, the screen app, its settings).
2. **One store for every app's Home** (`home.py`), a slot per Echo and app, followed live by the apps and the panel.
3. **Export and import**: a Home to a file and back; from one app into another by what they share; copied to other
   Echos.
4. **Apps take part over Home Assistant's websocket**, with the login they already have: Echo-Wall sends its layout as
   it changes and follows what the panel saves.

## The pieces

```
                   Home Assistant                                              Echo Show
 ┌───────────────────────────────────────────────────────┐        ┌────────────────────────────────┐
 │ sidebar "Echo Local"  (frontend/panel.js)             │        │ screen app                     │
 │   Echos │ Home screen │ Screen                        │        │  Java kiosk ─ WebView:         │
 │         │  form from the descriptor  │ preview        │        │     wall.html (app "wall")     │
 │         │  Import ▾ Export Copy to ▾ │ (wall.html in  │        │  Echo-Wall (Flutter):          │
 │         │  Save Revert Reset         │  an iframe)    │        │     layout.json + layout_sync  │
 │   admin's websocket                                   │        │  the kiosk user's token        │
 ├───────────────────────────────────────────────────────┤        │  (kiosk.py made it)            │
 │ home.py   echo_local/home/{list,get,set,subscribe,    │◄───────┤  HA's websocket, from the app  │
 │           describe,delete}  echo_local/kiosk/{get,set}│        │  (nothing through hassmic)     │
 │   Store "echo_local.wall" v2:                         │        └────────────────────────────────┘
 │     homes[echo][app] = {layout, updated, by}          │
 │     descriptors[app] (apps that described themselves) │
 │   BUILTIN descriptors: "wall", Echo-Wall              │
 │ kiosk.py  entry options → hassmic /api/kiosk (sealed) │──── signed settings-page API ───► hassmic
 └───────────────────────────────────────────────────────┘
```

hassmic itself is not involved in layouts. The app reaches Home Assistant with the token `GET /kiosk/config` hands it
(`docs/screen-apps.md`), exactly as the wall panel always has; the Echo's signed settings-page API carries only the
screen's options (`kiosk.py` `push`), as before.

## The store (`home.py`)

A Home Assistant `Store`, key `echo_local.wall` (the wall panel's of before), version 2:

```json
{
  "homes": {
    "echo-show-5-a1b2c3": {
      "wall":                    {"layout": {...}, "updated": 1793677325.27, "by": "panel"},
      "io.github.nt_f.echowall": {"layout": {...}, "updated": 1793677390.02, "by": "app"}
    },
    "default": {"wall": {"layout": {...}, "updated": 0, "by": "migrated"}}
  },
  "descriptors": {
    "echo-show-5-a1b2c3": {"org.example.screen": {"name": "Example", "fields": [...]}},
    "*": {}
  }
}
```

- **A slot is (Echo, app).** The Echo is its node (`echo-show-5-5695c4`, the config entry's unique id, the wall
  panel's `?echo=`); `default` is any browser that names none. The app is `wall` for the wall panel, else the screen
  app's Android package. At most 8 apps per Echo.
- **`by`** says who saved last: `panel` (an administrator), `app` (the Echo's own kiosk user), else that user's name.
  The panel shows it ("Saved 2 min ago by the Echo").
- **Version 1** (`{"layouts": {echo: layout}}`) is migrated on load by `_Store._async_migrate_func`: each layout
  becomes that Echo's `wall` slot, `by: "migrated"`. Nothing is lost on update.
- **Last writer wins**, as before: the Echo's edit mode, the panel and the options flow all write the same slot. The
  panel does not overwrite blindly, though (below, "Conflicts").

## Descriptors: what a layout holds

An app says what its layout holds with a descriptor; the panel draws its editor from it, `home.py` checks layouts by
it, and import between apps maps by it.

```json
{
  "name": "Echo-Wall",
  "about": "The Flutter screen app ...",
  "version": "1.4",
  "preview": "/echo_local/wall.html",
  "fields": [
    {"key": "wallpaper", "type": "select", "label": "Wallpaper",
     "options": [["photo", "Photo (Immich)"], ["amber", "Amber"], ["dusk", "Dusk"], ["light", "Light"]],
     "default": "photo", "common": "theme"},
    {"key": "favorites", "type": "entities", "label": "Home's tiles", "ordered": true, "nullable": true, "common": "favorites"},
    {"key": "ambient", "type": "number", "label": "Lock screen after untouched", "min": 0, "max": 86400, "step": 10, "unit": "s", "common": "ambient"},
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

- **Keys a descriptor does not name are kept** as they come (Echo-Wall's `place`, `home_order`, `player`): the app's own
  business. The only limit on them is the slot's size, **64 KB** of JSON: the Echo's kiosk user writes slots and is
  not an administrator.
- **`common`** names what apps share: `theme`, `favorites`, `hidden`, `order`, `ambient`, `nowplaying`. It is how a Home
  moves between apps (below). A `select` maps only to a value the target offers (Echo-Wall's `photo` wallpaper has no
  counterpart in the wall panel and is left out).
- **`preview`**: a page of this Home Assistant that draws the Home (`/echo_local/wall.html`). With it the panel shows
  the real thing; without it, a sketch of Home's tiles from the `common` fields.
- **Where descriptors come from.** `home.py` `BUILTIN` has the wall panel's and Echo-Wall's. Any other app sends its
  own with `echo_local/home/describe` (checked: ≤ 40 fields, keys `[a-z][a-z0-9_]*`, at most 32 apps per scope).
  Sent by an Echo's kiosk user, it is kept **for that Echo only** (`descriptors[<node>]`); sent by an administrator,
  for every Echo (`descriptors["*"]`). Looked up in that order: built in, the Echo's own, the administrator's. So one
  Echo's login cannot change how another Echo's layouts are checked or edited (a descriptor whose `select` offers
  nothing would otherwise refuse every other Echo's layout of that app), and no app can replace a built-in one. An
  app without a descriptor still gets Export, Import, Copy and a JSON editor.

## Who may touch which slot

| who | read | write | list, delete, the screen's options |
|---|---|---|---|
| administrator (the panel) | any | any | yes |
| an Echo's kiosk user (`kiosk.py`, `DATA_USER` of its entry) | **its own Echo's**, whatever `echo` it names | the same | no |
| any other user | any | `default` only | no |

The kiosk user is mapped to its Echo by `connection.user.id` against the entries' `DATA_USER`, so an app never needs to
know which Echo it runs on, and a token leaked from one Echo cannot rewrite another's Home. Before, any logged-in user
could write any Echo's wall layout; `tests/ha_real_home.py` checks the new rule.

## Websocket commands

All on Home Assistant's own websocket (`/api/websocket`). `echo` may be left out where the table says "own".

| command | fields | answer |
|---|---|---|
| `echo_local/home/list` | — | admin. `{echos: [{echo, title, entry_id, kiosk, app, screens, slots: {app: {updated, by}}, descriptors}], default: {...}, descriptors (built in + every Echo's), builtin, common, limits}` |
| `echo_local/home/get` | `echo?`, `app` (default `wall`) | the layout; the `default` slot's if the Echo has none; `{}` if neither |
| `echo_local/home/set` | `echo?`, `app`, `layout` | the layout as stored (checked by the descriptor); every subscriber gets it |
| `echo_local/home/subscribe` | `echo?`, `app` | result, then an event `{layout, echo}` now and at every change of that slot (or of `default`'s while the Echo has none) |
| `echo_local/home/describe` | `app`, `descriptor` | `{builtin: false}` stored (for the kiosk user's Echo, or every Echo from an administrator), `{builtin: true}` ignored |
| `echo_local/home/delete` | `echo`, `app` | admin. The slot gone: the app goes back to its own defaults |
| `echo_local/kiosk/get` | `echo` | admin. `{options, kinds, music_panel, ha_url}` |
| `echo_local/kiosk/set` | `echo`, `options` | admin. Checked (`kiosk.py`'s keys and kinds), saved into the entry's options, the entry reloaded: its setup sends them on to the Echo as the options flow's Submit does |
| `echo_local/wall/get\|set\|subscribe` | `echo?` (`layout`) | the old names: `home/*` with app `wall`, for a wall panel cached from before |

App ids are `wall` or a package name (`^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z0-9_]+)+$`); anything else is refused.

## The sidebar panel (`frontend/panel.js`)

Registered by `__init__.py` `async_setup` through `panel_custom.async_register_panel` (`frontend_url_path`
`echo-local`, element `echo-local-panel`, module `/echo_local/panel.js`, icon `mdi:tablet-dashboard`,
`require_admin`). A plain custom element with a shadow root, no build step, like the integration's other frontend
files; it takes Home Assistant's theme through its CSS variables (`--primary-color`, `--card-background-color`, ...)
and talks only over `hass.connection`.

**Left**: the Echos (each with "Screen on/off" and the apps that have a Home there), then "Any other browser"
(`default`). On a phone (`narrow`) they become a row of chips.

**Home screen tab**:

- **App chips**: the wall panel always; the screen app the Echo runs (its entry's `kiosk_app`); any app with a slot
  there. A green dot: something saved; "· on the screen": the one the Echo shows now.
- **Bar**: Save (only with changes), Revert, the status ("Unsaved changes" / "Saved 2 min ago by the Echo"), Import ▾,
  Export, Copy to ▾, Reset.
- **Form**: one row per descriptor field, then "All of it, as JSON" (also the whole editor for an app without a
  descriptor). Lists drag with the mouse (HTML5 drag and drop) and have ↑ ↓ for touch and keyboards. An entity not in
  this Home Assistant (from another one's export) shows in the warning colour, "not in this Home Assistant", and is
  kept.
- **Preview**, at the Echo's screen size (Show 5 960×470, Show 8 1280×790, others 1024×590: the WebView above the
  light band; picked from the Echo's name, changeable): for an app with `preview`, that page in a same-origin iframe
  with `?preview=1`; otherwise a sketch.

**Editing in the preview.** The wall panel in the iframe is the real one with the panel's draft, so its own edit mode
works there: the switch "Edit on the screen" turns it on, and a drag, ★ or − changes the draft in the panel (not Home
Assistant) and the form follows. The protocol (`wall.js`, all `postMessage` checked against `location.origin`):

| from | message | what it does |
|---|---|---|
| panel → preview | `{type: 'echo-local-layout', layout}` | draws the draft (after every change in the form) |
| panel → preview | `{type: 'echo-local-editmode', on}` | the wall panel's edit mode on/off |
| panel → preview | `{type: 'echo-local-page', name}` | scrolls to a page (a room) |
| preview → panel | `{type: 'echo-local-edit', layout}` | the edit mode changed the layout: the panel's draft |
| preview → panel | `parent.echoLocalPreview.token()` / `.layout()` | the login (the panel's own access token, refreshed when expired) and the draft at the start |

In preview mode `wall.js` neither subscribes to nor writes the store, and never goes to the big clock.

**Conflicts.** Each (Echo, app) the panel opens is subscribed. A change from elsewhere replaces the panel's copy only
while there is no unsaved draft; with one, a banner offers "Take the Echo's" or "Keep mine" (Keep mine: Save then
overwrites). So someone arranging tiles on the Echo while the owner edits in Home Assistant loses nothing silently.

**Screen tab** (an Echo only): the kiosk's options, as the options flow has them, with switches and a reorderable list
of screens; the screen app from a list (hassmic's kiosk, Echo-Wall, Echo-Screen, or a package typed in); its settings
(`key=value` lines). Save goes through `echo_local/kiosk/set`. The options flow stays as it was, its "wall" step a
short form of the same slot.

## Export and import

**The file** (`<Echo>-<App>.echohome.json`):

```json
{
  "format": "echo-local-home",
  "version": 1,
  "app": "wall",
  "app_name": "Wall panel",
  "echo": "echo-show-5-a1b2c3",
  "echo_name": "Echo Show 5 a1b2c3",
  "exported": "2026-11-02T22:43:01.512Z",
  "layout": { "theme": "light", "favorites": ["light.kitchen_lights"], "nowplaying": false },
  "common": { "theme": "light", "favorites": ["light.kitchen_lights"], "nowplaying": false }
}
```

`layout` is the app's whole layout, its own keys included; `common` the shared part by common name, so that a later
app can take it without knowing this one's descriptor.

**Import ▾** offers:

- **From a file…**: a `.echohome.json` up to 256 KB. The same app: its layout as it is. Another app: what both share.
- **Another app on this Echo**: e.g. Echo-Wall's Home into the wall panel's (both from the store).
- **Another Echo**: any app's slot on another Echo.

Import fills the **draft** only; Save sends it. Entities the file names that this Home Assistant lacks are counted in
the message and kept (a later rename back makes them show again).

**Between apps** (`take()` in panel.js, `home.from_common` in Python for the same rule): the source's fields with a
`common` name (and the file's `common`) give the shared values; each target field with that `common` name gets the
value, a `select` only if the target offers it. Everything else of the target's draft stays. Example from the test:
Echo-Wall's `{wallpaper: light, now_playing: false, favorites: [...], place: {...}}` into the wall panel gives
`{theme: light, nowplaying: false, favorites: [...]}`, and `place` (Echo-Wall's own) stays behind.

**Copy to ▾**: the draft saved as it is into the same app's slot on another Echo, or every other Echo.

**Reset**: the slot deleted; the app starts again from its own choice (the wall panel picks a thermostat, a camera,
scenes, locks).

## Apps: taking part

A screen app with a Home of its own takes part with three commands on Home Assistant's websocket, logged in with the
token from `/kiosk/config` (it already holds it):

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
- **After each save of its own** (Echo-Wall's 500 ms after the last change): send it, unless it is what just came in
  (`_agreed`), so a save from the panel does not bounce back.
- **Each later event**: take it, draw it, write it to the file (`Layout.apply`) without sending it back.
- **Without Echo Local** (the command unknown) or Home Assistant: the app's file alone, as before.

## What was decided and why

- **Home Assistant's websocket, not hassmic.** The app already has a Home Assistant token and a websocket to it; the
  wall panel always kept its layout this way. Going through hassmic (`/kiosk/...` on 127.0.0.1, then the signed API to
  Home Assistant) would add a hop, a second store and a sync problem, for no gain in safety: the token is the app's
  either way.
- **The user decides the Echo, not a parameter.** The kiosk user is per Echo (`kiosk.py`), so `connection.user` is a
  proof of which Echo is asking. Apps need no node, and one Echo cannot write another's slot.
- **Descriptors instead of a fixed schema.** `wall.py`'s schema dropped unknown keys (`REMOVE_EXTRA`), which would have
  thrown away Echo-Wall's tile placement. A descriptor checks what it names and keeps the rest under a size cap; new
  apps need no integration release.
- **A same-origin iframe for the preview**, the real `wall.html`, rather than a second renderer in the panel: what the
  owner sees is what the Echo shows, and the wall panel's edit mode (drag, ★, −) is the graphical editor for free.
- **A draft and Save**, not saving each change as the Echo's edit mode does: in the panel the owner tries things
  against the preview and the Echo should not flicker through them.
- **One Store key kept** (`echo_local.wall`, version 2 with a migration) rather than a new key, so an update keeps every
  layout. The price: a downgrade to a release with `wall.py` finds version 2 data with no `layouts` in it, and its wall
  panels fall back to their own choice. Accepted: downgrades are rare, and the export file is the backup.

## Limits and open ends

- 64 KB a slot, 8 apps an Echo, 300 ids a list, 32 described apps per Echo. A non-administrator writes slots; the caps keep a
  leaked kiosk token from filling Home Assistant's storage.
- The sketch preview for apps without a `preview` page is only that: Echo-Wall's real Home (photo wallpaper, analog
  clock, its placement grid) is not drawn in the panel. A web build of Echo-Wall's `WallView` could serve as its
  `preview` later.
- Echo-Wall's `place` (where each tile was dragged on its grid) is kept and copied but not editable in the form (the
  JSON editor can). Reordering favourites in the panel leaves `place` as it is; Echo-Wall packs what has no place.
- No undo beyond Revert; the export file is the backup.
- The panel is administrators only, like the options it changes. A non-administrator can still arrange the wall panel
  on the Echo or in a browser (the `default` slot).
