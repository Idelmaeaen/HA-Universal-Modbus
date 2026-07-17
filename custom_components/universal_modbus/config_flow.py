"""Config flow for Universal Modbus."""

from __future__ import annotations

import json
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import callback

from .const import (
    CONF_ENTITIES,
    CONF_PROFILE_JSON,
    CONF_SCAN_INTERVAL,
    CONF_SLAVE,
    CONF_TIMEOUT,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SLAVE,
    DEFAULT_TIMEOUT,
    DOMAIN,
)
from .models import ModbusProfile


class UniversalModbusConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Set up one Modbus TCP device."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            unique_id = f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}:{user_input[CONF_SLAVE]}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=user_input[CONF_NAME],
                data=user_input,
                options={CONF_ENTITIES: []},
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME): str,
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(int, vol.Range(min=1, max=65535)),
                vol.Required(CONF_SLAVE, default=DEFAULT_SLAVE): vol.All(int, vol.Range(min=0, max=247)),
                vol.Required(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(int, vol.Range(min=1)),
                vol.Required(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): vol.All(int, vol.Range(min=1)),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return UniversalModbusOptionsFlow(config_entry)


class UniversalModbusOptionsFlow(config_entries.OptionsFlow):
    """Manage imported entity profiles."""

    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        return self.async_show_menu(step_id="init", menu_options=["import_profile", "clear_entities"])

    async def async_step_import_profile(self, user_input=None):
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                profile = ModbusProfile.from_dict(json.loads(user_input[CONF_PROFILE_JSON]))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                errors["base"] = "invalid_profile"
            else:
                options = dict(self.config_entry.options)
                options[CONF_ENTITIES] = [entity.__dict__ for entity in profile.entities]
                options["profile"] = profile.to_dict()
                return self.async_create_entry(title="", data=options)

        return self.async_show_form(
            step_id="import_profile",
            data_schema=vol.Schema({vol.Required(CONF_PROFILE_JSON): str}),
            errors=errors,
        )

    async def async_step_clear_entities(self, user_input=None):
        if user_input is not None:
            options = dict(self.config_entry.options)
            options[CONF_ENTITIES] = []
            options.pop("profile", None)
            return self.async_create_entry(title="", data=options)
        return self.async_show_form(
            step_id="clear_entities",
            data_schema=vol.Schema({vol.Required("confirm", default=False): bool}),
        )
