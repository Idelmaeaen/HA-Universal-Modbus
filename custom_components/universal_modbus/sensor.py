"""Sensor platform for Universal Modbus."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
from .entity import UniversalModbusEntity


DIAGNOSTIC_SENSORS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="last_response_time_ms",
        name="Antwortzeit",
        native_unit_of_measurement=UnitOfTime.MILLISECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:timer-outline",
    ),
    SensorEntityDescription(
        key="communication_error_count",
        name="Kommunikationsfehler",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:alert-circle-outline",
    ),
    SensorEntityDescription(
        key="last_successful_update",
        name="Letzte erfolgreiche Abfrage",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-check-outline",
    ),
)


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    async_add_entities(
        [
            *[
                UniversalModbusSensor(coordinator, item)
                for item in coordinator.entities
                if item.platform == "sensor"
            ],
            *[
                UniversalModbusDiagnosticSensor(coordinator, description)
                for description in DIAGNOSTIC_SENSORS
            ],
        ]
    )


class UniversalModbusSensor(UniversalModbusEntity, SensorEntity):
    def __init__(self, coordinator, definition) -> None:
        super().__init__(coordinator, definition)
        self._attr_native_unit_of_measurement = definition.unit
        self._attr_device_class = definition.device_class
        self._attr_state_class = definition.state_class
        self._attr_suggested_display_precision = definition.display_precision
        if definition.options:
            self._attr_options = list(definition.options.values()) if isinstance(definition.options, dict) else list(definition.options)

    @property
    def native_value(self):
        value = self.coordinator.data.get(self.definition.key)
        if isinstance(self.definition.options, dict):
            return self.definition.options.get(str(value), value)
        return value


class UniversalModbusDiagnosticSensor(SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True

    def __init__(self, coordinator, description: SensorEntityDescription) -> None:
        self.coordinator = coordinator
        self.entity_description = description
        self._attr_name = description.name
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{description.key}"
        self._attr_device_class = description.device_class
        self._attr_native_unit_of_measurement = description.native_unit_of_measurement
        self._attr_state_class = description.state_class
        self._attr_icon = description.icon
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

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.async_add_listener(self.async_write_ha_state)
        )

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self):
        return getattr(self.coordinator, self.entity_description.key)
