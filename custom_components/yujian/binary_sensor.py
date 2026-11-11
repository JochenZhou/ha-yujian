"""Live banner visibility."""

from homeassistant.components.binary_sensor import BinarySensorEntity

from .const import DOMAIN
from .entity import YujianEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        [
            YujianBannerSensor(
                entry, hass.data[DOMAIN][entry.entry_id]["coordinator"], "banner"
            )
        ]
    )


class YujianBannerSensor(YujianEntity, BinarySensorEntity):
    _attr_icon = "mdi:message-badge-outline"

    @property
    def is_on(self):
        value = (self.coordinator.data or {}).get("banner")
        return None if value is None else value == "showing"
