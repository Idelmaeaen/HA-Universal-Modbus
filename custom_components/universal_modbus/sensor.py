"""Sensor platform for Universal Modbus."""
from homeassistant.components.sensor import SensorEntity
from .entity import UniversalModbusEntity

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    async_add_entities([UniversalModbusSensor(coordinator, item) for item in coordinator.entities if item.platform == "sensor"])

class UniversalModbusSensor(UniversalModbusEntity, SensorEntity):
    def __init__(self, coordinator, definition) -> None:
        super().__init__(coordinator, definition)
        self._attr_native_unit_of_measurement = definition.unit

    @property
    def native_value(self):
        return self.coordinator.data.get(self.definition.key)
