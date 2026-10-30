"""Client for the 玉简 HTTP API on the TV."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DEFAULT_DURATION,
    DISMISS_PATH_TEMPLATE,
    HEALTH_PATH,
    MAX_DURATION,
    MIN_DURATION,
    NOTIFY_PATH_TEMPLATE,
    REVIVE_DELAY_SEC,
    TV_SERVICE,
)

_LOGGER = logging.getLogger(__name__)


class YujianError(Exception):
    """Raised when the TV cannot be reached or refuses the request."""


class YujianClient:
    """Talks to one 玉简 instance on the LAN."""

    def __init__(self, hass: HomeAssistant, host: str, port: int, token: str) -> None:
        """Initialize the client."""
        self._hass = hass
        self._host = host
        self._port = port
        self._token = token

    @property
    def host(self) -> str:
        """Return the TV address."""
        return self._host

    @property
    def port(self) -> int:
        """Return the TV port."""
        return self._port

    @property
    def token(self) -> str:
        """Return the access token."""
        return self._token

    @property
    def base_url(self) -> str:
        """Return the base URL of the TV's HTTP server."""
        return f"http://{self._host}:{self._port}"

    def update(
        self,
        host: str | None = None,
        port: int | None = None,
        token: str | None = None,
    ) -> None:
        """Update the address after a rediscovery."""
        if host:
            self._host = host
        if port:
            self._port = port
        if token:
            self._token = token

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    async def async_health(self) -> dict[str, Any]:
        """Call the token-less health probe."""
        url = f"{self.base_url}{HEALTH_PATH}"
        session = async_get_clientsession(self._hass)
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status != 200:
                    raise YujianError(f"health check failed: HTTP {resp.status}")
                return await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise YujianError(f"health check failed: {err}") from err

    async def async_notify(
        self,
        title: str,
        message: str,
        duration: int = DEFAULT_DURATION,
        level: str | None = None,
        sticky: bool | None = None,
        max_duration: int | None = None,
        sound: bool | None = None,
    ) -> None:
        """Push a banner to the TV."""
        payload: dict[str, Any] = {
            "title": title,
            "text": message,
            "duration": max(MIN_DURATION, min(MAX_DURATION, duration)),
        }
        if level:
            payload["level"] = level
        if sticky is not None:
            payload["sticky"] = sticky
        if max_duration is not None:
            payload["maxDuration"] = max_duration
        if sound is not None:
            payload["sound"] = sound

        url = f"{self.base_url}{NOTIFY_PATH_TEMPLATE.format(token=self._token)}"
        await self._async_post(url, payload)

    async def async_dismiss(self) -> None:
        """Close the banner currently shown on the TV."""
        url = f"{self.base_url}{DISMISS_PATH_TEMPLATE.format(token=self._token)}"
        await self._async_post(url, {})

    async def _async_post(self, url: str, payload: dict[str, Any]) -> None:
        """POST JSON and raise on any non-2xx answer."""
        session = async_get_clientsession(self._hass)
        try:
            async with session.post(
                url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
                headers={"Content-Type": "application/json; charset=utf-8"},
            ) as resp:
                body = await resp.text()
                if resp.status != 200:
                    raise YujianError(f"HTTP {resp.status}: {body[:200]}")
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise YujianError(str(err)) from err

    # ------------------------------------------------------------------
    # Self healing
    # ------------------------------------------------------------------

    async def async_revive(self) -> bool:
        """Bring the TV app back up over ADB and wait for the port.

        The TV's firmware kills the app while it sits in standby; without
        this, a push would fail until somebody restarts the app by hand.
        """
        if not await self._async_adb_start_service():
            return False
        await asyncio.sleep(REVIVE_DELAY_SEC)
        return True

    async def _async_adb_start_service(self) -> bool:
        """Run ``am startservice`` on the TV through the Android TV integration."""
        from homeassistant.components.androidtv import DOMAIN as ANDROIDTV_DOMAIN
        from homeassistant.exceptions import HomeAssistantError

        entity_id = self._adb_entity_id()
        if entity_id is None:
            _LOGGER.warning(
                "没有找到这台电视对应的 Android TV 实体，无法自动拉起玉简服务"
            )
            return False

        command = f"am startservice -n {TV_SERVICE}"
        try:
            await self._hass.services.async_call(
                ANDROIDTV_DOMAIN,
                "adb_command",
                {"entity_id": entity_id, "command": command},
                blocking=True,
            )
        except HomeAssistantError as err:
            _LOGGER.warning("通过 ADB 拉起玉简服务失败: %s", err)
            return False
        except Exception as err:  # noqa: BLE001 - never break the notification path
            _LOGGER.warning("通过 ADB 拉起玉简服务时出错: %s", err)
            return False
        _LOGGER.debug("已通过 ADB 在电视上拉起 %s", TV_SERVICE)
        return True

    def _adb_entity_id(self) -> str | None:
        """Find the Android TV media_player entity that points at this TV."""
        from homeassistant.components.androidtv import DOMAIN as ANDROIDTV_DOMAIN
        from homeassistant.helpers import entity_registry as er

        registry = er.async_get(self._hass)
        for entry in self._hass.config_entries.async_loaded_entries(ANDROIDTV_DOMAIN):
            if entry.data.get("host") != self._host:
                continue
            for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
                if entity.domain == "media_player":
                    return entity.entity_id
        return None
