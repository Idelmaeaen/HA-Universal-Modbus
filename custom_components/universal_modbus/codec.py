"""Encode and decode Modbus register values."""
from __future__ import annotations

import struct
from typing import Any

from .models import ModbusEntityDefinition

_FORMATS = {
    "int16": "h",
    "uint16": "H",
    "int32": "i",
    "uint32": "I",
    "int64": "q",
    "uint64": "Q",
    "float32": "f",
}


def required_registers(data_type: str) -> int:
    """Return the register width for a supported data type."""
    if data_type in {"int64", "uint64"}:
        return 4
    return 2 if data_type in {"int32", "uint32", "float32"} else 1


def decode_registers(registers: list[int], definition: ModbusEntityDefinition) -> Any:
    """Decode registers and apply scale and offset."""
    if definition.data_type == "bool":
        return bool(registers[0])

    count = required_registers(definition.data_type)
    if len(registers) < count:
        raise ValueError(f"Not enough registers for {definition.data_type}")

    words = list(registers[:count])
    if count > 1 and definition.word_order == "little":
        words.reverse()

    byte_order = "big" if definition.byte_order == "big" else "little"
    payload = b"".join(word.to_bytes(2, byteorder=byte_order, signed=False) for word in words)
    prefix = ">" if definition.byte_order == "big" else "<"
    raw = struct.unpack(prefix + _FORMATS[definition.data_type], payload)[0]
    if definition.data_type != "float32" and definition.scale == 1 and definition.offset == 0:
        return raw
    return raw * definition.scale + definition.offset


def encode_registers(value: Any, definition: ModbusEntityDefinition) -> list[int]:
    """Reverse scale and offset and encode a value for register writes."""
    if definition.data_type == "bool":
        return [1 if bool(value) else 0]

    if definition.data_type != "float32" and definition.scale == 1 and definition.offset == 0:
        raw = int(value)
    else:
        raw = (float(value) - definition.offset) / definition.scale
        if definition.data_type != "float32":
            raw = int(round(raw))

    prefix = ">" if definition.byte_order == "big" else "<"
    payload = struct.pack(prefix + _FORMATS[definition.data_type], raw)
    byte_order = "big" if definition.byte_order == "big" else "little"
    words = [int.from_bytes(payload[index:index + 2], byteorder=byte_order) for index in range(0, len(payload), 2)]
    if len(words) > 1 and definition.word_order == "little":
        words.reverse()
    return words
