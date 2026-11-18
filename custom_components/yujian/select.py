"""Notification theme/position and music player/WLED select controls."""

from homeassistant.components.select import SelectEntity
from homeassistant.helpers.entity import EntityCategory

from .const import BANNER_POSITIONS, DOMAIN, PLAYER_STYLES, THEMES, WLED_EFFECTS
from .entity import YujianEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities(
        [
            YujianSelect(entry, coordinator, key)
            for key in ("theme", "position", "player_style", "wled_effect")
        ]
    )


class YujianSelect(YujianEntity, SelectEntity):
    _attr_entity_category = EntityCategory.CONFIG

    _CONFIG = {
        "theme": (THEMES, "mdi:palette-outline", False),
        "position": (BANNER_POSITIONS, "mdi:page-layout-header-footer", False),
        "player_style": (PLAYER_STYLES, "mdi:disc-player", True),
        "wled_effect": (WLED_EFFECTS, "mdi:auto-fix", True),
    }

    def __init__(self, entry, coordinator, key):
        super().__init__(entry, coordinator, key)
        options, icon, requires_sendspin = self._CONFIG[key]
        self._attr_options = list(options)
        self._attr_icon = icon
        self._requires_sendspin = requires_sendspin

    @property
    def available(self):
        if not super().available:
            return False
        if not self._requires_sendspin:
            return True
        return bool((self.coordinator.data or {}).get("sendspin_config_available"))

    @property
    def current_option(self):
        return (self.coordinator.data or {}).get(self._key)

    async def async_select_option(self, option):
        if self._requires_sendspin:
            await self.async_set_sendspin_config(**{self._key: option})
        else:
            await self.async_set_config(**{self._key: option})
