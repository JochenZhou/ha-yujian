"""Notification sound settings."""

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN
from .entity import YujianEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        [
            YujianMuteSwitch(
                entry, hass.data[DOMAIN][entry.entry_id]["coordinator"], "muted"
            )
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
