"""Global notification theme and position controls."""

from homeassistant.components.select import SelectEntity
from homeassistant.helpers.entity import EntityCategory

from .const import BANNER_POSITIONS, DOMAIN, THEMES
from .entity import YujianEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities(
        [YujianSelect(entry, coordinator, key) for key in ("theme", "position")]
    )


class YujianSelect(YujianEntity, SelectEntity):
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, entry, coordinator, key):
        super().__init__(entry, coordinator, key)
        self._attr_options = list(THEMES if key == "theme" else BANNER_POSITIONS)
        self._attr_icon = (
            "mdi:palette-outline" if key == "theme" else "mdi:page-layout-header-footer"
        )

    @property
    def current_option(self):
        return (self.coordinator.data or {}).get(self._key)

    async def async_select_option(self, option):
        await self.async_set_config(**{self._key: option})
