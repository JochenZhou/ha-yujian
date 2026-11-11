"""Shared identity and state handling for native notification entities."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import YujianError
from .const import DISPLAY_NAME, DOMAIN, LEGACY_NAMES


def device_info(entry, coordinator) -> DeviceInfo:
    """Preserve the notify platform's existing device identifier."""
    name = entry.options.get(CONF_NAME) or entry.data.get(CONF_NAME) or DISPLAY_NAME
    if name.startswith(LEGACY_NAMES):
        name = DISPLAY_NAME
    data = coordinator.data or {}
    return DeviceInfo(
        identifiers={
            (DOMAIN, entry.unique_id or entry.data.get(CONF_HOST, entry.entry_id))
        },
        name=name,
        manufacturer=DISPLAY_NAME,
        model=data.get("model"),
        sw_version=data.get("version"),
        configuration_url=coordinator.client.configuration_url,
    )


class YujianEntity(CoordinatorEntity):
    """One control or status field belonging to a configured TV."""

    _attr_has_entity_name = True

    def __init__(self, entry, coordinator, key):
        super().__init__(coordinator)
        self._entry = entry
        self._key = key
        self._attr_translation_key = key
        self._attr_unique_id = (
            f"{entry.unique_id or entry.data.get(CONF_HOST, entry.entry_id)}_{key}"
        )

    @property
    def device_info(self) -> DeviceInfo:
        return device_info(self._entry, self.coordinator)

    async def async_set_config(self, **changes):
        """Publish the actual configuration echoed by the App."""
        try:
            result = await self.coordinator.client.async_set_config(**changes)
        except YujianError as err:
            raise HomeAssistantError(str(err)) from err
        self.coordinator.async_set_updated_data(
            {
                **(self.coordinator.data or {}),
                **{k: v for k, v in result.items() if k != "ok"},
            }
        )
