"""Config flow for the 玉简 integration.

Discovery path: the TV app broadcasts ``_yujian._tcp.local.`` with the
access token in the TXT record, so the flow completes without the user
copying anything by hand.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT, CONF_TOKEN
from homeassistant.core import callback
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .const import DEFAULT_PORT, DISPLAY_NAME, DOMAIN, TXT_TOKEN, ZEROCONF_TYPES

_LOGGER = logging.getLogger(__name__)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): vol.Coerce(int),
        vol.Required(CONF_TOKEN): str,
        vol.Optional(CONF_NAME, default=DISPLAY_NAME): str,
    }
)


def _prop(properties: dict[str, Any], key: str) -> str | None:
    """Read a TXT property; zeroconf hands them over as bytes."""
    value = properties.get(key)
    if value is None:
        value = properties.get(key.encode())
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8", "replace")
    value = str(value).strip()
    return value or None


class YujianConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for 玉简."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._discovered: dict[str, Any] = {}

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Handle a flow initialized by zeroconf.

        The discovery only *prepares* the entry; the user still has to confirm
        it. Home Assistant re-runs zeroconf discovery whenever a discovered
        config entry is removed, so creating the entry directly here would
        make the integration reappear on its own right after the user deleted
        it. With a confirm step the device simply shows up again under
        "Discovered" and the user decides what to do with it.
        """
        if discovery_info.ip_address.version != 4:
            return self.async_abort(reason="not_ipv4_address")

        if discovery_info.type not in ZEROCONF_TYPES:
            return self.async_abort(reason="not_supported_type")

        token = _prop(discovery_info.properties, TXT_TOKEN)
        if not token:
            _LOGGER.debug("mDNS 记录里没有 token，忽略这台设备")
            return self.async_abort(reason="no_token")

        host = discovery_info.host
        port = discovery_info.port or DEFAULT_PORT
        # The mDNS instance name (e.g. "TVNotify-tyeq") is App-internal and
        # means nothing to the user, so the entry gets the Chinese display
        # name instead; the host is what identifies the TV to the user.
        name = DISPLAY_NAME

        data = {
            CONF_HOST: host,
            CONF_PORT: port,
            CONF_TOKEN: token,
            CONF_NAME: name,
        }

        # One entry per TV. The token changes when the user resets it on the
        # TV, so the host is the stable identity here.
        await self.async_set_unique_id(host)
        self._abort_if_unique_id_configured(updates=data)

        self._discovered = data
        self.context["title_placeholders"] = {"name": host}

        _LOGGER.debug("通过 mDNS 发现电视: %s (%s:%s)", discovery_info.name, host, port)
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask the user to confirm the discovered TV."""
        if user_input is None:
            # title_placeholders only fills the card title; the {name} in the
            # step description needs description_placeholders, otherwise the
            # frontend throws "MISSING_VALUE" for the intl string. The host is
            # what tells the TVs apart, so show that here.
            return self.async_show_form(
                step_id="confirm",
                description_placeholders={"name": self._discovered[CONF_HOST]},
            )

        # The entry may have been created manually while this confirmation
        # was waiting, so check again before creating a second one.
        self._abort_if_unique_id_configured(updates=self._discovered)

        return self.async_create_entry(
            title=self._discovered[CONF_NAME], data=self._discovered
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a manual setup (no mDNS available)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            token = user_input[CONF_TOKEN].strip()
            port = user_input[CONF_PORT]
            name = user_input.get(CONF_NAME) or DISPLAY_NAME

            # raise_on_progress=False: a pending zeroconf discovery for the
            # same TV must not block a manual setup the user started on
            # purpose (same as the Sonos integration does).
            await self.async_set_unique_id(host, raise_on_progress=False)
            self._abort_if_unique_id_configured(
                updates={
                    CONF_HOST: host,
                    CONF_PORT: port,
                    CONF_TOKEN: token,
                }
            )

            from .client import YujianClient, YujianError

            client = YujianClient(self.hass, host, port, token)
            try:
                await client.async_health()
            except YujianError as err:
                errors["base"] = "cannot_connect"
                _LOGGER.debug("手动配置时健康检查失败: %s", err)
            else:
                return self.async_create_entry(
                    title=name,
                    data={
                        CONF_HOST: host,
                        CONF_PORT: port,
                        CONF_TOKEN: token,
                        CONF_NAME: name,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=USER_SCHEMA,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> Any:
        """Return the options flow handler."""
        from .options import YujianOptionsFlow

        return YujianOptionsFlow()
