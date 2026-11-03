"""The wall panel's layout (frontend/wall.js), kept in Home Assistant so that every screen showing it agrees: one per
Echo (its node, the panel's ?echo=), "default" for any other browser.  Set from the integration's options
(config_flow.py, the "Wall panel" step) or on the panel itself (its edit mode), read and followed by the panel over
Home Assistant's websocket:

    echo_local/wall/get        {echo}           the layout
    echo_local/wall/set        {echo, layout}   replaces it (checked: below); every panel following it gets it
    echo_local/wall/subscribe  {echo}           the layout now and at every change

Any logged-in user may read and set it: the Echo's kiosk user is not an administrator, and a layout only says which
tiles show where.  What it holds (all optional; missing = the panel's own choice):

    theme        amber | dusk | light
    ambient      seconds untouched before the big clock, 0 never
    nowplaying   false: no "now playing" on Home
    weather      the weather entity of the date widget ("none": no weather)
    favorites    Home's widgets and tiles, in order (a climate entity a big thermostat, a camera its picture); none
                 set: the thermostat, a camera, scenes and locks the panel picks
    hidden       entities shown nowhere
    order        {area id: [entities]}: a room page's tiles in this order, the rest after them"""
from __future__ import annotations

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send
from homeassistant.helpers.storage import Store

from .const import DOMAIN

STORE_KEY = "echo_local.wall"
SIGNAL = "echo_local_wall_changed"
DEFAULT = "default"
THEMES = ["amber", "dusk", "light"]
_ids = vol.All([vol.All(str, vol.Length(max=255))], vol.Length(max=300))

LAYOUT = vol.Schema({
    vol.Optional("theme"): vol.In(THEMES),
    vol.Optional("ambient"): vol.All(vol.Coerce(int), vol.Range(min=0, max=86400)),
    vol.Optional("nowplaying"): bool,
    vol.Optional("weather"): vol.All(str, vol.Length(max=255)),
    vol.Optional("favorites"): vol.Any(None, _ids),
    vol.Optional("hidden"): _ids,
    vol.Optional("order"): vol.All({vol.All(str, vol.Length(max=255)): _ids}, vol.Length(max=200)),
}, extra=vol.REMOVE_EXTRA)


def _data(hass: HomeAssistant) -> dict:
    return hass.data[DOMAIN + "_wall"]


def get(hass: HomeAssistant, echo: str | None) -> dict:
    """the Echo's layout, else the default one"""
    d = _data(hass)["layouts"]
    return dict(d.get(echo or DEFAULT) or d.get(DEFAULT) or {})


async def put(hass: HomeAssistant, echo: str | None, layout: dict) -> dict:
    layout = LAYOUT(layout)
    data = _data(hass)
    data["layouts"][echo or DEFAULT] = layout
    await data["store"].async_save({"layouts": data["layouts"]})
    async_dispatcher_send(hass, SIGNAL, echo or DEFAULT)
    return layout


async def async_setup(hass: HomeAssistant) -> None:
    store = Store(hass, 1, STORE_KEY)
    saved = await store.async_load() or {}
    hass.data[DOMAIN + "_wall"] = {"store": store, "layouts": saved.get("layouts", {})}
    websocket_api.async_register_command(hass, ws_get)
    websocket_api.async_register_command(hass, ws_set)
    websocket_api.async_register_command(hass, ws_subscribe)


@websocket_api.websocket_command({vol.Required("type"): "echo_local/wall/get", vol.Optional("echo", default=""): str})
@callback
def ws_get(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    connection.send_result(msg["id"], get(hass, msg["echo"]))


@websocket_api.websocket_command({vol.Required("type"): "echo_local/wall/set", vol.Optional("echo", default=""): str,
                                  vol.Required("layout"): dict})
@websocket_api.async_response
async def ws_set(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    try:
        layout = await put(hass, msg["echo"], msg["layout"])
    except vol.Invalid as e:
        connection.send_error(msg["id"], "invalid_format", str(e))
        return
    connection.send_result(msg["id"], layout)


@websocket_api.websocket_command({vol.Required("type"): "echo_local/wall/subscribe", vol.Optional("echo", default=""): str})
@callback
def ws_subscribe(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict) -> None:
    echo = msg["echo"] or DEFAULT

    @callback
    def changed(key: str) -> None:
        # the Echo's own changed, or the default it falls back to
        if key == echo or (key == DEFAULT and echo not in _data(hass)["layouts"]):
            connection.send_message(websocket_api.event_message(msg["id"], {"layout": get(hass, echo)}))

    connection.subscriptions[msg["id"]] = async_dispatcher_connect(hass, SIGNAL, changed)
    connection.send_result(msg["id"])
    connection.send_message(websocket_api.event_message(msg["id"], {"layout": get(hass, echo)}))
