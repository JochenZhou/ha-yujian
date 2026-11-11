"""Poll notification health and recent history independently of music."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import YujianClient, YujianError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL_SEC = 60


class YujianCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, client: YujianClient):
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=SCAN_INTERVAL_SEC),
        )
        self.client = client
        self.entry = entry

    async def _async_update_data(self):
        try:
            data = dict(await self.client.async_health())
        except YujianError as err:
            raise UpdateFailed(str(err)) from err
        if data.get("ok") is not True:
            raise UpdateFailed("Invalid device health response")
        try:
            history = await self.client.async_history()
        except YujianError:
            data["history_available"] = False
            data["last_notification"] = (self.data or {}).get("last_notification")
            data["history_count"] = (self.data or {}).get("history_count")
        else:
            data["history_available"] = True
            data["last_notification"] = history[0] if history else None
            data["history_count"] = len(history)
        registry = dr.async_get(self.hass)
        device = registry.async_get_device_by_identifier(
            (
                DOMAIN,
                self.entry.unique_id
                or self.entry.data.get("host", self.entry.entry_id),
            ),
            self.entry.entry_id,
        )
        if device is not None:
            registry.async_update_device(
                device.id,
                sw_version=data.get("version"),
                configuration_url=self.client.configuration_url,
            )
        return data
