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

from .client import YujianClient, YujianError
from .const import DEFAULT_DURATION, DISPLAY_NAME, DOMAIN, LEGACY_NAMES
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


class YujianNotifyEntity(NotifyEntity):
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
        self._entry = entry
        self._coordinator = coordinator
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
    def available(self) -> bool:
        """Return whether the TV is reachable."""
        return self._coordinator.last_update_success

    @property
    def default_duration(self) -> int:
        """Return the default banner duration in seconds."""
        raw = self._entry.options.get("duration", DEFAULT_DURATION)
        try:
            return int(raw)
        except (TypeError, ValueError):
            return DEFAULT_DURATION

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the TV's health payload as attributes."""
        if self._coordinator.data is None:
            return {}
        return dict(self._coordinator.data)

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
    ) -> None:
        """Push a banner, reviving the TV app once if the first attempt fails."""
        try:
            await self._client.async_notify(
                title=title,
                message=message,
                duration=duration,
                level=level,
                sound=sound,
                sticky=sticky,
                max_duration=max_duration,
                image=image,
                video=video,
            )
        except YujianError as err:
            _LOGGER.debug("第一次推送失败，尝试拉起电视上的服务后重试: %s", err)
            if not await self._client.async_revive():
                raise HomeAssistantError(f"电视上的玉简服务不可用: {err}") from err
            try:
                await self._client.async_notify(
                    title=title,
                    message=message,
                    duration=duration,
                    level=level,
                    sound=sound,
                    sticky=sticky,
                    max_duration=max_duration,
                    image=image,
                    video=video,
                )
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

    async def async_send_message(self, message: str, title: str | None = None) -> None:
        """Send a banner to the TV."""
        await self.async_push(title=title or "", message=message)
