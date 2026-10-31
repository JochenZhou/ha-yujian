"""Coordinator for the 玉简 integration.

Keeps the last health payload of the TV so the notify entity can report
availability and expose the TV's version / uptime / banner state / mute state /
default banner position, plus the newest entry of the TV's notification history.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import YujianClient, YujianError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL_SEC = 60


class YujianCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Poll the TV's health endpoint so availability reflects the real state."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: YujianClient
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=SCAN_INTERVAL_SEC),
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch the health payload, plus the newest history entry (best effort).

        The history endpoint only exists on app v1.3.0+, so a failure there must
        never make the entity look unavailable -- it is merged in as ``None``.
        """
        try:
            data = dict(await self.client.async_health())
        except YujianError as err:
            raise UpdateFailed(str(err)) from err

        try:
            history = await self.client.async_history()
        except YujianError as err:
            _LOGGER.debug("读取传音简录失败（旧版 App 不支持该接口）: %s", err)
            history = []
        data["last_notification"] = history[0] if history else None
        data["history_count"] = len(history)
        return data
