"""Data models and validation for Universal Modbus profiles."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .const import PROFILE_SCHEMA_VERSION

SUPPORTED_PLATFORMS = {"sensor", "binary_sensor", "switch", "toggle_switch", "button", "number", "select"}
SUPPORTED_TABLES = {"coil", "discrete_input", "holding_register", "input_register"}
SUPPORTED_DATA_TYPES = {"bool", "int16", "uint16", "int32", "uint32", "int64", "uint64", "float32"}
SUPPORTED_ORDERS = {"big", "little"}


def automatic_count_for_data_type(data_type: str) -> int:
    """Return the fixed bit/register width for a supported data type."""
    if data_type in {"int64", "uint64"}:
        return 4
    return 2 if data_type in {"int32", "uint32", "float32"} else 1


@dataclass(slots=True)
class ModbusEntityDefinition:
    """One Modbus-backed Home Assistant entity."""

    key: str
    name: str
    platform: str
    table: str
    register: int
    data_type: str = "int16"
    count: int = 1
    scale: float = 1.0
    offset: float = 0.0
    unit: str | None = None
    icon: str | None = None
    device_class: str | None = None
    state_class: str | None = None
    display_precision: int | None = None
    byte_order: str = "big"
    word_order: str = "big"
    writable: bool = False
    feedback_table: str | None = None
    feedback_register: int | None = None
    command_on: int | bool = True
    command_off: int | bool = False
    pulse_ms: int | None = None
    minimum: float = 0.0
    maximum: float = 100.0
    step: float = 1.0
    options: dict[str, int | str] | list[str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ModbusEntityDefinition":
        normalized = dict(value)
        if "register" not in normalized and "address" in normalized:
            normalized["register"] = normalized.pop("address")
        else:
            normalized.pop("address", None)
        if "feedback_register" not in normalized and "feedback_address" in normalized:
            normalized["feedback_register"] = normalized.pop("feedback_address")
        else:
            normalized.pop("feedback_address", None)
        entity = cls(**normalized)
        if entity.platform not in SUPPORTED_PLATFORMS:
            raise ValueError(f"Unsupported platform: {entity.platform}")
        if entity.table not in SUPPORTED_TABLES:
            raise ValueError(f"Unsupported table: {entity.table}")
        if entity.data_type not in SUPPORTED_DATA_TYPES:
            raise ValueError(f"Unsupported data type: {entity.data_type}")
        if entity.table in {"coil", "discrete_input"} and entity.data_type != "bool":
            raise ValueError(f"Table {entity.table} only supports bool data")
        if entity.byte_order not in SUPPORTED_ORDERS or entity.word_order not in SUPPORTED_ORDERS:
            raise ValueError("Unsupported byte or word order")
        if entity.register < 0:
            raise ValueError("Register is invalid")
        entity.count = automatic_count_for_data_type(entity.data_type)
        if entity.display_precision is not None and not 0 <= entity.display_precision <= 6:
            raise ValueError("Display precision must be between 0 and 6")
        if entity.feedback_table and entity.feedback_table not in SUPPORTED_TABLES:
            raise ValueError("Unsupported feedback table")
        if entity.platform == "toggle_switch" and not entity.pulse_ms:
            raise ValueError("Toggle switches require a positive pulse duration")
        if entity.platform == "select" and not entity.options:
            raise ValueError("Select entities require options")
        if entity.platform == "select" and not isinstance(entity.options, dict):
            raise ValueError("Select options must be an object")
        if entity.options and entity.platform in {"sensor", "binary_sensor"} and not isinstance(entity.options, (dict, list)):
            raise ValueError("Sensor options must be an object or list")
        if entity.options and entity.platform == "sensor":
            if entity.device_class != "enum":
                raise ValueError("Sensor options require enum device class")
            if entity.state_class or entity.unit:
                raise ValueError("Sensor options cannot be combined with state class or unit")
        return entity

    def to_dict(self) -> dict[str, Any]:
        """Serialize the entity definition for config entry options."""
        return asdict(self)


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
        defaults = dict(value.get("defaults", {}))
        for order in ("byte_order", "word_order"):
            if order in defaults and defaults[order] not in SUPPORTED_ORDERS:
                raise ValueError(f"Unsupported profile default: {order}")
        keys = [entity.key for entity in entities]
        if len(keys) != len(set(keys)):
            raise ValueError("Entity keys must be unique")
        return cls(
            name=str(value["name"]),
            manufacturer=str(value.get("manufacturer", "")),
            model=str(value.get("model", "")),
            description=str(value.get("description", "")),
            schema_version=version,
            defaults=defaults,
            entities=entities,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
