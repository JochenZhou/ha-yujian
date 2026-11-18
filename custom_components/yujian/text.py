"""Text setting for the target WLED host."""

from homeassistant.components.text import TextEntity
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN
from .entity import YujianEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([YujianWledHostText(entry, coordinator, "wled_color_host")])


class YujianWledHostText(YujianEntity, TextEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:ip-network-outline"
    _attr_native_min = 1
    _attr_native_max = 128

    @property
    def available(self):
        return super().available and bool(
            (self.coordinator.data or {}).get("sendspin_config_available")
        )

    @property
    def native_value(self):
        return (self.coordinator.data or {}).get(self._key)

    async def async_set_value(self, value: str) -> None:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("WLED host cannot be empty")
        await self.async_set_sendspin_config(wled_color_host=cleaned)
