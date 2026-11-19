"""Numeric WLED sync settings (UDP port and dynamic resolution)."""

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import PERCENTAGE
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN
from .entity import YujianEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities(
        [
            YujianWledPortNumber(entry, coordinator, "wled_sync_port"),
            YujianWledDynamicsNumber(entry, coordinator, "wled_sync_dynamics"),
        ]
    )


class YujianWledPortNumber(YujianEntity, NumberEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:network-outline"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 1
    _attr_native_max_value = 65535
    _attr_native_step = 1

    @property
    def available(self):
        return super().available and bool(
            (self.coordinator.data or {}).get("sendspin_config_available")
        )

    @property
    def native_value(self):
        return (self.coordinator.data or {}).get(self._key)

    async def async_set_native_value(self, value: float) -> None:
        await self.async_set_sendspin_config(wled_sync_port=int(round(value)))


class YujianWledDynamicsNumber(YujianEntity, NumberEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:tune-vertical"
    _attr_mode = NumberMode.SLIDER
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 5
    _attr_native_unit_of_measurement = PERCENTAGE

    @property
    def available(self):
        data = self.coordinator.data or {}
        return super().available and bool(data.get("sendspin_config_available")) and (
            self._key in data
        )

    @property
    def native_value(self):
        return (self.coordinator.data or {}).get(self._key)

    async def async_set_native_value(self, value: float) -> None:
        await self.async_set_sendspin_config(wled_sync_dynamics=int(round(value)))
