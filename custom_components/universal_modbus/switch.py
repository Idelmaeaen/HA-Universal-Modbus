"""Switch platform for Universal Modbus."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity

from .entity import UniversalModbusEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        UniversalModbusSwitch(coordinator, definition)
        for definition in coordinator.entities
        if definition.platform == "switch"
    )


class UniversalModbusSwitch(UniversalModbusEntity, SwitchEntity):
    """Representation of a writable Modbus switch."""

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.get(self.definition.key))

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_write_value(
            self.definition, self.definition.command_on
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_write_value(
            self.definition, self.definition.command_off
        )
