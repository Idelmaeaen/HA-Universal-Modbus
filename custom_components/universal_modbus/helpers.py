"""Small helpers shared by the Universal Modbus config flow."""

from __future__ import annotations

from collections.abc import Collection
import inspect
import re
import unicodedata


def generate_unique_key(name: str, existing_keys: Collection[str]) -> str:
    """Generate a stable profile key from a display name."""
    normalized = unicodedata.normalize("NFKD", name.casefold())
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    base = re.sub(r"[^a-z0-9]+", "_", ascii_name).strip("_") or "entity"
    candidate = base
    suffix = 2
    while candidate in existing_keys:
        candidate = f"{base}_{suffix}"
        suffix += 1
    return candidate


def modbus_device_parameter(method) -> str:
    """Return the device-address keyword supported by a pymodbus method."""
    return (
        "device_id" if "device_id" in inspect.signature(method).parameters else "slave"
    )
