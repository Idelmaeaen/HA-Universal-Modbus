"""Binary sensor platform for Universal Modbus."""
from homeassistant.components.binary_sensor import BinarySensorEntity
from .entity import UniversalModbusEntity

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    async_add_entities([UniversalModbusBinarySensor(coordinator, item) for item in coordinator.entities if item.platform == "binary_sensor"])

class UniversalModbusBinarySensor(UniversalModbusEntity, BinarySensorEntity):
    def __init__(self, coordinator, definition) -> None:
        super().__init__(coordinator, definition)
        self._attr_device_class = definition.device_class

    @property
    def is_on(self):
        return bool(self.coordinator.data.get(self.definition.key))
