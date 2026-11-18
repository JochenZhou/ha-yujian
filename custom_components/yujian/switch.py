"""Notification sound and WLED sync switches."""

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN
from .entity import YujianEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities(
        [
            YujianMuteSwitch(entry, coordinator, "muted"),
            YujianWledSwitch(
                entry, coordinator, "wled_sync_enabled", "mdi:waveform"
            ),
            YujianWledSwitch(
                entry,
                coordinator,
                "wled_color_sync_enabled",
                "mdi:palette-swatch-outline",
            ),
        ]
    )


class YujianMuteSwitch(YujianEntity, SwitchEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:bell-off-outline"

    @property
    def is_on(self):
        return (self.coordinator.data or {}).get("muted")

    async def async_turn_on(self, **kwargs):
        await self.async_set_config(muted=True)

    async def async_turn_off(self, **kwargs):
        await self.async_set_config(muted=False)


class YujianWledSwitch(YujianEntity, SwitchEntity):
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, entry, coordinator, key, icon):
        super().__init__(entry, coordinator, key)
        self._attr_icon = icon

    @property
    def available(self):
        return super().available and bool(
            (self.coordinator.data or {}).get("sendspin_config_available")
        )

    @property
    def is_on(self):
        return (self.coordinator.data or {}).get(self._key)

    async def async_turn_on(self, **kwargs):
        await self.async_set_sendspin_config(**{self._key: True})

    async def async_turn_off(self, **kwargs):
        await self.async_set_sendspin_config(**{self._key: False})
