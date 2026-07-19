"""Button platform for Universal Modbus."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity

from .entity import UniversalModbusEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        UniversalModbusButton(coordinator, definition)
        for definition in coordinator.entities
        if definition.platform == "button"
    )


class UniversalModbusButton(UniversalModbusEntity, ButtonEntity):
    def __init__(self, coordinator, definition) -> None:
        super().__init__(coordinator, definition)
        self._attr_device_class = definition.device_class

    async def async_press(self) -> None:
        if not self.definition.writable:
            raise ValueError("Entity is read only")
        if self.definition.pulse_ms:
            await self.coordinator.async_pulse(self.definition)
        else:
            await self.coordinator.async_write_value(
                self.definition, self.definition.command_on
            )
