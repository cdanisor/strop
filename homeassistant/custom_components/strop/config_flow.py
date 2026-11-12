"""Config flow for Strop: URL + password -> long-lived integration token."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.network import NoURLAvailableError, get_url
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import StropAuthError, StropClient, StropConnectionError, StropError
from .const import (
    CONF_HA_URL,
    CONF_LANGUAGE,
    CONF_NOTIFY_EVENTS,
    CONF_NOTIFY_SERVICE,
    CONF_TOKEN,
    CONF_URL,
    DEFAULT_NOTIFY_EVENTS,
    DEFAULT_URL,
    DOMAIN,
    NOTIFY_EVENT_TYPES,
    TOKEN_NAME,
)

PASSWORD_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


def _default_ha_url(hass) -> str:
    try:
        return get_url(hass, allow_external=False, prefer_external=False)
    except NoURLAvailableError:
        return ""


class StropConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def _obtain_token(self, url: str, password: str) -> str:
        client = StropClient(async_get_clientsession(self.hass), url)
        session_token = await client.login(password)
        return await client.create_integration_token(session_token, TOKEN_NAME)

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            url = user_input[CONF_URL].rstrip("/")
            await self.async_set_unique_id(url)
            self._abort_if_unique_id_configured()
            try:
                token = await self._obtain_token(url, user_input["password"])
            except StropAuthError:
                errors["base"] = "invalid_auth"
            except StropConnectionError:
                errors["base"] = "cannot_connect"
            except StropError:
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title="Strop",
                    data={CONF_URL: url, CONF_TOKEN: token, CONF_HA_URL: user_input[CONF_HA_URL].rstrip("/")},
                )

        schema = vol.Schema({
            vol.Required(CONF_URL, default=(user_input or {}).get(CONF_URL, DEFAULT_URL)): str,
            vol.Required("password"): PASSWORD_SELECTOR,
            vol.Required(CONF_HA_URL, default=(user_input or {}).get(CONF_HA_URL, _default_ha_url(self.hass))): str,
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    # ------------------------------------------------------------------ reauth
    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            try:
                token = await self._obtain_token(entry.data[CONF_URL], user_input["password"])
            except StropAuthError:
                errors["base"] = "invalid_auth"
            except StropConnectionError:
                errors["base"] = "cannot_connect"
            except StropError:
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(entry, data_updates={CONF_TOKEN: token})
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required("password"): PASSWORD_SELECTOR}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return StropOptionsFlow()


class StropOptionsFlow(OptionsFlow):
    """Notification settings."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        services = sorted(self.hass.services.async_services_for_domain("notify"))
        notify_options = [SelectOptionDict(value="", label="—")] + [
            SelectOptionDict(value=f"notify.{name}", label=f"notify.{name}") for name in services
        ]
        options = self.config_entry.options
        default_lang = "ro" if (self.hass.config.language or "").startswith("ro") else "en"
        schema = vol.Schema({
            vol.Optional(CONF_NOTIFY_SERVICE, default=options.get(CONF_NOTIFY_SERVICE, "")): SelectSelector(
                SelectSelectorConfig(options=notify_options, mode=SelectSelectorMode.DROPDOWN, custom_value=True)
            ),
            vol.Optional(CONF_NOTIFY_EVENTS, default=options.get(CONF_NOTIFY_EVENTS, DEFAULT_NOTIFY_EVENTS)): SelectSelector(
                SelectSelectorConfig(options=NOTIFY_EVENT_TYPES, multiple=True, mode=SelectSelectorMode.LIST,
                                     translation_key="notify_events")
            ),
            vol.Optional(CONF_LANGUAGE, default=options.get(CONF_LANGUAGE, default_lang)): SelectSelector(
                SelectSelectorConfig(options=["ro", "en"], mode=SelectSelectorMode.DROPDOWN, translation_key="language")
            ),
        })
        return self.async_show_form(step_id="init", data_schema=schema)
