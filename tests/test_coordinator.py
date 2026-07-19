"""Tests for fault-isolated Modbus polling."""

from __future__ import annotations

import sys
from threading import Lock
from types import MethodType, SimpleNamespace

pymodbus = sys.modules.setdefault("pymodbus", SimpleNamespace())
pymodbus_client = sys.modules.setdefault("pymodbus.client", SimpleNamespace())
pymodbus_client.ModbusTcpClient = object

from custom_components.universal_modbus.coordinator import (  # noqa: E402
    UniversalModbusCoordinator,
    _ReadBatch,
    _ReadItem,
)
from custom_components.universal_modbus.models import ModbusEntityDefinition  # noqa: E402


def _coil(key: str, name: str, register: int) -> ModbusEntityDefinition:
    return ModbusEntityDefinition.from_dict(
        {
            "key": key,
            "name": name,
            "platform": "binary_sensor",
            "table": "coil",
            "register": register,
            "data_type": "bool",
        }
    )


def test_invalid_address_does_not_block_valid_entity() -> None:
    valid = _coil("valid", "Valid coil", 5051)
    invalid = _coil("invalid", "Invalid coil", 5052)
    valid_item = _ReadItem(valid, "coil", 5051, 1)
    invalid_item = _ReadItem(invalid, "coil", 5052, 1)

    coordinator = UniversalModbusCoordinator.__new__(UniversalModbusCoordinator)
    coordinator.entities = [valid, invalid]
    coordinator._read_batches = (
        _ReadBatch("coil", 5051, 2, (valid_item, invalid_item)),
    )
    coordinator._client_lock = Lock()
    coordinator._client = SimpleNamespace(close=lambda: None)
    coordinator.data = {}
    coordinator.entity_errors = {}
    coordinator.last_error = None
    coordinator.communication_error_count = 0
    coordinator.last_response_time_ms = None
    coordinator.last_successful_update = None
    coordinator._ensure_connected = MethodType(lambda self: None, coordinator)

    def read_batch(self, batch):
        if batch.count > 1 or batch.register == 5052:
            raise RuntimeError("IllegalAddress")
        return [1]

    coordinator._read_batch = MethodType(read_batch, coordinator)

    values = coordinator._read_all()

    assert values == {"valid": True}
    assert coordinator.entity_errors == {"invalid": "IllegalAddress"}
    assert "Invalid coil (coil:5052): IllegalAddress" in coordinator.last_error
    assert coordinator.communication_error_count == 1
    assert coordinator.last_successful_update is not None
