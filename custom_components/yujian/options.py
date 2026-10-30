"""Options flow for the 玉简 integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT, CONF_TOKEN

from .const import DEFAULT_DURATION, DEFAULT_PORT


class YujianOptionsFlow(OptionsFlow):
    """Handle the 玉简 options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the 玉简 options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.data
        schema = vol.Schema(
            {
                vol.Optional(CONF_NAME, default=current.get(CONF_NAME, DISPLAY_NAME)): str,
                vol.Optional(CONF_HOST, default=current.get(CONF_HOST, "")): str,
                vol.Optional(
                    CONF_PORT, default=current.get(CONF_PORT, DEFAULT_PORT)
                ): vol.Coerce(int),
                vol.Optional(CONF_TOKEN, default=current.get(CONF_TOKEN, "")): str,
                vol.Optional("duration", default=DEFAULT_DURATION): vol.Coerce(int),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
