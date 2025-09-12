from __future__ import annotations
from typing import Any, Dict, Optional
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN, CONF_CLIENT_ID, CONF_CLIENT_SECRET, CONF_EXPOSE_DOMAINS, DEFAULT_EXPOSE

STEP_USER_SCHEMA = vol.Schema({
    vol.Required(CONF_CLIENT_ID): str,
    vol.Required(CONF_CLIENT_SECRET): str,
    vol.Optional(CONF_EXPOSE_DOMAINS, default=DEFAULT_EXPOSE): [str],
})

class HABridgeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    def __init__(self):
        self._data: Dict[str, Any] = {}

    async def async_step_user(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        if user_input is not None:
            # Single instance enforcement
            existing = await self._async_current_entries()
            if existing:
                return self.async_abort(reason="single_instance_allowed")
            self._data = user_input
            return self.async_create_entry(title="HA Bridge", data=self._data)
        return self.async_show_form(step_id="user", data_schema=STEP_USER_SCHEMA)

    async def async_step_import(self, user_input: Dict[str, Any]) -> FlowResult:
        # Support YAML import (if still present) but prefer UI
        return await self.async_step_user(user_input)

class HABridgeOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="Options", data=user_input)
        data = {**self.config_entry.data, **(self.config_entry.options or {})}
        schema = vol.Schema({
            vol.Required(CONF_CLIENT_ID, default=data.get(CONF_CLIENT_ID, "")): str,
            vol.Required(CONF_CLIENT_SECRET, default=data.get(CONF_CLIENT_SECRET, "")): str,
            vol.Optional(CONF_EXPOSE_DOMAINS, default=data.get(CONF_EXPOSE_DOMAINS, DEFAULT_EXPOSE)): [str],
        })
        return self.async_show_form(step_id="init", data_schema=schema)

def get_options_flow(config_entry):
    return HABridgeOptionsFlowHandler(config_entry)
