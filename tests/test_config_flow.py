"""Tests for entity handling in the options flow."""

from __future__ import annotations

import asyncio
from pathlib import Path
import sys
import types

PACKAGE_PATH = Path(__file__).parents[1] / "custom_components" / "universal_modbus"
sys.modules.setdefault("custom_components", types.ModuleType("custom_components"))
package = sys.modules.setdefault(
    "custom_components.universal_modbus",
    types.ModuleType("custom_components.universal_modbus"),
)
package.__path__ = [str(PACKAGE_PATH)]

from custom_components.universal_modbus.config_flow import UniversalModbusOptionsFlow  # noqa: E402


def _schema_keys(schema) -> set[str]:
    return {str(key.schema) for key in schema.schema}


def _flow() -> UniversalModbusOptionsFlow:
    flow = UniversalModbusOptionsFlow()
    flow._profile = lambda: {"defaults": {"byte_order": "big", "word_order": "big"}}
    return flow


def _entity_input(**overrides):
    values = {
        "name": "Status",
        "platform": "sensor",
        "table": "coil",
        "register": 0,
        "data_type": "bool",
        "options_json": '{"0": "Off", "1": "On"}',
        "device_class": "enum",
    }
    values.update(overrides)
    return values


def test_init_exposes_all_options_flow_steps() -> None:
    class TestOptionsFlow(UniversalModbusOptionsFlow):
        @property
        def config_entry(self):
            return types.SimpleNamespace(entry_id="test-entry")

        def async_show_menu(self, **kwargs):
            return kwargs

    flow = TestOptionsFlow()
    flow._profile = lambda: {
        "manufacturer": "Test",
        "model": "Device",
        "description": "Profile",
    }

    result = asyncio.run(flow.async_step_init())

    assert result["step_id"] == "init"
    assert result["menu_options"] == [
        "profile_info",
        "manage_entities",
        "import_profile",
        "export_profile",
    ]


def test_coil_sensor_schema_hides_options_and_enum_device_class() -> None:
    schema = UniversalModbusOptionsFlow._entity_details_schema(_entity_input())

    assert "options_json" not in _schema_keys(schema)
    device_class_validator = next(
        validator
        for key, validator in schema.schema.items()
        if key.schema == "device_class"
    )
    assert "enum" not in device_class_validator.container


def test_coil_sensor_discards_existing_options_and_enum_device_class() -> None:
    entity = _flow()._entity_from_input(
        _entity_input(options_json="not json"), "status"
    )

    assert entity.options == {}
    assert entity.device_class is None


def test_register_sensor_keeps_enum_options() -> None:
    values = _entity_input(table="holding_register", data_type="uint16")
    schema = UniversalModbusOptionsFlow._entity_details_schema(values)
    entity = _flow()._entity_from_input(values, "status")

    assert "options_json" in _schema_keys(schema)
    assert entity.options == {"0": "Off", "1": "On"}
    assert entity.device_class == "enum"


def test_select_and_binary_sensor_options_are_unchanged() -> None:
    select = _entity_input(
        platform="select",
        table="coil",
        options_json='{"Off": 0, "On": 1}',
        device_class="",
    )
    binary_sensor = _entity_input(platform="binary_sensor", device_class="")

    assert _flow()._entity_from_input(select, "mode").options == {"Off": 0, "On": 1}
    assert _flow()._entity_from_input(binary_sensor, "status").options == {
        "0": "Off",
        "1": "On",
    }


def test_advanced_formula_fields_follow_checkbox_and_entity_type() -> None:
    sensor = _entity_input(
        table="holding_register",
        data_type="uint16",
        advanced_calculation=True,
    )
    number = {**sensor, "platform": "number", "device_class": ""}

    sensor_keys = _schema_keys(
        UniversalModbusOptionsFlow._entity_details_schema(sensor)
    )
    number_keys = _schema_keys(
        UniversalModbusOptionsFlow._entity_details_schema(number)
    )

    assert "read_formula" in sensor_keys
    assert "write_formula" not in sensor_keys
    assert {"read_formula", "write_formula"} <= number_keys
    sensor["advanced_calculation"] = False
    assert "read_formula" not in _schema_keys(
        UniversalModbusOptionsFlow._entity_details_schema(sensor)
    )


def test_entity_input_keeps_advanced_formulas() -> None:
    values = _entity_input(
        table="holding_register", data_type="uint16", advanced_calculation=True,
        read_formula="register_value / 10",
    )

    assert _flow()._entity_from_input(values, "status").read_formula == "register_value / 10"
