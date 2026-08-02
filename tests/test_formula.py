"""Tests for safe per-entity calculation formulas."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types

import pytest

ROOT = Path(__file__).parents[1]
PACKAGE_PATH = ROOT / "custom_components" / "universal_modbus"
sys.modules.setdefault("custom_components", types.ModuleType("custom_components"))
package = sys.modules.setdefault(
    "custom_components.universal_modbus",
    types.ModuleType("custom_components.universal_modbus"),
)
package.__path__ = [str(PACKAGE_PATH)]


def _load_module(name: str):
    full_name = f"custom_components.universal_modbus.{name}"
    if full_name in sys.modules:
        return sys.modules[full_name]
    spec = importlib.util.spec_from_file_location(
        full_name, PACKAGE_PATH / f"{name}.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = module
    spec.loader.exec_module(module)
    return module


_load_module("const")
FORMULA = _load_module("formula")
MODELS = _load_module("models")
CODEC = _load_module("codec")
FormulaError = FORMULA.FormulaError
evaluate_formula = FORMULA.evaluate_formula
validate_formula = FORMULA.validate_formula
ModbusEntityDefinition = MODELS.ModbusEntityDefinition
decode_registers = CODEC.decode_registers
encode_registers = CODEC.encode_registers


def _definition(**overrides) -> ModbusEntityDefinition:
    values = {
        "key": "temperature",
        "name": "Temperature",
        "platform": "number",
        "table": "holding_register",
        "register": 0,
        "data_type": "uint16",
        "writable": True,
    }
    values.update(overrides)
    return ModbusEntityDefinition.from_dict(values)


def test_conditional_read_formula() -> None:
    expression = "None if register_value == 65535 else register_value / 10"

    assert evaluate_formula(expression, "register_value", 250, scale=1, offset=0) == 25
    assert (
        evaluate_formula(expression, "register_value", 65535, scale=1, offset=0) is None
    )


def test_formula_supports_documented_functions() -> None:
    result = evaluate_formula(
        "round(max(register_value, 0) * scale + offset, 2)",
        "register_value",
        12.345,
        scale=0.5,
        offset=1,
    )

    assert result == 7.17


@pytest.mark.parametrize(
    "expression",
    [
        '__import__("os")',
        "register_value.real",
        "register_value[0]",
        "value + 1",
    ],
)
def test_read_formula_rejects_unsafe_or_unknown_elements(expression: str) -> None:
    with pytest.raises(FormulaError):
        validate_formula(expression, "register_value")


def test_model_validates_enabled_formulas() -> None:
    with pytest.raises(FormulaError):
        _definition(advanced_calculation=True, read_formula="unknown + 1")


def test_codec_uses_advanced_read_and_write_formulas() -> None:
    definition = _definition(
        advanced_calculation=True,
        read_formula="register_value / 2",
        write_formula="value * 2",
    )

    assert decode_registers([200], definition) == 100
    assert encode_registers(100, definition) == [200]


def test_disabled_advanced_calculation_keeps_scale_and_offset_behavior() -> None:
    definition = _definition(scale=0.5, offset=2)

    assert decode_registers([200], definition) == 102
    assert encode_registers(102, definition) == [200]
