"""Client for the 玉简 HTTP API on the TV."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONFIG_PATH_TEMPLATE,
    DEFAULT_DURATION,
    DISMISS_PATH_TEMPLATE,
    HEALTH_PATH,
    HISTORY_PATH_TEMPLATE,
    MAX_DURATION,
    MAX_IMAGE_INTERVAL,
    MAX_MAX_DURATION,
    MIN_DURATION,
    MIN_IMAGE_INTERVAL,
    MIN_MAX_DURATION,
    NOTIFY_PATH_TEMPLATE,
    REVIVE_DELAY_SEC,
    TV_SERVICE,
)

_LOGGER = logging.getLogger(__name__)


class YujianError(Exception):
    """Raised when the TV cannot be reached or refuses the request."""


def _looks_like_base64(value: str) -> bool:
    """Tell an inline base64 image from an image URL.

    The TV app accepts both (``image_base64`` vs ``image``). Everything that
    is not http(s) or a local file path is treated as base64 payload; data
    URIs, raw base64 and whitespace-wrapped camera snapshots all land here.
    """
    head = value.strip()[:2048].lower()
    return not (head.startswith("http://") or head.startswith("https://")
                or head.startswith("file://"))


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
        image: str | None = None,
        video: str | None = None,
        notify_id: str | None = None,
        position: str | None = None,
        tts: bool | str | None = None,
        image_interval: int | None = None,
        queue: bool | None = None,
    ) -> None:
        """Push a banner to the TV.

        ``image`` is a URL or an inline base64 data string, ``video`` an MJPEG
        stream URL -- both match the media contract of the TV app (v1.2.2+).
        The remaining arguments mirror the app v1.3.0 additions:

        * ``notify_id``: reuse the same id to update a showing banner in place
          (no re-entry animation).
        * ``position``: top / bottom / top-left / top-right / bottom-left /
          bottom-right; omit to inherit the TV's default position.
        * ``tts``: ``True`` speaks title + text, a string speaks that string.
        * ``image_interval``: seconds between refreshes of a static image URL.
        * ``queue``: enqueue behind the showing banner instead of replacing it.
        """
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
            payload["maxDuration"] = max(
                MIN_MAX_DURATION, min(MAX_MAX_DURATION, max_duration)
            )
        if sound is not None:
            payload["sound"] = sound
        if image:
            payload["image_base64" if _looks_like_base64(image) else "image"] = image
        if video:
            payload["video"] = video
        if notify_id:
            payload["id"] = notify_id
        if position:
            payload["position"] = position
        if tts is not None and tts != "":
            payload["tts"] = tts
        if image_interval:
            payload["image_interval"] = max(
                MIN_IMAGE_INTERVAL, min(MAX_IMAGE_INTERVAL, image_interval)
            )
        if queue is not None:
            payload["queue"] = queue

        url = f"{self.base_url}{NOTIFY_PATH_TEMPLATE.format(token=self._token)}"
        await self._async_post(url, payload)

    async def async_history(self) -> list[dict[str, Any]]:
        """Return the TV's recent notifications (app v1.3.0+, newest first)."""
        url = f"{self.base_url}{HISTORY_PATH_TEMPLATE.format(token=self._token)}"
        data = await self._async_get(url)
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        return []

    async def async_set_config(
        self,
        muted: bool | None = None,
        position: str | None = None,
    ) -> dict[str, Any]:
        """Change the TV's do-not-disturb switch and/or default banner position."""
        payload: dict[str, Any] = {}
        if muted is not None:
            payload["muted"] = muted
        if position:
            payload["position"] = position
        url = f"{self.base_url}{CONFIG_PATH_TEMPLATE.format(token=self._token)}"
        data = await self._async_post(url, payload)
        return data if isinstance(data, dict) else {}

    async def async_dismiss(self) -> None:
        """Close the banner currently shown on the TV."""
        url = f"{self.base_url}{DISMISS_PATH_TEMPLATE.format(token=self._token)}"
        await self._async_post(url, {})

    async def _async_post(self, url: str, payload: dict[str, Any]) -> Any:
        """POST JSON, raise on any non-2xx answer, return the decoded body."""
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
        try:
            return json.loads(body)
        except ValueError:
            return None

    async def _async_get(self, url: str) -> Any:
        """GET and decode a JSON body, raise on any non-2xx answer."""
        session = async_get_clientsession(self._hass)
        try:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                body = await resp.text()
                if resp.status != 200:
                    raise YujianError(f"HTTP {resp.status}: {body[:200]}")
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise YujianError(str(err)) from err
        try:
            return json.loads(body)
        except ValueError as err:
            raise YujianError(f"响应不是合法 JSON: {body[:120]}") from err

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
