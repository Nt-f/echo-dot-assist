"""Adding an Echo: its address (or found on the network: the ESPHome mDNS hassmic announces says platform=hassmic), then
one press of its action button lets Home Assistant in, as a browser is let into its settings page."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlowWithReload
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .api import DEFAULT_PORT, Echo, EchoError, new_key
from . import kiosk as k, wall
from .const import CONF_KEY, CONF_MAC, CONF_NODE, DOMAIN

_LOGGER = logging.getLogger(__name__)


class HassmicConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> HassmicOptionsFlow:
        return HassmicOptionsFlow()

    def __init__(self) -> None:
        self.host: str | None = None
        self.port = DEFAULT_PORT
        self.key = new_key()
        self.hello: dict = {}
        self.asked = False

    def _echo(self) -> Echo:
        return Echo(async_get_clientsession(self.hass), self.host, self.port, self.key)

    async def _identify(self) -> None:
        """hello: who it is; one config entry per Echo, by its node (echo-show-5-5695c4)"""
        self.hello = await self._echo().get_hello()
        await self.async_set_unique_id(self.hello["node"])

    def _button(self) -> str:
        return "both volume keys together" if self.hello.get("action") == "volume_keys" else "the action button (the dot)"

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self.host, self.port = user_input[CONF_HOST].strip(), user_input.get(CONF_PORT, DEFAULT_PORT)
            try:
                await self._identify()
            except EchoError:
                errors["base"] = "cannot_connect"
            else:
                self._abort_if_unique_id_configured(updates={CONF_HOST: self.host, CONF_PORT: self.port})
                return await self.async_step_approve()
        return self.async_show_form(step_id="user", errors=errors, data_schema=vol.Schema({
            vol.Required(CONF_HOST, default=self.host or ""): str,
            vol.Optional(CONF_PORT, default=self.port): int}))

    async def async_step_zeroconf(self, discovery_info: ZeroconfServiceInfo) -> ConfigFlowResult:
        if (discovery_info.properties.get("platform") or "").lower() != "hassmic":
            return self.async_abort(reason="not_hassmic")
        self.host = str(discovery_info.ip_address)
        try:
            await self._identify()
        except EchoError:
            return self.async_abort(reason="cannot_connect")
        self._abort_if_unique_id_configured(updates={CONF_HOST: self.host})
        self.context["title_placeholders"] = {"name": self.hello.get("name", self.host)}
        return await self.async_step_confirm()

    async def async_step_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return await self.async_step_approve()
        return self.async_show_form(step_id="confirm", description_placeholders={"name": self.hello.get("name", self.host)})

    async def async_step_approve(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """asks the Echo to let this key in (it plays its login sound and shows the blue ring), then waits for "Submit"
        after the press; a login runs out after a minute, asked again then"""
        errors: dict[str, str] = {}
        echo = self._echo()
        try:
            await echo.get_hello()
            state = await echo.login("Home Assistant")
        except EchoError:
            return self.async_abort(reason="cannot_connect")
        if state == "refused":             # another login at the same moment, or turned down: a new key, ask again
            self.key = new_key(); echo = self._echo(); await echo.get_hello(); state = await echo.login("Home Assistant")
            errors["base"] = "refused"
        if state == "approved":
            data = {CONF_HOST: self.host, "port": self.port, CONF_KEY: self.key, CONF_NODE: self.hello["node"],
                    CONF_MAC: self.hello.get("mac", ""), "name": self.hello.get("name", self.host)}
            if self.source == "reauth":
                return self.async_update_reload_and_abort(self._get_reauth_entry(), data=data)
            return self.async_create_entry(title=self.hello.get("name", self.host), data=data)
        if user_input is not None and not errors:
            errors["base"] = "not_approved"
        self.asked = True
        return self.async_show_form(step_id="approve", errors=errors,
                                    description_placeholders={"name": self.hello.get("name", self.host), "button": self._button()})

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """the Echo forgot this key (a factory reset, the login revoked on its page): let a new one in"""
        self.host, self.port = entry_data[CONF_HOST], entry_data.get("port", DEFAULT_PORT)
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """first a Submit: the login lights up the Echo and waits a minute for its button, so only when someone is there"""
        if user_input is None:
            return self.async_show_form(step_id="reauth_confirm", description_placeholders={"name": self._get_reauth_entry().title})
        try:
            await self._identify()
        except EchoError:
            return self.async_abort(reason="cannot_connect")
        return await self.async_step_approve()


class HassmicOptionsFlow(OptionsFlowWithReload):
    """The Echo Show's screen (kiosk.py): Home Assistant on it, which screens, where it starts.  The entry reloads on
    Submit, and its setup sends it all to the Echo."""

    def __init__(self) -> None:
        self.kiosk: dict = {}

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        o = self.config_entry.options
        if user_input is not None:
            self.kiosk = user_input
            return await self.async_step_wall()
        kinds = [selector.SelectOptionDict(value=v, label=l) for v, l in (
            ("clock", "Clock (a screen app's own: not hassmic's built-in kiosk)"),
            ("wall", "Wall panel (rooms and tiles, light on memory)"), ("dashboard", "Home Assistant's own UI"),
            ("music", "Music Assistant"), ("custom", "A page of your own"))]
        music = k.music_panel(self.hass)
        schema = vol.Schema({
            vol.Required(k.OPT_KIOSK, default=o.get(k.OPT_KIOSK, False)): bool,
            vol.Required(k.OPT_SCREENS, default=o.get(k.OPT_SCREENS, ["wall", "dashboard"] + (["music"] if music else []))):
                selector.SelectSelector(selector.SelectSelectorConfig(options=kinds, multiple=True)),
            vol.Required(k.OPT_DEFAULT, default=o.get(k.OPT_DEFAULT, "wall")):
                selector.SelectSelector(selector.SelectSelectorConfig(options=kinds, mode=selector.SelectSelectorMode.DROPDOWN)),
            vol.Optional(k.OPT_DASHBOARD, default=o.get(k.OPT_DASHBOARD, "lovelace")): str,
            vol.Optional(k.OPT_MUSIC, default=o.get(k.OPT_MUSIC, music)): str,
            vol.Optional(k.OPT_CUSTOM_NAME, default=o.get(k.OPT_CUSTOM_NAME, "")): str,
            vol.Optional(k.OPT_CUSTOM_URL, default=o.get(k.OPT_CUSTOM_URL, "")): str,
            vol.Required(k.OPT_RETURN, default=o.get(k.OPT_RETURN, 120)):
                selector.NumberSelector(selector.NumberSelectorConfig(min=0, max=3600, step=10, unit_of_measurement="s", mode=selector.NumberSelectorMode.BOX)),
            vol.Required(k.OPT_ADMIN, default=o.get(k.OPT_ADMIN, False)): bool,
            vol.Optional(k.OPT_URL, default=o.get(k.OPT_URL, "")): str,
            vol.Optional(k.OPT_APP, default=o.get(k.OPT_APP, "")): str,
        })
        return self.async_show_form(step_id="init", data_schema=schema,
                                    description_placeholders={"url": k.ha_url(self.hass, self.config_entry)})

    async def async_step_wall(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """The wall panel on this Echo (wall.py): its look and what Home shows.  The same layout the panel's own edit
        mode changes (hold the page dots on the Echo): whichever was last."""
        echo = self.config_entry.unique_id
        lay = wall.get(self.hass, echo)
        if user_input is not None:
            new = {**lay, "theme": user_input["theme"], "ambient": int(user_input["ambient"]),
                   "nowplaying": user_input["nowplaying"], "hidden": user_input.get("hidden") or []}
            new["weather"] = user_input.get("weather") or ""
            fav = user_input.get("favorites") or []
            new["favorites"] = fav if fav else None         # none: the panel picks (thermostat, camera, scenes, locks)
            await wall.put(self.hass, echo, new)
            return self.async_create_entry(data={**self.config_entry.options, **self.kiosk})
        sel = lambda **kw: selector.EntitySelector(selector.EntitySelectorConfig(**kw))
        theme = [selector.SelectOptionDict(value=v, label=l) for v, l in (("amber", "Amber"), ("dusk", "Dusk"), ("light", "Light"))]
        schema = vol.Schema({
            vol.Required("theme", default=lay.get("theme", "amber")):
                selector.SelectSelector(selector.SelectSelectorConfig(options=theme, mode=selector.SelectSelectorMode.LIST)),
            vol.Optional("favorites", description={"suggested_value": lay.get("favorites") or []}): sel(multiple=True, reorder=True),
            vol.Optional("weather", description={"suggested_value": lay.get("weather") or None}): sel(domain="weather"),
            vol.Required("nowplaying", default=lay.get("nowplaying", True)): bool,
            vol.Required("ambient", default=lay.get("ambient", 120)):
                selector.NumberSelector(selector.NumberSelectorConfig(min=0, max=3600, step=10, unit_of_measurement="s", mode=selector.NumberSelectorMode.BOX)),
            vol.Optional("hidden", description={"suggested_value": lay.get("hidden") or []}): sel(multiple=True),
        })
        return self.async_show_form(step_id="wall", data_schema=schema)
