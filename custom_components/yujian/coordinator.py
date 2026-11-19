"""Poll notification health and recent history independently of music."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import timedelta

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import YujianClient, YujianError
from .const import CONF_MODEL, DOMAIN

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
        # Called when the TV's app uptime goes backwards, i.e. the app (and its
        # in-memory playlist catalog) restarted between two polls.
        self.on_device_restart: Callable[[], None] | None = None
        self._last_uptime: float | None = None
        self._last_playlist_count: int | None = None

    async def _async_update_data(self):
        try:
            data = dict(await self.client.async_health())
        except YujianError as err:
            raise UpdateFailed(str(err)) from err
        if data.get("ok") is not True:
            raise UpdateFailed("Invalid device health response")
        self._async_note_uptime(data)
        self._async_note_model(data)
        self._async_note_playlist_loss(data)
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
        try:
            sendspin = await self.client.async_sendspin_status()
        except YujianError:
            sendspin = None
        if isinstance(sendspin, dict) and "player_style" in sendspin:
            data["sendspin_config_available"] = True
            for key in (
                "player_style",
                "wled_sync_enabled",
                "wled_sync_port",
                "wled_sync_gain",
                "wled_color_sync_enabled",
                "wled_color_host",
                "wled_effect",
                "playlist_count",
            ):
                if key in sendspin:
                    data[key] = sendspin[key]
        else:
            data["sendspin_config_available"] = False
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

    def _async_note_uptime(self, data) -> None:
        """Fire the restart hook when the TV app restarted since the last poll.

        ``/health`` reports the app process uptime in seconds; a smaller value
        than last time means the app was restarted (and its playlist catalog,
        which lives in memory, is gone).
        """
        uptime = data.get("uptime")
        if not isinstance(uptime, (int, float)):
            return
        previous = self._last_uptime
        self._last_uptime = float(uptime)
        if previous is None or uptime >= previous:
            return
        _LOGGER.debug("电视 App 已重启（uptime %s → %s），准备重推歌单", previous, uptime)
        if self.on_device_restart is not None:
            self.on_device_restart()

    def _async_note_model(self, data) -> None:
        """Persist the TV's model string when /health reports one.

        Newer app versions include ``model`` in ``/health``, which is what lets
        the play webhook resolve the TV's own Music Assistant player without the
        user picking one by hand.
        """
        model = data.get("model")
        if not isinstance(model, str):
            return
        model = model.strip()
        if not model or model == self.entry.data.get(CONF_MODEL):
            return
        self.hass.config_entries.async_update_entry(
            self.entry, data={**self.entry.data, CONF_MODEL: model}
        )

    def _async_note_playlist_loss(self, data) -> None:
        """Re-trigger playlist sync when /health reports 0 playlists after holding some."""
        count = data.get("playlist_count")
        if not isinstance(count, int) or isinstance(count, bool):
            return
        previous = self._last_playlist_count
        self._last_playlist_count = count
        if previous is None or previous <= 0 or count > 0:
            return
        _LOGGER.debug("电视端歌单数降至 0（此前 %s），准备重推歌单", previous)
        if self.on_device_restart is not None:
            self.on_device_restart()
