"""Tests for dependency-free Universal Modbus helpers."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).parents[1]
PACKAGE_PATH = ROOT / "custom_components" / "universal_modbus"
sys.modules.setdefault("custom_components", types.ModuleType("custom_components"))
package = sys.modules.setdefault(
    "custom_components.universal_modbus", types.ModuleType("custom_components.universal_modbus")
)
package.__path__ = [str(PACKAGE_PATH)]
CONST_SPEC = importlib.util.spec_from_file_location(
    "custom_components.universal_modbus.const", PACKAGE_PATH / "const.py"
)
assert CONST_SPEC is not None and CONST_SPEC.loader is not None
CONST_MODULE = importlib.util.module_from_spec(CONST_SPEC)
sys.modules[CONST_SPEC.name] = CONST_MODULE
CONST_SPEC.loader.exec_module(CONST_MODULE)
MODELS_SPEC = importlib.util.spec_from_file_location(
    "custom_components.universal_modbus.models", PACKAGE_PATH / "models.py"
)
assert MODELS_SPEC is not None and MODELS_SPEC.loader is not None
MODELS = importlib.util.module_from_spec(MODELS_SPEC)
sys.modules[MODELS_SPEC.name] = MODELS
MODELS_SPEC.loader.exec_module(MODELS)
ModbusEntityDefinition = MODELS.ModbusEntityDefinition
HELPERS_PATH = PACKAGE_PATH / "helpers.py"
SPEC = importlib.util.spec_from_file_location("universal_modbus_helpers", HELPERS_PATH)
assert SPEC is not None and SPEC.loader is not None
HELPERS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HELPERS)


class GenerateUniqueKeyTests(unittest.TestCase):
    """Test automatic entity key generation."""

    def test_generates_normalized_key(self) -> None:
        self.assertEqual(HELPERS.generate_unique_key("Kitchen Temperature", set()), "kitchen_temperature")

    def test_transliterates_and_casefolds_name(self) -> None:
        self.assertEqual(HELPERS.generate_unique_key("Straße ÄÖÜ", set()), "strasse_aou")

    def test_adds_first_available_suffix(self) -> None:
        self.assertEqual(HELPERS.generate_unique_key("Temperature", {"temperature", "temperature_2"}), "temperature_3")

    def test_uses_fallback_for_name_without_ascii_characters(self) -> None:
        self.assertEqual(HELPERS.generate_unique_key("温度", set()), "entity")


class ModbusDeviceParameterTests(unittest.TestCase):
    """Test pymodbus device-address keyword compatibility."""

    def test_uses_device_id_for_current_pymodbus(self) -> None:
        def method(address, *, count=1, device_id=1):
            return address, count, device_id

        self.assertEqual(HELPERS.modbus_device_parameter(method), "device_id")

    def test_uses_slave_for_legacy_pymodbus(self) -> None:
        def method(address, *, count=1, slave=1):
            return address, count, slave

        self.assertEqual(HELPERS.modbus_device_parameter(method), "slave")


class ModbusEntityDefinitionTests(unittest.TestCase):
    """Test profile entity field normalization."""

    def test_uses_register_field_for_profile_json(self) -> None:
        entity = ModbusEntityDefinition.from_dict(
            {
                "key": "temperature",
                "name": "Temperature",
                "platform": "sensor",
                "table": "holding_register",
                "register": 0,
            }
        )

        self.assertEqual(entity.to_dict()["register"], 0)
        self.assertNotIn("address", entity.to_dict())

    def test_normalizes_count_from_data_type(self) -> None:
        entity = ModbusEntityDefinition.from_dict(
            {
                "key": "energy",
                "name": "Energy",
                "platform": "sensor",
                "table": "holding_register",
                "register": 12,
                "data_type": "float32",
                "count": 99,
            }
        )

        self.assertEqual(entity.count, 2)

    def test_accepts_legacy_address_field(self) -> None:
        entity = ModbusEntityDefinition.from_dict(
            {
                "key": "temperature",
                "name": "Temperature",
                "platform": "sensor",
                "table": "holding_register",
                "address": 4,
                "feedback_address": 8,
            }
        )

        self.assertEqual(entity.register, 4)
        self.assertEqual(entity.feedback_register, 8)
