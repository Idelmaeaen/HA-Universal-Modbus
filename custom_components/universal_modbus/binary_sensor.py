"""Binary sensor platform for Universal Modbus."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.const import CONF_HOST, CONF_PORT, EntityCategory
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .entity import UniversalModbusEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    async_add_entities(
        [
            *[
                UniversalModbusBinarySensor(coordinator, item)
                for item in coordinator.entities
                if item.platform == "binary_sensor"
            ],
            UniversalModbusDeviceStatusSensor(coordinator),
        ]
    )


class UniversalModbusBinarySensor(UniversalModbusEntity, BinarySensorEntity):
    def __init__(self, coordinator, definition) -> None:
        super().__init__(coordinator, definition)
        self._attr_device_class = definition.device_class

    @property
    def is_on(self):
        return bool(self.coordinator.data.get(self.definition.key))


class UniversalModbusDeviceStatusSensor(BinarySensorEntity):
    """Diagnostic binary sensor reporting the overall communication health.

    ``on`` means the hub is communicating normally, ``off`` means the last
    polling cycle failed (device offline). It intentionally stays available
    when the device is offline so the failure is visible in the UI.
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True
    _attr_translation_key = "device_status"
    _attr_icon = "mdi:lan-connect"

    def __init__(self, coordinator) -> None:
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry.entry_id}_device_status"
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
        # Remain available when offline so the "device offline" state is shown.
        return True

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.last_update_success)

    @staticmethod
    def _format_time(value) -> str | None:
        if value is None:
            return None
        return dt_util.as_local(value).isoformat(timespec="seconds")

    @property
    def extra_state_attributes(self):
        coordinator = self.coordinator
        entry = coordinator.entry
        return {
            "requests_sent": coordinator.requests_sent,
            "responses_received": coordinator.responses_received,
            "last_successful_update": self._format_time(
                coordinator.last_successful_update
            ),
            "host": entry.data.get(CONF_HOST),
            "port": int(entry.data.get(CONF_PORT, 502)),
            "communication_ok": bool(coordinator.last_update_success),
            "last_error_time": self._format_time(coordinator.last_error_time),
            "last_error": coordinator.last_error,
            "communication_error_count": coordinator.communication_error_count,
        }
