"""Notification summary and service diagnostics."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import UnitOfTime
from homeassistant.helpers.entity import EntityCategory
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .entity import YujianEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities(
        [
            YujianSensor(entry, coordinator, key)
            for key in ("last_notification", "history_count", "uptime")
        ]
    )


class YujianSensor(YujianEntity, SensorEntity):
    def __init__(self, entry, coordinator, key):
        super().__init__(entry, coordinator, key)
        if key == "last_notification":
            self._attr_device_class = SensorDeviceClass.TIMESTAMP
        elif key == "uptime":
            self._attr_device_class = SensorDeviceClass.DURATION
            self._attr_native_unit_of_measurement = UnitOfTime.SECONDS
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def available(self):
        return super().available and (
            self._key == "uptime"
            or (self.coordinator.data or {}).get("history_available", False)
        )

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        if self._key != "last_notification":
            return data.get(self._key)
        ts = (data.get("last_notification") or {}).get("timestamp")
        if isinstance(ts, (int, float)) and not isinstance(ts, bool):
            try:
                return dt_util.utc_from_timestamp(ts / 1000)
            except (ValueError, OverflowError, OSError):
                return None
        return None

    @property
    def extra_state_attributes(self):
        if self._key != "last_notification":
            return None
        item = (self.coordinator.data or {}).get("last_notification") or {}
        return {
            key: item.get(key)
            for key in (
                "id",
                "title",
                "text",
                "level",
                "position",
                "has_media",
                "sticky",
            )
        }
