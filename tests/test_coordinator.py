"""Tests for fault-isolated Modbus polling."""

from __future__ import annotations

import asyncio
import sys
from threading import Lock
from types import MethodType, SimpleNamespace

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed

pymodbus = sys.modules.setdefault("pymodbus", SimpleNamespace())
pymodbus_client = sys.modules.setdefault("pymodbus.client", SimpleNamespace())
pymodbus_client.ModbusTcpClient = object

from custom_components.universal_modbus.coordinator import (  # noqa: E402
    UniversalModbusCoordinator,
    _ReadBatch,
    _ReadItem,
)
from custom_components.universal_modbus.models import ModbusEntityDefinition  # noqa: E402


def _coil(key: str, name: str, register: int, **overrides) -> ModbusEntityDefinition:
    return ModbusEntityDefinition.from_dict(
        {
            "key": key,
            "name": name,
            "platform": "binary_sensor",
            "table": "coil",
            "register": register,
            "data_type": "bool",
            **overrides,
        }
    )


def test_invalid_address_does_not_block_valid_entity() -> None:
    valid = _coil("valid", "Valid coil", 5051)
    invalid = _coil("invalid", "Invalid coil", 5052)
    valid_item = _ReadItem(valid, "coil", 5051, 1)
    invalid_item = _ReadItem(invalid, "coil", 5052, 1)

    coordinator = UniversalModbusCoordinator.__new__(UniversalModbusCoordinator)
    coordinator.entities = [valid, invalid]
    coordinator._slave = 10
    batches = [_ReadBatch("coil", 5051, 2, (valid_item, invalid_item), 10)]
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
        assert batch.unit_id == 10
        if batch.count > 1 or batch.register == 5052:
            raise RuntimeError("IllegalAddress")
        return [1]

    coordinator._read_batch = MethodType(read_batch, coordinator)

    values = coordinator._read_all(batches)

    assert values == {"valid": True}
    assert coordinator.entity_errors == {"invalid": "IllegalAddress"}
    assert "Invalid coil (coil:5052): IllegalAddress" in coordinator.last_error
    assert coordinator.communication_error_count == 1
    assert coordinator.last_successful_update is not None


class _WriteResponse:
    def isError(self) -> bool:
        return False


class _WriteClient:
    def __init__(self) -> None:
        self.calls = []

    def close(self) -> None:
        pass

    def _record(self, method, *args, **kwargs):
        self.calls.append((method, args, kwargs))
        return _WriteResponse()

    def write_coil(self, *args, **kwargs):
        return self._record("write_coil", *args, **kwargs)

    def write_coils(self, *args, **kwargs):
        return self._record("write_coils", *args, **kwargs)

    def write_register(self, *args, **kwargs):
        return self._record("write_register", *args, **kwargs)

    def write_registers(self, *args, **kwargs):
        return self._record("write_registers", *args, **kwargs)

    def read_coils(self, address, *, count, device_id):
        self._record("read_coils", address, count, device_id)
        return SimpleNamespace(isError=lambda: False, bits=[False] * count)


def _write_coordinator() -> UniversalModbusCoordinator:
    coordinator = UniversalModbusCoordinator.__new__(UniversalModbusCoordinator)
    coordinator._client_lock = Lock()
    coordinator._client = _WriteClient()
    coordinator._slave = 10
    coordinator._device_id_parameter = "device_id"
    coordinator._ensure_connected = MethodType(lambda self: None, coordinator)
    return coordinator


def _polling_coordinator(entities):
    coordinator = _write_coordinator()
    coordinator._operation_lock = asyncio.Lock()
    coordinator.entities = entities
    coordinator.data = {}
    coordinator.entity_errors = {}
    coordinator.communication_error_count = 0
    coordinator.last_update_success = True
    coordinator._scan_interval = 5
    coordinator._read_batches = coordinator._build_read_batches()
    coordinator._next_poll = dict.fromkeys(coordinator._read_batches, 0)
    coordinator._force_refresh = False
    coordinator.updates = []
    coordinator.async_update_listeners = lambda: coordinator.updates.append(coordinator.data)

    async def run_job(job, *args):
        return job(*args)

    coordinator.hass = SimpleNamespace(
        loop=SimpleNamespace(time=lambda: 100.95), async_add_executor_job=run_job
    )
    return coordinator


@pytest.mark.parametrize(
    ("table", "data_type", "write_mode", "value", "method", "payload"),
    [
        ("coil", "bool", "auto", True, "write_coil", True),
        ("coil", "bool", "single", True, "write_coil", True),
        ("coil", "bool", "multiple", True, "write_coils", [True]),
        ("holding_register", "uint16", "auto", 7, "write_register", 7),
        ("holding_register", "uint16", "single", 7, "write_register", 7),
        ("holding_register", "uint16", "multiple", 7, "write_registers", [7]),
        ("holding_register", "uint32", "auto", 7, "write_registers", [0, 7]),
    ],
)
def test_write_mode_selects_modbus_function(
    table, data_type, write_mode, value, method, payload
) -> None:
    definition = ModbusEntityDefinition.from_dict(
        {
            "key": "command",
            "name": "Command",
            "platform": "switch" if table == "coil" else "number",
            "table": table,
            "register": 19,
            "data_type": data_type,
            "writable": True,
            "write_mode": write_mode,
        }
    )
    coordinator = _write_coordinator()

    coordinator._write_value(definition, value)

    assert coordinator._client.calls == [
        (method, (19, payload), {"device_id": 10})
    ]


def test_polling_batches_use_unit_ids_and_independent_intervals() -> None:
    coordinator = _polling_coordinator(
        [
            _coil("first", "First", 10),
            _coil("second", "Second", 11, unit_id=10, scan_interval=5),
            _coil("other_unit", "Other unit", 10, unit_id=0),
            _coil("fast", "Fast", 11, unit_id=255, scan_interval=2),
        ]
    )

    async def poll():
        coordinator.data = await coordinator._async_update_data()
        assert coordinator._client.calls == [
            ("read_coils", (10, 2, 10), {}),
            ("read_coils", (10, 1, 0), {}),
            ("read_coils", (11, 1, 255), {}),
        ]
        coordinator._client.calls.clear()
        coordinator.hass.loop.time = lambda: 102.05
        coordinator.entity_errors["other_unit"] = "Previous read failed"
        coordinator.data = await coordinator._async_update_data()
        assert coordinator._client.calls == [("read_coils", (11, 1, 255), {})]
        assert len(coordinator.data) == 4
        assert coordinator.entity_errors == {"other_unit": "Previous read failed"}
        assert coordinator.update_interval.total_seconds() == 2

    asyncio.run(poll())


@pytest.mark.parametrize("confirmation", [True, False])
def test_write_publishes_feedback_or_ack_without_polling_other_entities(confirmation) -> None:
    command = _coil(
        "command", "Command", 19, platform="switch", writable=True, unit_id=255,
        feedback_table="coil", feedback_register=0, write_confirmation=confirmation,
    )
    coordinator = _polling_coordinator([command, _coil("other", "Other", 88)])
    coordinator.data = {"other": True}

    asyncio.run(coordinator.async_write_value(command, True))

    expected_calls = [("write_coil", (19, True), {"device_id": 255})]
    if confirmation:
        expected_calls.append(("read_coils", (0, 1, 255), {}))
    assert coordinator._client.calls == expected_calls
    assert coordinator.updates == [{"other": True, "command": not confirmation}]
    assert coordinator._next_poll == {5: 0}


def test_failed_feedback_preserves_last_value_and_reports_acknowledgement() -> None:
    command = _coil(
        "command", "Command", 19, platform="switch", writable=True,
        feedback_table="coil", feedback_register=0,
    )
    coordinator = _polling_coordinator([command])
    coordinator.data = {"command": False}

    def read_coils(*args, **kwargs):
        raise RuntimeError("Read timeout")

    coordinator._client.read_coils = read_coils
    with pytest.raises(UpdateFailed, match="write acknowledged.*feedback failed"):
        asyncio.run(coordinator.async_write_value(command, True))
    assert coordinator._client.calls == [
        ("write_coil", (19, True), {"device_id": 10}),
    ]
    assert coordinator.data == {"command": False}
    assert coordinator.entity_errors == {"command": "Read timeout"}


def test_pulse_reads_feedback_only_after_off_command() -> None:
    command = _coil(
        "command", "Command", 19, platform="toggle_switch", writable=True,
        pulse_ms=1, feedback_table="coil", feedback_register=0,
    )
    coordinator = _polling_coordinator([command])

    asyncio.run(coordinator.async_pulse(command))

    assert coordinator._client.calls == [
        ("write_coil", (19, True), {"device_id": 10}),
        ("write_coil", (19, False), {"device_id": 10}),
        ("read_coils", (0, 1, 10), {}),
    ]
    assert coordinator.updates == [{"command": False}]
