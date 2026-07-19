"""Frontend panel and WebSocket API for Universal Modbus administration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant import config_entries, const as ha_const
from homeassistant.components import panel_custom, websocket_api
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.button import ButtonDeviceClass
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.number import NumberDeviceClass
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.components.switch import SwitchDeviceClass
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ENTITIES,
    CONF_SCAN_INTERVAL,
    CONF_SLAVE,
    CONF_TIMEOUT,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SLAVE,
    DEFAULT_TIMEOUT,
    DOMAIN,
    PROFILE_SCHEMA_VERSION,
)
from .helpers import generate_unique_key
from .models import ModbusEntityDefinition, ModbusProfile

PANEL_URL = "universal-modbus"
STATIC_URL = "/universal_modbus_static"
BRAND_STATIC_URL = "/universal_modbus_brand"
MANIFEST_VERSION = json.loads(
    (Path(__file__).parent / "manifest.json").read_text(encoding="utf-8")
)["version"]
HUB_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): str,
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(
            int, vol.Range(min=1, max=65535)
        ),
        vol.Required(CONF_SLAVE, default=DEFAULT_SLAVE): vol.All(
            int, vol.Range(min=0, max=247)
        ),
        vol.Required(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
            int, vol.Range(min=1)
        ),
        vol.Required(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): vol.All(
            int, vol.Range(min=1)
        ),
    }
)


async def async_setup_frontend(hass: HomeAssistant) -> None:
    """Register the administration panel and API."""
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                STATIC_URL, str(Path(__file__).parent / "frontend"), False
            ),
            StaticPathConfig(
                BRAND_STATIC_URL, str(Path(__file__).parent / "brand"), False
            ),
        ]
    )
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL,
        webcomponent_name="universal-modbus-panel",
        sidebar_title="Universal Modbus",
        sidebar_icon="mdi:cable-data",
        module_url=f"{STATIC_URL}/profile-editor.js?v={MANIFEST_VERSION}",
        require_admin=True,
    )
    for command in (
        websocket_get_editor_data,
        websocket_save_profile,
        websocket_write_value,
        websocket_save_hub,
        websocket_delete_hub,
        websocket_cleanup_entities,
    ):
        websocket_api.async_register_command(hass, command)


def _enum_values(enum_type) -> list[str]:
    return sorted(item.value for item in enum_type)


def _units() -> list[str]:
    units = {ha_const.PERCENTAGE}
    for name in dir(ha_const):
        if name.startswith("UnitOf"):
            try:
                units.update(item.value for item in getattr(ha_const, name))
            except TypeError:
                pass
    return sorted(units)


def _entry_profile(entry) -> dict[str, Any]:
    entities = [
        ModbusEntityDefinition.from_dict(dict(item)).to_dict()
        for item in entry.options.get(CONF_ENTITIES, [])
    ]
    profile = dict(entry.options.get("profile", {}))
    profile.setdefault("schema_version", PROFILE_SCHEMA_VERSION)
    profile.setdefault("name", entry.title)
    profile.setdefault("manufacturer", "")
    profile.setdefault("model", "")
    profile.setdefault("description", "")
    profile.setdefault("defaults", {"byte_order": "big", "word_order": "big"})
    profile["entities"] = entities
    return profile


def _validated_profile(raw: dict[str, Any]) -> dict[str, Any]:
    profile = dict(raw)
    entities = [dict(item) for item in profile.get("entities", [])]
    existing: set[str] = set()
    defaults = dict(profile.get("defaults", {}))
    defaults.setdefault("byte_order", "big")
    defaults.setdefault("word_order", "big")
    profile["defaults"] = defaults
    for entity in entities:
        key = entity.get("key") or generate_unique_key(
            str(entity.get("name", "")), existing
        )
        if key in existing:
            raise ValueError(f"Duplicate key: {key}")
        entity["key"] = key
        entity["byte_order"] = defaults["byte_order"]
        entity["word_order"] = defaults["word_order"]
        existing.add(key)
    profile["entities"] = entities
    return ModbusProfile.from_dict(profile).to_dict()


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/editor/get"})
@websocket_api.require_admin
@callback
def websocket_get_editor_data(hass, connection, msg) -> None:
    """Return hubs, profiles, current values, and editor metadata."""
    entries = []
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)
    for entry in hass.config_entries.async_entries(DOMAIN):
        coordinator = getattr(entry, "runtime_data", None)
        values = dict(getattr(coordinator, "data", None) or {})
        client = getattr(coordinator, "_client", None)
        device = device_registry.async_get_device(
            identifiers={(DOMAIN, entry.entry_id)}
        )
        entity_ids = {
            registry_entry.unique_id.removeprefix(f"{entry.entry_id}_"): registry_entry.entity_id
            for registry_entry in er.async_entries_for_config_entry(
                entity_registry, entry.entry_id
            )
            if registry_entry.unique_id.startswith(f"{entry.entry_id}_")
        }
        last_update_success = bool(getattr(coordinator, "last_update_success", False))
        error = getattr(coordinator, "last_error", None)
        if not error and not last_update_success:
            error = getattr(coordinator, "last_exception", None) or getattr(
                entry, "reason", None
            )
        entries.append(
            {
                "entry_id": entry.entry_id,
                "device_id": device.id if device else None,
                "entity_ids": entity_ids,
                "title": entry.title,
                "hub": dict(entry.data),
                "profile": _entry_profile(entry),
                "values": values,
                "connected": bool(getattr(client, "connected", False)),
                "last_update_success": last_update_success,
                "error": str(error) if error else None,
                "entity_errors": dict(getattr(coordinator, "entity_errors", {}) or {}),
                "last_response_time_ms": getattr(
                    coordinator, "last_response_time_ms", None
                ),
                "communication_error_count": getattr(
                    coordinator, "communication_error_count", 0
                ),
                "last_successful_update": dt_util.as_local(
                    last_successful_update
                ).isoformat()
                if (
                    last_successful_update := getattr(
                        coordinator, "last_successful_update", None
                    )
                )
                else None,
            }
        )
    connection.send_result(
        msg["id"],
        {
            "entries": entries,
            "device_classes": {
                "sensor": _enum_values(SensorDeviceClass),
                "binary_sensor": _enum_values(BinarySensorDeviceClass),
                "number": _enum_values(NumberDeviceClass),
                "switch": _enum_values(SwitchDeviceClass),
                "toggle_switch": _enum_values(SwitchDeviceClass),
                "button": _enum_values(ButtonDeviceClass),
                "select": [],
            },
            "state_classes": _enum_values(SensorStateClass),
            "units": _units(),
            "version": MANIFEST_VERSION,
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/editor/save",
        vol.Required("entry_id"): str,
        vol.Required("profile"): dict,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_save_profile(hass, connection, msg) -> None:
    """Validate and save a complete profile."""
    entry = hass.config_entries.async_get_entry(msg["entry_id"])
    if entry is None or entry.domain != DOMAIN:
        connection.send_error(msg["id"], "entry_not_found", "Unknown config entry")
        return
    try:
        profile = _validated_profile(msg["profile"])
    except (KeyError, TypeError, ValueError) as err:
        connection.send_error(msg["id"], "invalid_profile", str(err))
        return
    options = dict(entry.options)
    options[CONF_ENTITIES] = profile["entities"]
    options["profile"] = profile
    hass.config_entries.async_update_entry(entry, options=options)
    connection.send_result(msg["id"], {"profile": profile})


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/editor/write",
        vol.Required("entry_id"): str,
        vol.Required("key"): str,
        vol.Optional("value"): object,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_write_value(hass, connection, msg) -> None:
    """Write a value through a writable profile entity."""
    entry = hass.config_entries.async_get_entry(msg["entry_id"])
    if entry is None or entry.domain != DOMAIN:
        connection.send_error(msg["id"], "entry_not_found", "Unknown config entry")
        return
    coordinator = getattr(entry, "runtime_data", None)
    definition = (
        next((item for item in coordinator.entities if item.key == msg["key"]), None)
        if coordinator
        else None
    )
    if definition is None or not definition.writable:
        connection.send_error(msg["id"], "not_writable", "Entity is not writable")
        return
    try:
        if definition.platform in {"button", "toggle_switch"}:
            if definition.pulse_ms:
                await coordinator.async_pulse(definition)
            else:
                await coordinator.async_write_value(definition, definition.command_on)
        elif definition.platform == "switch":
            value = (
                definition.command_on
                if bool(msg.get("value"))
                else definition.command_off
            )
            await coordinator.async_write_value(definition, value)
        elif definition.platform == "number":
            value = float(msg["value"])
            if not definition.minimum <= value <= definition.maximum:
                raise ValueError("Value is outside the configured range")
            await coordinator.async_write_value(definition, value)
        elif definition.platform == "select":
            await coordinator.async_write_value(
                definition, definition.options[str(msg["value"])]
            )
        else:
            raise ValueError("Unsupported writable platform")
    except (KeyError, TypeError, ValueError) as err:
        connection.send_error(msg["id"], "invalid_value", str(err))
        return
    connection.send_result(msg["id"])


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/hub/save",
        vol.Optional("entry_id"): str,
        vol.Required("hub"): dict,
        vol.Required("profile"): dict,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_save_hub(hass, connection, msg) -> None:
    """Create or update a Modbus hub and its profile metadata."""
    try:
        hub = HUB_SCHEMA(msg["hub"])
        profile = _validated_profile(msg["profile"])
    except (KeyError, TypeError, ValueError, vol.Invalid) as err:
        connection.send_error(msg["id"], "invalid_hub", str(err))
        return
    unique_id = f"{hub[CONF_HOST]}:{hub[CONF_PORT]}:{hub[CONF_SLAVE]}"
    entry_id = msg.get("entry_id")
    for other in hass.config_entries.async_entries(DOMAIN):
        if other.entry_id != entry_id and other.unique_id == unique_id:
            connection.send_error(msg["id"], "already_configured", "Hub already exists")
            return
    if entry_id:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN:
            connection.send_error(msg["id"], "entry_not_found", "Unknown config entry")
            return
        options = dict(entry.options)
        options[CONF_ENTITIES] = profile["entities"]
        options["profile"] = profile
        hass.config_entries.async_update_entry(
            entry, title=hub[CONF_NAME], data=hub, options=options, unique_id=unique_id
        )
    else:
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data=hub,
        )
        if result["type"] != FlowResultType.CREATE_ENTRY:
            connection.send_error(
                msg["id"], "create_failed", str(result.get("reason", result["type"]))
            )
            return
        entry = result["result"]
        hass.config_entries.async_update_entry(
            entry,
            options={CONF_ENTITIES: profile["entities"], "profile": profile},
        )
    connection.send_result(msg["id"], {"entry_id": entry.entry_id})


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/hub/delete",
        vol.Required("entry_id"): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_delete_hub(hass, connection, msg) -> None:
    """Delete a Universal Modbus config entry."""
    entry = hass.config_entries.async_get_entry(msg["entry_id"])
    if entry is None or entry.domain != DOMAIN:
        connection.send_error(msg["id"], "entry_not_found", "Unknown config entry")
        return
    await hass.config_entries.async_remove(entry.entry_id)
    connection.send_result(msg["id"])


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/hub/cleanup_entities",
        vol.Required("entry_id"): str,
    }
)
@websocket_api.require_admin
@callback
def websocket_cleanup_entities(hass, connection, msg) -> None:
    """Remove registry entities that are no longer part of the hub profile."""
    entry = hass.config_entries.async_get_entry(msg["entry_id"])
    if entry is None or entry.domain != DOMAIN:
        connection.send_error(msg["id"], "entry_not_found", "Unknown config entry")
        return
    current_unique_ids = {
        f"{entry.entry_id}_{definition['key']}"
        for definition in _entry_profile(entry)["entities"]
    }
    registry = er.async_get(hass)
    stale_entities = [
        entity
        for entity in er.async_entries_for_config_entry(registry, entry.entry_id)
        if entity.unique_id not in current_unique_ids
    ]
    for entity in stale_entities:
        registry.async_remove(entity.entity_id)
    connection.send_result(
        msg["id"],
        {
            "removed": len(stale_entities),
            "entity_ids": [entity.entity_id for entity in stale_entities],
        },
    )
