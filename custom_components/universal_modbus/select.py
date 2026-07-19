"""Select platform for Universal Modbus."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity

from .entity import UniversalModbusEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        UniversalModbusSelect(coordinator, definition)
        for definition in coordinator.entities
        if definition.platform == "select"
    )


class UniversalModbusSelect(UniversalModbusEntity, SelectEntity):
    def __init__(self, coordinator, definition) -> None:
        super().__init__(coordinator, definition)
        self._attr_options = list(definition.options)

    @property
    def current_option(self) -> str | None:
        value = self.coordinator.data.get(self.definition.key)
        for option, raw_value in self.definition.options.items():
            if raw_value == value:
                return option
        return None

    async def async_select_option(self, option: str) -> None:
        if not self.definition.writable:
            raise ValueError("Entity is read only")
        try:
            value = self.definition.options[option]
        except KeyError as err:
            raise ValueError(f"Unsupported option: {option}") from err
        await self.coordinator.async_write_value(self.definition, value)
