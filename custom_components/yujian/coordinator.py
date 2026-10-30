"""Coordinator for the 玉简 integration.

Keeps the last health payload of the TV so the notify entity can report
availability and expose the TV's version / uptime / banner state.
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
        """Fetch the health payload."""
        try:
            return await self.client.async_health()
        except YujianError as err:
            raise UpdateFailed(str(err)) from err
