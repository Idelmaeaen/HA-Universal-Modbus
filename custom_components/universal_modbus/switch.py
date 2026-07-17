"""Switch platform for Universal Modbus."""
from homeassistant.components.switch import SwitchEntity

from .entity import UniversalModbusEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    async_add_entities(
        [UniversalModbusSwitch(coordinator, item) for item in coordinator.entities if item.platform == "switch"]
    )


class UniversalModbusSwitch(UniversalModbusEntity, SwitchEntity):
    @property
    def is_on(self):
        return bool(self.coordinator.data.get(self.definition.key))

    async def async_turn_on(self, **kwargs):
        await self.coordinator.async_write_value(self.definition, self.definition.command_on)

    async def async_turn_off(self, **kwargs):
        await self.coordinator.async_write_value(self.definition, self.definition.command_off)
