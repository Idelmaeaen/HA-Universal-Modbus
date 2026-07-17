"""Encode and decode Modbus values."""
from __future__ import annotations

import struct
from typing import Any

from .models import ModbusEntityDefinition

_FORMATS = {
    "int16": "h",
    "uint16": "H",
    "int32": "i",
    "uint32": "I",
    "float32": "f",
}


def required_registers(data_type: str) -> int:
    return 2 if data_type in {"int32", "uint32", "float32"} else 1


def decode_registers(registers: list[int], definition: ModbusEntityDefinition) -> Any:
    if definition.data_type == "bool":