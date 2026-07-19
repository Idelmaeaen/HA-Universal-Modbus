"""Base entity for Universal Modbus."""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


class UniversalModbusEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, definition) -> None:
        super().__init__(coordinator)
        self.definition = definition
        self._attr_name = definition.name
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{definition.key}"
        self._attr_icon = definition.icon
        profile = coordinator.entry.options.get("profile", {})
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
            name=coordinator.entry.title,
            manufacturer=profile.get("manufacturer") or None,
            model=profile.get("model") or None,
            configuration_url=(
                f"homeassistant://universal-modbus?config_entry={coordinator.entry.entry_id}"
            ),
        )

    @property
    def available(self) -> bool:
        """Return whether this entity's own Modbus read succeeded."""
        return (
            super().available
            and self.definition.key not in self.coordinator.entity_errors
        )
