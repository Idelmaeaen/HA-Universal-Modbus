"""Data models and validation for Universal Modbus profiles."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .const import PROFILE_SCHEMA_VERSION

SUPPORTED_PLATFORMS = {"sensor", "binary_sensor", "switch", "button", "number", "select"}
SUPPORTED_TABLES = {"coil", "discrete_input", "holding_register", "input_register"}
SUPPORTED_DATA_TYPES = {"bool", "int16", "uint16", "int32", "uint32", "float32"}
SUPPORTED_ORDERS = {"big", "little"}


@dataclass(slots=True)
class ModbusEntityDefinition:
    """One Modbus-backed Home Assistant entity."""

    key: str
    name: str
    platform: str
    table: str
    address: int
    data_type: str = "uint16"
    count: int = 1
    scale: float = 1.0
    offset: float = 0.0
    unit: str | None = None
    device_class: str | None = None
    state_class: str | None = None
    byte_order: str = "big"
    word_order: str = "big"
    writable: bool = False
    feedback_table: str | None = None
    feedback_address: int | None = None
    command_on: int | bool = True
    command_off: int | bool = False
    pulse_ms: int | None = None
    minimum: float = 0.0
    maximum: float = 100.0
    step: float = 1.0
    options: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ModbusEntityDefinition":
        entity = cls(**value)
        if entity.platform not in SUPPORTED_PLATFORMS:
            raise ValueError(f"Unsupported platform: {entity.platform}")
        if entity.table not in SUPPORTED_TABLES:
            raise ValueError(f"Unsupported table: {entity.table}")
        if entity.data_type not in SUPPORTED_DATA_TYPES:
            raise ValueError(f"Unsupported data type: {entity.data_type}")
        if entity.byte_order not in SUPPORTED_ORDERS or entity.word_order not in SUPPORTED_ORDERS:
            raise ValueError("Unsupported byte or word order")
        if entity.address < 0 or entity.count < 1:
            raise ValueError("Address and count are invalid")
        if entity.platform in {"switch", "button", "number", "select"} and not entity.writable:
            raise ValueError(f"Platform {entity.platform} must be writable")
        if entity.feedback_table and entity.feedback_table not in SUPPORTED_TABLES:
            raise ValueError("Unsupported feedback table")
        if entity.platform == "select" and not entity.options:
            raise ValueError("Select entities require options")
        return entity


@dataclass(slots=True)
class ModbusProfile:
    """Portable profile containing a complete device definition."""

    name: str
    manufacturer: str = ""
    model: str = ""
    description: str = ""
    schema_version: int = PROFILE_SCHEMA_VERSION
    defaults: dict[str, Any] = field(default_factory=dict)
    entities: list[ModbusEntityDefinition] = field(default_factory=list)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ModbusProfile":
        version = int(value.get("schema_version", 0))
        if version != PROFILE_SCHEMA_VERSION:
            raise ValueError(f"Unsupported profile schema version: {version}")
        entities = [ModbusEntityDefinition.from_dict(item) for item in value.get("entities", [])]
        keys = [entity.key for entity in entities]
        if len(keys) != len(set(keys)):
            raise ValueError("Entity keys must be unique")
        return cls(
            name=str(value["name"]),
            manufacturer=str(value.get("manufacturer", "")),
            model=str(value.get("model", "")),
            description=str(value.get("description", "")),
            schema_version=version,
            defaults=dict(value.get("defaults", {})),
            entities=entities,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
