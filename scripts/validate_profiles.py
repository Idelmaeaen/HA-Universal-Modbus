"""Validate all published Universal Modbus profiles."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType


ROOT = Path(__file__).resolve().parents[1]
PROFILE_DIRECTORY = ROOT / "profiles"
INTEGRATION_DIRECTORY = ROOT / "custom_components" / "universal_modbus"


def _load_profile_model():
    """Load the profile model without importing Home Assistant dependencies."""
    package_name = "custom_components.universal_modbus"
    package = ModuleType(package_name)
    package.__path__ = [str(INTEGRATION_DIRECTORY)]
    sys.modules[package_name] = package

    for module_name in ("const", "models"):
        qualified_name = f"{package_name}.{module_name}"
        spec = importlib.util.spec_from_file_location(
            qualified_name, INTEGRATION_DIRECTORY / f"{module_name}.py"
        )
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Could not load {qualified_name}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[qualified_name] = module
        spec.loader.exec_module(module)

    return sys.modules[f"{package_name}.models"].ModbusProfile


def validate_profile(path: Path, profile_model) -> None:
    """Validate one profile file."""
    with path.open(encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError("Profile root must be a JSON object")

    if "profile" in data:
        if not isinstance(data["profile"], dict):
            raise ValueError("Exported profile must be a JSON object")
        if "host" in data.get("hub", {}):
            raise ValueError("Published hub exports must not contain a host")
        if "exported_by" in data.get("metadata", {}):
            raise ValueError("Published hub exports must not contain exported_by")
        data = data["profile"]

    # Older bit-table profiles omitted data_type because bool is implicit.
    for entity in data.get("entities", []):
        if entity.get("table") in {"coil", "discrete_input"}:
            entity.setdefault("data_type", "bool")

    profile = profile_model.from_dict(data)
    if not profile.name.strip():
        raise ValueError("Profile name must not be empty")
    if not profile.manufacturer.strip():
        raise ValueError("Manufacturer must not be empty")
    if not profile.model.strip():
        raise ValueError("Model must not be empty")
    if not profile.entities:
        raise ValueError("Profile must contain at least one entity")


def main() -> int:
    """Validate every JSON profile and return a process exit code."""
    profile_files = sorted(PROFILE_DIRECTORY.rglob("*.json"))
    if not profile_files:
        print("ERROR: No profiles found.", file=sys.stderr)
        return 1

    profile_model = _load_profile_model()
    failed = False
    for path in profile_files:
        relative_path = path.relative_to(ROOT)
        try:
            validate_profile(path, profile_model)
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as error:
            failed = True
            print(f"ERROR: {relative_path}: {error}", file=sys.stderr)
        else:
            print(f"OK: {relative_path}")

    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
