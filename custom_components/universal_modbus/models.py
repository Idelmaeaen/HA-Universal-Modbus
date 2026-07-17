"""Data models and validation for Universal Modbus profiles."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .const import PROFILE_SCHEMA_VERSION

SUPPORTED_PLATFORMS = {"sensor", "binary_sensor", "switch", "button", "number", "select"}
SUPPORTED_TABLES = {"coil", "discrete_input", "holding_register", "input_register"}


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
    writable: bool = False
    feedback_table: str | None = None
    feedback_address: int | None = None
    command_on: int | bool = True
    command_off: int | bool = False
    pulse_ms: int | None = None
    options: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ModbusEntityDefinition":
        entity = cls(**value)
        if entity.platform not in SUPPORTED_PLATFORMS:
            raise ValueError(f"Unsupported platform: {entity.platform}")
        if entity.table not in SUPPORTED_TABLES:
            raise ValueError(f"Unsupported table: {entity.table}")
        if entity.address < 0 or entity.count < 1:
            raise ValueError("Address and count are invalid")
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
