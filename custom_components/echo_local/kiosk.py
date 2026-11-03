"""The Echo Show's kiosk (src/hassmic/kiosk.c, tools/kiosk): what its screen shows, set up from here.

The integration's options (config_flow.py OptionsFlow, or the sidebar panel's Screen tab) pick the screens: Home
(hassmic:home, drawn by the screen app: Echo-Wall), the clock, a dashboard of Home Assistant's own UI, Music Assistant,
a page of one's own.  The Echo has no keyboard, so it gets a login of its own: a Home Assistant user
made for this Echo ("<Echo> kiosk", not an administrator unless the options say so) and a long-lived token of it, sealed
for the Echo on the way.  Removing the integration's entry removes that user."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.auth.const import GROUP_ID_ADMIN, GROUP_ID_USER
from homeassistant.auth.models import TOKEN_TYPE_LONG_LIVED_ACCESS_TOKEN
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.network import NoURLAvailableError, get_url

from .api import Echo, EchoError

_LOGGER = logging.getLogger(__name__)

OPT_KIOSK = "kiosk"                     # on: the Echo's display_kiosk setting on, the screens sent
OPT_SCREENS = "kiosk_screens"           # of SCREEN_KINDS, in this order
OPT_DASHBOARD = "kiosk_dashboard"       # url path of the dashboard ("lovelace" = Overview)
OPT_MUSIC = "kiosk_music"               # Music Assistant: a panel's url path or a whole address
OPT_CUSTOM_NAME = "kiosk_custom_name"
OPT_CUSTOM_URL = "kiosk_custom_url"
OPT_DEFAULT = "kiosk_default"           # the kind it starts on
OPT_RETURN = "kiosk_return"             # seconds untouched before going back to it (0 never)
OPT_ADMIN = "kiosk_admin"               # the kiosk's user an administrator (Home Assistant's settings on the Echo)
OPT_URL = "kiosk_ha_url"                # Home Assistant's address as the Echo reaches it; empty: get_url's
OPT_APP = "kiosk_app"                   # the screen app's package (docs/screen-apps.md); empty: hassmic's Java kiosk
OPT_APP_SETTINGS = "kiosk_app_settings"  # "key=value" lines for the screen app (an Immich address and key, ...)


def app_settings(text: str) -> dict[str, str]:
    """the options' "key=value" lines; blank lines and # comments left out"""
    out: dict[str, str] = {}
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip().lower()] = v.strip()
    return out

SCREEN_KINDS = ["clock", "wall", "dashboard", "music", "custom"]
DATA_USER, DATA_TOKEN = "kiosk_user", "kiosk_token"


def music_panel(hass: HomeAssistant) -> str:
    """the Music Assistant add-on's sidebar panel (ingress, "<slug>_music_assistant"), "" without one"""
    panels = hass.data.get("frontend_panels", {})
    for path, p in panels.items():
        title = (getattr(p, "sidebar_title", None) or "").lower()
        if "music_assistant" in path or title == "music assistant":
            return path
    return ""


def ha_url(hass: HomeAssistant, entry: ConfigEntry) -> str:
    u = (entry.options.get(OPT_URL) or "").strip().rstrip("/")
    if u:
        return u
    try:
        # the address the LAN reaches: the Echo's egress lock lets it reach local addresses only
        return get_url(hass, allow_external=False, allow_cloud=False, prefer_external=False).rstrip("/")
    except NoURLAvailableError:
        return get_url(hass).rstrip("/")


def screens(hass: HomeAssistant, entry: ConfigEntry) -> tuple[list[tuple[str, str]], int]:
    o, base = entry.options, ha_url(hass, entry)
    kinds = [k for k in SCREEN_KINDS if k in (o.get(OPT_SCREENS) or ["wall", "dashboard"])]
    out: list[tuple[str, str, str]] = []
    for k in kinds:
        if k == "clock":                # drawn by a screen app that can (docs/screen-apps.md); hassmic's own kiosk skips it
            out.append((k, "Clock", "hassmic:clock"))
        elif k == "wall":               # the screen app's own Home (Echo-Wall's WallView; home.py keeps its layout)
            out.append((k, "Home", "hassmic:home"))
        elif k == "dashboard":
            out.append((k, "Home Assistant", f"{base}/{(o.get(OPT_DASHBOARD) or 'lovelace').strip('/')}"))
        elif k == "music":
            m = (o.get(OPT_MUSIC) or music_panel(hass) or "").strip()
            if m:
                out.append((k, "Music", m if m.startswith(("http://", "https://")) else f"{base}/{m.strip('/')}"))
        elif k == "custom":
            u = (o.get(OPT_CUSTOM_URL) or "").strip()
            if u.startswith(("http://", "https://")):
                out.append((k, (o.get(OPT_CUSTOM_NAME) or "Page").strip()[:40], u))
    want = o.get(OPT_DEFAULT) or (kinds[0] if kinds else "wall")
    default = next((i for i, s in enumerate(out) if s[0] == want), 0)
    return [(n, u) for _, n, u in out], default


async def login(hass: HomeAssistant, entry: ConfigEntry) -> str:
    """the kiosk's user and token: made once, kept in the entry's data; a new token if the old one is gone"""
    admin = bool(entry.options.get(OPT_ADMIN))
    groups = [GROUP_ID_ADMIN if admin else GROUP_ID_USER]
    user = None
    if uid := entry.data.get(DATA_USER):
        user = await hass.auth.async_get_user(uid)
    if user is None:
        user = await hass.auth.async_create_user(f"{entry.title} kiosk", group_ids=groups, local_only=True)
        hass.config_entries.async_update_entry(entry, data={**entry.data, DATA_USER: user.id, DATA_TOKEN: ""})
    elif [g.id for g in user.groups] != groups:
        await hass.auth.async_update_user(user, group_ids=groups)
    token = entry.data.get(DATA_TOKEN) or ""
    if token and hass.auth.async_validate_access_token(token) is not None:
        return token
    for rt in list(user.refresh_tokens.values()):        # a token of an earlier setup: one at a time
        hass.auth.async_remove_refresh_token(rt)
    rt = await hass.auth.async_create_refresh_token(user, client_name=f"Echo Local kiosk ({entry.unique_id})",
                                                    token_type=TOKEN_TYPE_LONG_LIVED_ACCESS_TOKEN,
                                                    access_token_expiration=timedelta(days=3650))
    token = hass.auth.async_create_access_token(rt)
    hass.config_entries.async_update_entry(entry, data={**entry.data, DATA_TOKEN: token})
    return token


async def push(hass: HomeAssistant, entry: ConfigEntry, echo: Echo) -> None:
    """the options onto the Echo: its setting, then the screens"""
    o = entry.options
    if not o.get(OPT_KIOSK):
        await echo.set("display_kiosk=0\n")
        return
    scr, default = screens(hass, entry)
    if not scr:
        _LOGGER.warning("%s: the kiosk has no screen to show", entry.title)
    token = await login(hass, entry)
    try:
        await echo.put_kiosk(ha_url(hass, entry), scr, default, int(o.get(OPT_RETURN, 120)), token,
                             (o.get(OPT_APP) or "").strip(), app_settings(o.get(OPT_APP_SETTINGS, "")))
        await echo.set("display_kiosk=1\n")
    except EchoError as e:
        _LOGGER.warning("%s: the kiosk could not be set up: %s", entry.title, e)
        raise


async def remove(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """the entry is gone: so is its kiosk's user (and with it the token the Echo holds)"""
    if uid := entry.data.get(DATA_USER):
        if user := await hass.auth.async_get_user(uid):
            await hass.auth.async_remove_user(user)
