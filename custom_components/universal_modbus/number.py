"""Number platform for Universal Modbus."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity

from .entity import UniversalModbusEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        UniversalModbusNumber(coordinator, definition)
        for definition in coordinator.entities
        if definition.platform == "number"
    )


class UniversalModbusNumber(UniversalModbusEntity, NumberEntity):
    def __init__(self, coordinator, definition) -> None:
        super().__init__(coordinator, definition)
        self._attr_native_min_value = definition.minimum
        self._attr_native_max_value = definition.maximum
        self._attr_native_step = definition.step
        self._attr_native_unit_of_measurement = definition.unit
        self._attr_device_class = definition.device_class
        self._attr_suggested_display_precision = definition.display_precision

    @property
    def native_value(self):
        return self.coordinator.data.get(self.definition.key)

    async def async_set_native_value(self, value: float) -> None:
        if not self.definition.writable:
            raise ValueError("Entity is read only")
        await self.coordinator.async_write_value(self.definition, value)
