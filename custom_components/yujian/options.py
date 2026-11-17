"""Options flow for the 玉简 integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT, CONF_TOKEN
from homeassistant.helpers import selector

from .const import (
    CONF_SYNC_PLAYLISTS,
    CONF_TARGET_ENTITY,
    CONF_TTS_ENTITY,
    DEFAULT_DURATION,
    DEFAULT_PORT,
    DISPLAY_NAME,
)


class YujianOptionsFlow(OptionsFlow):
    """Handle the 玉简 options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the 玉简 options."""
        if user_input is not None:
            connection = {
                key: value
                for key, value in user_input.items()
                if key in (CONF_HOST, CONF_PORT, CONF_TOKEN, CONF_NAME)
            }
            self.hass.config_entries.async_update_entry(
                self.config_entry, data={**self.config_entry.data, **connection}
            )
            return self.async_create_entry(
                title="",
                data={
                    key: value
                    for key, value in user_input.items()
                    if key not in connection
                },
            )

        current = self.config_entry.data
        options = self.config_entry.options

        schema: dict[Any, Any] = {
            vol.Optional(CONF_NAME, default=current.get(CONF_NAME, DISPLAY_NAME)): str,
            vol.Optional(CONF_HOST, default=current.get(CONF_HOST, "")): str,
            vol.Optional(
                CONF_PORT, default=current.get(CONF_PORT, DEFAULT_PORT)
            ): vol.Coerce(int),
            vol.Optional(CONF_TOKEN, default=current.get(CONF_TOKEN, "")): str,
            vol.Optional(
                "duration", default=options.get("duration", DEFAULT_DURATION)
            ): vol.Coerce(int),
            # Optional: lets the integration synthesize speech itself and push
            # the audio URL to the app. This is the only voice path that works
            # on Android 6 TVs, which ship no Chinese TTS voice.
            vol.Optional(
                CONF_TTS_ENTITY,
                description={"suggested_value": options.get(CONF_TTS_ENTITY)},
            ): selector.EntitySelector(selector.EntitySelectorConfig(domain="tts")),
            # Which Music Assistant player plays the picked playlist. Leave
            # empty to auto-detect the first music_assistant player.
            vol.Optional(
                CONF_TARGET_ENTITY,
                description={"suggested_value": options.get(CONF_TARGET_ENTITY)},
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="media_player")
            ),
            # Push the playlist catalog to the TV (and accept its play requests).
            # NOTE: must be a selector, not vol.Boolean() -- HA 2026.11's
            # probatio serializer cannot serialize the voluptuous Boolean
            # marker and the options form dies with HTTP 500.
            vol.Optional(
                CONF_SYNC_PLAYLISTS,
                default=options.get(CONF_SYNC_PLAYLISTS, True),
            ): selector.BooleanSelector(),
        }
        return self.async_show_form(step_id="init", data_schema=vol.Schema(schema))
