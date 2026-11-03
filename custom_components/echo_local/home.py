"""Home screens: the layout of each screen app's Home on each Echo Show, kept in Home Assistant, edited in the sidebar
panel (frontend/panel.js), exported to a file and imported again.  docs/home-screens.md is the whole design.

One store for every app that draws a Home of its own: hassmic's wall panel (frontend/wall.js, app id "wall", shown by
the Java kiosk) and screen apps (docs/screen-apps.md; app id = their Android package, e.g. Echo-Wall's
io.github.nt_f.echowall).  A slot is (Echo node, app id); "default" is the Echo of any browser that names none.

Each app says what its layout holds with a *descriptor* (fields with a type, a label and the "common" name of what
apps share: favourites, hidden entities, room order, theme, idle clock, now playing).  Built in here for the wall
panel and Echo-Wall; any other app publishes its own over the websocket (echo_local/home/describe), so the panel draws
an editor for an app this integration has never heard of.  An app's own descriptor counts for its Echo only (one sent
by an administrator for every Echo): one Echo's login must not change how another Echo's layouts are checked.  Keys a descriptor does not name are the app's own (Echo-Wall's
"place": where each tile was dragged) and are kept as they come, within a size cap.

Websocket (Home Assistant's own, the token the kiosk already holds; the Echo's signed API is not involved):

    echo_local/home/list                                  admin: the Echos, their slots, the descriptors
    echo_local/home/get        {echo?, app}               the layout ({} none yet)
    echo_local/home/set        {echo?, app, layout}       replaces it (checked by the descriptor), told to every subscriber
    echo_local/home/subscribe  {echo?, app}               the layout now and at every change
    echo_local/home/describe   {app, descriptor}          an app's own descriptor, for its Echo (not the built-in ones')
    echo_local/home/delete     {echo, app}                admin: the slot gone (the app starts from its own defaults)
    echo_local/kiosk/get       {echo}                     admin: the screen's options (kiosk.py), for the panel
    echo_local/kiosk/set       {echo, options}            admin: the same, saved; the entry reloads and sends them on
    echo_local/wall/get|set|subscribe {echo}              the wall panel's old names = home/* with app "wall"

Who may touch which slot: an administrator any.  An Echo's kiosk user (kiosk.py makes one per Echo: not an
administrator, local only) only its own Echo's slots, whatever echo it names: the connection's user says which Echo it
is, so an app never needs to know its node.  Any other user reads, and writes "default" only."""
from __future__ import annotations

import json
import logging
import time
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send
from homeassistant.helpers.storage import Store

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STORE_KEY = "echo_local.wall"           # the wall panel's store of before; version 2 holds every app's
STORE_VERSION = 2
SIGNAL = "echo_local_home_changed"
DEFAULT = "default"
WALL = "wall"
MAX_LAYOUT = 64 * 1024                  # bytes of JSON a slot may hold (a kiosk user writes it: not an administrator)
MAX_APPS = 8                            # slots per Echo
MAX_IDS = 300                           # entity ids in one list
MAX_FIELDS = 40
FIELD_TYPES = ("select", "number", "bool", "text", "entities", "entity", "area_order", "strings")
# what apps share, so that a Home moves from one app to another (export of one, import into the other)
COMMON = ("theme", "favorites", "hidden", "order", "ambient", "nowplaying")

_opts = [["amber", "Amber"], ["dusk", "Dusk"], ["light", "Light"]]
BUILTIN: dict[str, dict] = {
    WALL: {
        "name": "Wall panel", "about": "hassmic's own Home (the Java kiosk's \"Home\" screen). Previewed here as it draws.",
        "preview": "/echo_local/wall.html",
        "fields": [
            {"key": "theme", "type": "select", "label": "Wallpaper", "options": _opts, "default": "amber", "common": "theme"},
            {"key": "favorites", "type": "entities", "label": "Home's tiles", "ordered": True, "nullable": True,
             "help": "In order. A thermostat shows big, a camera its picture. None: the panel picks.", "common": "favorites"},
            {"key": "weather", "type": "entity", "label": "Weather on the date", "domain": "weather", "none": "none"},
            {"key": "nowplaying", "type": "bool", "label": "What plays, on Home", "default": True, "common": "nowplaying"},
            {"key": "ambient", "type": "number", "label": "Big clock after untouched", "min": 0, "max": 86400, "step": 10,
             "unit": "s", "default": 120, "help": "0: never.", "common": "ambient"},
            {"key": "hidden", "type": "entities", "label": "Hidden everywhere", "ordered": False, "common": "hidden"},
            {"key": "order", "type": "area_order", "label": "Rooms", "help": "A room page's tiles in this order, the rest after them.",
             "common": "order"},
        ],
    },
    "io.github.nt_f.echowall": {
        "name": "Echo-Wall", "about": "The Flutter screen app (Nt-f/Echo-Wall). It sends its layout here as it changes and follows what is saved here.",
        "fields": [
            {"key": "wallpaper", "type": "select", "label": "Wallpaper",
             "options": [["photo", "Photo (Immich)"], *_opts], "default": "photo", "common": "theme"},
            {"key": "favorites", "type": "entities", "label": "Home's tiles", "ordered": True, "nullable": True, "common": "favorites"},
            {"key": "analog_clock", "type": "bool", "label": "Analog clock", "default": True},
            {"key": "digital_clock", "type": "bool", "label": "Digital clock", "default": True},
            {"key": "date_card", "type": "bool", "label": "Date", "default": True},
            {"key": "now_playing", "type": "bool", "label": "What plays, on Home", "default": True, "common": "nowplaying"},
            {"key": "ambient", "type": "number", "label": "Lock screen after untouched", "min": 0, "max": 86400, "step": 10,
             "unit": "s", "default": 120, "common": "ambient"},
            {"key": "hidden", "type": "entities", "label": "Hidden everywhere", "ordered": False, "common": "hidden"},
            {"key": "hidden_screens", "type": "strings", "label": "Screens off Home", "help": "The kiosk's screens, by name."},
            {"key": "order", "type": "area_order", "label": "Rooms", "common": "order"},
        ],
    },
}

_id = vol.All(str, vol.Length(max=255))
_ids = vol.All([_id], vol.Length(max=MAX_IDS))
FIELD = vol.Schema({
    vol.Required("key"): vol.All(str, vol.Match(r"^[a-z][a-z0-9_]{0,39}$")),
    vol.Required("type"): vol.In(FIELD_TYPES),
    vol.Optional("label"): vol.All(str, vol.Length(max=80)),
    vol.Optional("help"): vol.All(str, vol.Length(max=300)),
    vol.Optional("options"): vol.All([vol.All([vol.All(str, vol.Length(max=80))], vol.Length(min=2, max=2))], vol.Length(max=40)),
    vol.Optional("default"): vol.Any(str, int, float, bool, None),
    vol.Optional("min"): vol.Coerce(float), vol.Optional("max"): vol.Coerce(float), vol.Optional("step"): vol.Coerce(float),
    vol.Optional("unit"): vol.All(str, vol.Length(max=10)),
    vol.Optional("domain"): vol.All(str, vol.Length(max=40)),
    vol.Optional("none"): vol.All(str, vol.Length(max=40)),
    vol.Optional("ordered"): bool, vol.Optional("nullable"): bool,
    vol.Optional("common"): vol.In(COMMON),
}, extra=vol.REMOVE_EXTRA)
DESCRIPTOR = vol.Schema({
    vol.Required("name"): vol.All(str, vol.Length(min=1, max=60)),
    vol.Optional("about"): vol.All(str, vol.Length(max=400)),
    vol.Optional("version"): vol.All(str, vol.Length(max=40)),
    vol.Required("fields"): vol.All([FIELD], vol.Length(max=MAX_FIELDS)),
}, extra=vol.REMOVE_EXTRA)
APP = vol.All(str, vol.Match(r"^(wall|[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z0-9_]+)+)$"), vol.Length(max=120))


class _Store(Store):
    async def _async_migrate_func(self, old_major: int, old_minor: int, old: dict) -> dict:
        # 1: {"layouts": {echo: wall layout}} (wall.py)
        if old_major == 1:
            return {"homes": {e: {WALL: {"layout": l, "updated": 0, "by": "migrated"}} for e, l in (old.get("layouts") or {}).items()},
                    "descriptors": {}}
        return old


def _data(hass: HomeAssistant) -> dict:
    return hass.data[DOMAIN + "_home"]


ANY = "*"                               # descriptors an administrator sent: every Echo's


def descriptor(hass: HomeAssistant, app: str, echo: str | None = None) -> dict | None:
    """built in, else the one its app sent from this Echo, else an administrator's"""
    d = _data(hass)["descriptors"]
    return BUILTIN.get(app) or (d.get(echo or "") or {}).get(app) or (d.get(ANY) or {}).get(app)


def check(hass: HomeAssistant, app: str, layout: Any, echo: str | None = None) -> dict:
    """a layout as the app's descriptor has it: every field it names of its type, the rest kept within the size cap"""
    if not isinstance(layout, dict):
        raise vol.Invalid("a layout is an object")
    out = dict(layout)
    for f in (descriptor(hass, app, echo) or {}).get("fields", []):
        k, t = f["key"], f["type"]
        if k not in out:
            continue
        v = out[k]
        if t == "select":
            ok = [o[0] for o in f.get("options", [])]
            if v not in ok:
                raise vol.Invalid(f"{k}: one of {ok}")
        elif t == "number":
            v = vol.Coerce(float)(v)
            if ("min" in f and v < f["min"]) or ("max" in f and v > f["max"]):
                raise vol.Invalid(f"{k}: {f.get('min')}..{f.get('max')}")
            out[k] = int(v) if v == int(v) else v
        elif t == "bool":
            if not isinstance(v, bool):
                raise vol.Invalid(f"{k}: true or false")
        elif t in ("text", "entity"):
            out[k] = _id(v) if v is not None else None
        elif t in ("entities", "strings"):
            if v is None and f.get("nullable"):
                continue
            out[k] = _ids(v)
        elif t == "area_order":
            out[k] = vol.All({_id: _ids}, vol.Length(max=200))(v)
    if len(json.dumps(out, separators=(",", ":"))) > MAX_LAYOUT:
        raise vol.Invalid(f"a layout is {MAX_LAYOUT // 1024} KB at most")
    return out


def common(hass: HomeAssistant, app: str, layout: dict) -> dict:
    """the shared part of a layout, by its common names (an export carries it beside the app's own)"""
    out = {}
    for f in (descriptor(hass, app) or {}).get("fields", []):
        if f.get("common") and f["key"] in layout:
            out[f["common"]] = layout[f["key"]]
    return out


def from_common(hass: HomeAssistant, app: str, shared: dict) -> dict:
    """another app's Home in this one: what both have, a select only to a value this app offers"""
    out = {}
    for f in (descriptor(hass, app) or {}).get("fields", []):
        c = f.get("common")
        if not c or c not in shared:
            continue
        v = shared[c]
        if f["type"] == "select" and v not in [o[0] for o in f.get("options", [])]:
            continue
        out[f["key"]] = v
    return out


def get(hass: HomeAssistant, echo: str | None, app: str = WALL) -> dict:
    """the Echo's layout of that app, else the default one's"""
    h = _data(hass)["homes"]
    slot = (h.get(echo or DEFAULT) or {}).get(app) or (h.get(DEFAULT) or {}).get(app) or {}
    return dict(slot.get("layout") or {})


async def put(hass: HomeAssistant, echo: str | None, layout: dict, app: str = WALL, by: str = "") -> dict:
    layout = check(hass, app, layout, echo or DEFAULT)
    d = _data(hass)
    slots = d["homes"].setdefault(echo or DEFAULT, {})
    if app not in slots and len(slots) >= MAX_APPS:
        raise vol.Invalid(f"{MAX_APPS} apps a screen at most")
    slots[app] = {"layout": layout, "updated": time.time(), "by": by}
    await _save(hass)
    async_dispatcher_send(hass, SIGNAL, echo or DEFAULT, app)
    return layout


async def delete(hass: HomeAssistant, echo: str, app: str) -> None:
    d = _data(hass)
    if (d["homes"].get(echo) or {}).pop(app, None) is not None:
        await _save(hass)
        async_dispatcher_send(hass, SIGNAL, echo, app)


async def _save(hass: HomeAssistant) -> None:
    d = _data(hass)
    await d["store"].async_save({"homes": d["homes"], "descriptors": d["descriptors"]})


async def async_setup(hass: HomeAssistant) -> None:
    store = _Store(hass, STORE_VERSION, STORE_KEY)
    saved = await store.async_load() or {}
    hass.data[DOMAIN + "_home"] = {"store": store, "homes": saved.get("homes", {}), "descriptors": saved.get("descriptors", {})}
    for c in (ws_list, ws_get, ws_set, ws_subscribe, ws_describe, ws_delete, ws_kiosk_get, ws_kiosk_set,
              ws_wall_get, ws_wall_set, ws_wall_subscribe):
        websocket_api.async_register_command(hass, c)


# ---------------------------------------------------------------- who may touch which slot

def _entries(hass: HomeAssistant):
    return hass.config_entries.async_entries(DOMAIN)


def _own_echo(hass: HomeAssistant, user) -> str | None:
    """the Echo whose kiosk user this is (kiosk.py DATA_USER), else None"""
    from .kiosk import DATA_USER
    return next((e.unique_id for e in _entries(hass) if user and e.data.get(DATA_USER) == user.id), None)


def _slot(hass: HomeAssistant, connection, echo: str, write: bool) -> str:
    """the Echo this connection may read or write; raises Unauthorized"""
    user = connection.user
    if user.is_admin:
        return echo or DEFAULT
    own = _own_echo(hass, user)
    if own:
        return own                      # its own, whatever it named
    if write and (echo or DEFAULT) != DEFAULT:
        raise websocket_api.Unauthorized()
    return echo or DEFAULT


def _by(hass: HomeAssistant, connection) -> str:
    """who saved a slot, for the panel ("panel", "app": the Echo's own kiosk user, else the user's name)"""
    u = connection.user
    return "panel" if u.is_admin else "app" if _own_echo(hass, u) else (u.name or "user")


# ---------------------------------------------------------------- commands

@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): "echo_local/home/list"})
@callback
def ws_list(hass: HomeAssistant, connection, msg: dict) -> None:
    from . import kiosk
    homes, out = _data(hass)["homes"], []
    for e in _entries(hass):
        node = e.unique_id or ""
        out.append({"echo": node, "title": e.title, "entry_id": e.entry_id, "kiosk": bool(e.options.get(kiosk.OPT_KIOSK)),
                    "app": (e.options.get(kiosk.OPT_APP) or "").strip(), "screens": e.options.get(kiosk.OPT_SCREENS) or ["wall", "dashboard"],
                    "slots": {a: {"updated": s.get("updated", 0), "by": s.get("by", "")} for a, s in (homes.get(node) or {}).items()},
                    "descriptors": _data(hass)["descriptors"].get(node, {})})
    connection.send_result(msg["id"], {
        "echos": out,
        "default": {a: {"updated": s.get("updated", 0), "by": s.get("by", "")} for a, s in (homes.get(DEFAULT) or {}).items()},
        "descriptors": {**_data(hass)["descriptors"].get(ANY, {}), **BUILTIN}, "builtin": list(BUILTIN), "common": list(COMMON),
        "limits": {"layout": MAX_LAYOUT, "apps": MAX_APPS, "ids": MAX_IDS}})


_slotkeys = {vol.Optional("echo", default=""): str, vol.Optional("app", default=WALL): APP}


@websocket_api.websocket_command({vol.Required("type"): "echo_local/home/get", **_slotkeys})
@callback
def ws_get(hass: HomeAssistant, connection, msg: dict) -> None:
    connection.send_result(msg["id"], get(hass, _slot(hass, connection, msg["echo"], False), msg["app"]))


async def _set(hass, connection, msg, app):
    echo = _slot(hass, connection, msg["echo"], True)
    try:
        layout = await put(hass, echo, msg["layout"], app, _by(hass, connection))
    except vol.Invalid as e:
        connection.send_error(msg["id"], "invalid_format", str(e))
        return
    connection.send_result(msg["id"], layout)


@websocket_api.websocket_command({vol.Required("type"): "echo_local/home/set", **_slotkeys, vol.Required("layout"): dict})
@websocket_api.async_response
async def ws_set(hass: HomeAssistant, connection, msg: dict) -> None:
    await _set(hass, connection, msg, msg["app"])


def _subscribe(hass, connection, msg, app):
    echo = _slot(hass, connection, msg["echo"], False)
    homes = _data(hass)["homes"]

    @callback
    def changed(key: str, which: str) -> None:
        # this app's layout on the Echo changed, or the default one it falls back to
        if which == app and (key == echo or (key == DEFAULT and app not in (homes.get(echo) or {}))):
            connection.send_message(websocket_api.event_message(msg["id"], {"layout": get(hass, echo, app), "echo": echo}))

    connection.subscriptions[msg["id"]] = async_dispatcher_connect(hass, SIGNAL, changed)
    connection.send_result(msg["id"])
    connection.send_message(websocket_api.event_message(msg["id"], {"layout": get(hass, echo, app), "echo": echo}))


@websocket_api.websocket_command({vol.Required("type"): "echo_local/home/subscribe", **_slotkeys})
@callback
def ws_subscribe(hass: HomeAssistant, connection, msg: dict) -> None:
    _subscribe(hass, connection, msg, msg["app"])


@websocket_api.websocket_command({vol.Required("type"): "echo_local/home/describe", vol.Required("app"): APP, vol.Required("descriptor"): dict})
@websocket_api.async_response
async def ws_describe(hass: HomeAssistant, connection, msg: dict) -> None:
    if msg["app"] in BUILTIN:           # those are this integration's: an app on one Echo does not change them for all
        connection.send_result(msg["id"], {"builtin": True})
        return
    scope = ANY if connection.user.is_admin else _own_echo(hass, connection.user)
    if not scope:
        raise websocket_api.Unauthorized()
    try:
        d = DESCRIPTOR(msg["descriptor"])
    except vol.Invalid as e:
        connection.send_error(msg["id"], "invalid_format", str(e))
        return
    descs = _data(hass)["descriptors"].setdefault(scope, {})
    if descs.get(msg["app"]) != d:
        if msg["app"] not in descs and len(descs) >= 32:
            connection.send_error(msg["id"], "invalid_format", "too many apps described")
            return
        descs[msg["app"]] = d
        await _save(hass)
    connection.send_result(msg["id"], {"builtin": False})


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): "echo_local/home/delete", vol.Required("echo"): str, vol.Required("app"): APP})
@websocket_api.async_response
async def ws_delete(hass: HomeAssistant, connection, msg: dict) -> None:
    await delete(hass, msg["echo"] or DEFAULT, msg["app"])
    connection.send_result(msg["id"])


# ---------------------------------------------------------------- the screen's options (kiosk.py), for the panel

def _kiosk_schema():
    from . import kiosk as k
    return vol.Schema({
        vol.Optional(k.OPT_KIOSK): bool,
        vol.Optional(k.OPT_SCREENS): vol.All([vol.In(k.SCREEN_KINDS)], vol.Length(max=len(k.SCREEN_KINDS))),
        vol.Optional(k.OPT_DEFAULT): vol.In(k.SCREEN_KINDS),
        vol.Optional(k.OPT_DASHBOARD): vol.All(str, vol.Length(max=200)),
        vol.Optional(k.OPT_MUSIC): vol.All(str, vol.Length(max=400)),
        vol.Optional(k.OPT_CUSTOM_NAME): vol.All(str, vol.Length(max=40)),
        vol.Optional(k.OPT_CUSTOM_URL): vol.All(str, vol.Length(max=400)),
        vol.Optional(k.OPT_RETURN): vol.All(vol.Coerce(int), vol.Range(min=0, max=3600)),
        vol.Optional(k.OPT_ADMIN): bool,
        vol.Optional(k.OPT_URL): vol.All(str, vol.Length(max=400)),
        vol.Optional(k.OPT_APP): vol.All(str, vol.Match(r"^([a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z0-9_]+)+)?$"), vol.Length(max=120)),
        vol.Optional(k.OPT_APP_SETTINGS): vol.All(str, vol.Length(max=8000)),
    })


def _entry(hass, echo):
    return next((e for e in _entries(hass) if e.unique_id == echo), None)


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): "echo_local/kiosk/get", vol.Required("echo"): str})
@callback
def ws_kiosk_get(hass: HomeAssistant, connection, msg: dict) -> None:
    from . import kiosk as k
    e = _entry(hass, msg["echo"])
    if e is None:
        connection.send_error(msg["id"], "not_found", "no such Echo")
        return
    connection.send_result(msg["id"], {"options": dict(e.options), "kinds": k.SCREEN_KINDS, "music_panel": k.music_panel(hass),
                                       "ha_url": k.ha_url(hass, e)})


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): "echo_local/kiosk/set", vol.Required("echo"): str, vol.Required("options"): dict})
@websocket_api.async_response
async def ws_kiosk_set(hass: HomeAssistant, connection, msg: dict) -> None:
    e = _entry(hass, msg["echo"])
    if e is None:
        connection.send_error(msg["id"], "not_found", "no such Echo")
        return
    try:
        new = _kiosk_schema()(msg["options"])
    except vol.Invalid as err:
        connection.send_error(msg["id"], "invalid_format", str(err))
        return
    hass.config_entries.async_update_entry(e, options={**e.options, **new})
    # as the options flow's Submit (OptionsFlowWithReload): the setup sends it all to the Echo
    hass.config_entries.async_schedule_reload(e.entry_id)
    connection.send_result(msg["id"], {"options": dict(e.options)})


# ---------------------------------------------------------------- the wall panel's old names (a page cached from before)

@websocket_api.websocket_command({vol.Required("type"): "echo_local/wall/get", vol.Optional("echo", default=""): str})
@callback
def ws_wall_get(hass: HomeAssistant, connection, msg: dict) -> None:
    connection.send_result(msg["id"], get(hass, _slot(hass, connection, msg["echo"], False), WALL))


@websocket_api.websocket_command({vol.Required("type"): "echo_local/wall/set", vol.Optional("echo", default=""): str, vol.Required("layout"): dict})
@websocket_api.async_response
async def ws_wall_set(hass: HomeAssistant, connection, msg: dict) -> None:
    await _set(hass, connection, msg, WALL)


@websocket_api.websocket_command({vol.Required("type"): "echo_local/wall/subscribe", vol.Optional("echo", default=""): str})
@callback
def ws_wall_subscribe(hass: HomeAssistant, connection, msg: dict) -> None:
    _subscribe(hass, connection, msg, WALL)
