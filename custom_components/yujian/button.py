"""Explicit notification actions."""

from homeassistant.components.button import ButtonEntity
from homeassistant.exceptions import HomeAssistantError

from .client import YujianError
from .const import DOMAIN
from .entity import YujianEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities(
        [YujianButton(entry, coordinator, key) for key in ("dismiss", "refresh")]
    )


class YujianButton(YujianEntity, ButtonEntity):
    def __init__(self, entry, coordinator, key):
        super().__init__(entry, coordinator, key)
        self._attr_icon = "mdi:close-box-outline" if key == "dismiss" else "mdi:refresh"

    @property
    def available(self):
        """Keep manual retry available while the device is offline."""
        return self._key == "refresh" or super().available

    async def async_press(self):
        if self._key == "dismiss":
            try:
                await self.coordinator.client.async_dismiss()
            except YujianError as err:
                raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_refresh()
        if not self.coordinator.last_update_success:
            raise HomeAssistantError("Unable to refresh the device")
