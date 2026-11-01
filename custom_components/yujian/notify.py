"""Notify platform for the 玉简 integration.

The TV is discovered over mDNS, so address and access token are known without
the user copying anything by hand. The entity is a regular ``notify`` entity:
automations call ``notify.send_message`` with the TV as the target, or the
convenience service ``yujian.notify`` registered by the integration.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.notify import NotifyEntity, NotifyEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .client import YujianClient, YujianError
from .const import (
    CONF_TTS_ENTITY,
    DEFAULT_DURATION,
    DISPLAY_NAME,
    DOMAIN,
    LEGACY_NAMES,
)
from .coordinator import YujianCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the 玉简 notify entity from a config entry."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    coordinator: YujianCoordinator = entry_data["coordinator"]
    client: YujianClient = entry_data["client"]

    entity = YujianNotifyEntity(entry, coordinator, client)
    async_add_entities([entity])
    entry_data["entity"] = entity


class YujianNotifyEntity(CoordinatorEntity[YujianCoordinator], NotifyEntity):
    """A TV that can show notification banners."""

    _attr_should_poll = False
    _attr_supported_features = NotifyEntityFeature.TITLE

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: YujianCoordinator,
        client: YujianClient,
    ) -> None:
        """Initialize the entity."""
        # CoordinatorEntity gives us availability + state writes on every poll,
        # which is what keeps mute/position/history attributes fresh.
        super().__init__(coordinator)
        self._entry = entry
        self._client = client
        # Entries created before v1.3.0 stored an older name here (the mDNS
        # instance name like "TVNotify-tyeq", or "电视通知"); show the current
        # display name for those so existing installs get it without a data
        # migration.
        raw_name = entry.data.get(CONF_NAME) or DISPLAY_NAME
        name = DISPLAY_NAME if raw_name.startswith(LEGACY_NAMES) else raw_name
        self._attr_name = name
        self._attr_icon = "mdi:television"
        self._attr_unique_id = entry.data.get(CONF_HOST, entry.entry_id)
        health = coordinator.data or {}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._attr_unique_id)},
            name=name,
            manufacturer="玉简",
            model=health.get("model"),
            sw_version=health.get("version"),
        )

    @property
    def default_duration(self) -> int:
        """Return the default banner duration in seconds."""
        raw = self._entry.options.get("duration", DEFAULT_DURATION)
        try:
            return int(raw)
        except (TypeError, ValueError):
            return DEFAULT_DURATION

    @property
    def tts_entity(self) -> str | None:
        """Return the TTS entity chosen in the options, if any."""
        entity = self._entry.options.get(CONF_TTS_ENTITY)
        return entity if isinstance(entity, str) and entity else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the TV's live state: version, mute, banner position, history."""
        data = self.coordinator.data
        if not data:
            return {}
        attrs = dict(data)
        last = attrs.get("last_notification")
        if isinstance(last, dict):
            # Flatten the newest history entry so automations can read it.
            attrs["last_title"] = last.get("title")
            attrs["last_text"] = last.get("text")
            attrs["last_level"] = last.get("level")
            attrs["last_has_media"] = last.get("hasMedia")
            attrs["last_tts"] = last.get("tts")
            ts = last.get("timestamp")
            if isinstance(ts, (int, float)):
                attrs["last_notified_at"] = dt_util.utc_from_timestamp(ts / 1000).isoformat()
        return attrs

    async def async_push(
        self,
        title: str,
        message: str,
        duration: int = DEFAULT_DURATION,
        level: str | None = None,
        sound: bool | None = None,
        sticky: bool | None = None,
        max_duration: int | None = None,
        image: str | None = None,
        video: str | None = None,
        notify_id: str | None = None,
        position: str | None = None,
        tts: bool | str | None = None,
        image_interval: int | None = None,
        queue: bool | None = None,
    ) -> None:
        """Push a banner, reviving the TV app once if the first attempt fails."""
        kwargs = {
            "title": title,
            "message": message,
            "duration": duration,
            "level": level,
            "sound": sound,
            "sticky": sticky,
            "max_duration": max_duration,
            "image": image,
            "video": video,
            "notify_id": notify_id,
            "position": position,
            "tts": tts,
            "image_interval": image_interval,
            "queue": queue,
        }
        try:
            await self._client.async_notify(**kwargs)
        except YujianError as err:
            _LOGGER.debug("第一次推送失败，尝试拉起电视上的服务后重试: %s", err)
            if not await self._client.async_revive():
                raise HomeAssistantError(f"电视上的玉简服务不可用: {err}") from err
            try:
                await self._client.async_notify(**kwargs)
            except YujianError as retry_err:
                raise HomeAssistantError(
                    f"拉起服务后仍然无法推送通知: {retry_err}"
                ) from retry_err

    async def async_dismiss(self) -> None:
        """Close the banner currently shown on the TV."""
        try:
            await self._client.async_dismiss()
        except YujianError as err:
            raise HomeAssistantError(f"关闭电视上的横幅失败: {err}") from err

    async def async_send_message(
        self, message: str, title: str | None = None, **kwargs: Any
    ) -> None:
        """Send a banner to the TV.

        ``kwargs`` carries the integration's own extras (duration / level /
        sticky / sound / max_duration / image / video / position / tts /
        queue / notify_id / image_interval) when the convenience service pushes
        through the platform entry point; the plain ``notify.send_message``
        service passes none of them.
        """
        await self.async_push(
            title=title or "",
            message=message,
            duration=kwargs.get("duration", self.default_duration),
            level=kwargs.get("level"),
            sound=kwargs.get("sound"),
            sticky=kwargs.get("sticky"),
            max_duration=kwargs.get("max_duration"),
            image=kwargs.get("image"),
            video=kwargs.get("video"),
            notify_id=kwargs.get("notify_id"),
            position=kwargs.get("position"),
            tts=kwargs.get("tts"),
            image_interval=kwargs.get("image_interval"),
            queue=kwargs.get("queue"),
        )