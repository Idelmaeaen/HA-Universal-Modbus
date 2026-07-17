"""Universal Modbus integration."""
from __future__ import annotations

import json
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, PLATFORMS, PROFILE_DIRECTORY, SERVICE_EXPORT_PROFILE
from .coordinator import UniversalModbusCoordinator


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register integration-wide services."""

    async def export_profile(call: ServiceCall) -> None:
        entry_id = call.data["entry_id"]
        filename = call.data.get("filename", f"{entry_id}.json")
        if not filename.endswith(".json") or Path(filename).name != filename:
            raise ValueError("filename must be a plain .json filename")
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN:
            raise ValueError("Unknown Universal Modbus config entry")
        profile = entry.options.get(
            "profile",
            {"schema_version": 1, "name": entry.title, "entities": []},
        )
        directory = Path(hass.config.path(PROFILE_DIRECTORY))
        await hass.async_add_executor_job(directory.mkdir, parents=True, exist_ok=True)
        target = directory / filename
        payload = json.dumps(profile, indent=2, ensure_ascii=False)
        await hass.async_add_executor_job(target.write_text, payload, "utf-8")

    hass.services.async_register(DOMAIN, SERVICE_EXPORT_PROFILE, export_profile)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up one Modbus device."""
    coordinator = UniversalModbusCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload one Modbus device."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_shutdown()
    return unloaded


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
