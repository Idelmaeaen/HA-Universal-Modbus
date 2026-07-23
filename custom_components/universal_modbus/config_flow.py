"""Config flow for Universal Modbus."""
from __future__ import annotations

import json
from typing import Any

import voluptuous as vol
from homeassistant import config_entries, const as ha_const
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.button import ButtonDeviceClass
from homeassistant.components.number import NumberDeviceClass
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.components.switch import SwitchDeviceClass
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig

from .const import (
    CONF_ENTITIES,
    CONF_PROFILE_JSON,
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
from .models import ModbusEntityDefinition, ModbusProfile, automatic_count_for_data_type

PLATFORMS = ["sensor", "binary_sensor", "switch", "toggle_switch", "button", "number", "select"]
TABLES = ["coil", "discrete_input", "holding_register", "input_register"]
DATA_TYPES = ["bool", "int16", "uint16", "int32", "uint32", "int64", "uint64", "float32"]
ORDERS = ["big", "little"]
WRITABLE_PLATFORMS = {"switch", "toggle_switch", "button", "number", "select"}
DEVICE_CLASSES_BY_PLATFORM = {
    "sensor": {item.value for item in SensorDeviceClass},
    "binary_sensor": {item.value for item in BinarySensorDeviceClass},
    "number": {item.value for item in NumberDeviceClass},
    "switch": {item.value for item in SwitchDeviceClass},
    "toggle_switch": {item.value for item in SwitchDeviceClass},
    "button": {item.value for item in ButtonDeviceClass},
    "select": set(),
}
STATE_CLASSES = sorted(item.value for item in SensorStateClass)
FEEDBACK_TABLE_OPTIONS = {
    "": "None",
    "coil": "coil",
    "discrete_input": "discrete_input",
    "holding_register": "holding_register",
    "input_register": "input_register",
}


def _home_assistant_units() -> list[str]:
    """Collect units exposed by Home Assistant's UnitOf* enums."""
    units = {ha_const.PERCENTAGE}
    for name in dir(ha_const):
        if not name.startswith("UnitOf"):
            continue
        enum = getattr(ha_const, name)
        try:
            units.update(item.value for item in enum)
        except TypeError:
            continue
    return sorted(units)


UNIT_OPTIONS = _home_assistant_units()


class UniversalModbusConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the Universal Modbus config flow."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Create a Universal Modbus hub."""
        if user_input is not None:
            await self.async_set_unique_id(
                f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}:{user_input[CONF_SLAVE]}"
            )
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=user_input[CONF_NAME], data=user_input, options={CONF_ENTITIES: []}
            )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME): str,
                    vol.Required(CONF_HOST): str,
                    vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(int, vol.Range(min=1, max=65535)),
                    vol.Required(CONF_SLAVE, default=DEFAULT_SLAVE): vol.All(int, vol.Range(min=0, max=247)),
                    vol.Required(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(int, vol.Range(min=1)),
                    vol.Required(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): vol.All(int, vol.Range(min=1)),
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Return the options flow handler."""
        return UniversalModbusOptionsFlow()


class UniversalModbusOptionsFlow(config_entries.OptionsFlow):
    """Handle profile import and manual entity editing."""

    def __init__(self) -> None:
        self._selected_key: str | None = None
        self._entity_draft: dict[str, Any] | None = None

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=dict(self.config_entry.options))
        profile = self._profile()
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({}),
            description_placeholders={
                "manufacturer": profile.get("manufacturer") or "-",
                "model": profile.get("model") or "-",
                "description": profile.get("description") or "-",
                "config_entry": self.config_entry.entry_id,
            },
        )

    async def async_step_manage_entities(self, user_input=None):
        options = ["add_entity"]
        if self._entities():
            options.extend(["edit_entity_select", "delete_entity_select"])
        return self.async_show_menu(
            step_id="manage_entities",
            menu_options=options,
            description_placeholders={"entities": self._entity_summary()},
        )

    async def async_step_profile_info(self, user_input=None):
        profile = self._profile()
        if user_input is not None:
            profile.update(
                name=user_input["profile_name"],
                manufacturer=user_input.get("manufacturer", ""),
                model=user_input.get("model", ""),
                description=user_input.get("description", ""),
            )
            profile["defaults"].update(
                byte_order=user_input["byte_order"],
                word_order=user_input["word_order"],
            )
            entities = self._apply_profile_orders(profile["entities"], profile["defaults"])
            return self._save(entities, profile)
        return self.async_show_form(
            step_id="profile_info",
            data_schema=vol.Schema(
                {
                    vol.Required("profile_name", default=profile["name"]): str,
                    vol.Optional("manufacturer", default=profile["manufacturer"]): str,
                    vol.Optional("model", default=profile["model"]): str,
                    vol.Optional("description", default=profile["description"]): str,
                    vol.Required(
                        "byte_order", default=profile["defaults"]["byte_order"]
                    ): vol.In(ORDERS),
                    vol.Required(
                        "word_order", default=profile["defaults"]["word_order"]
                    ): vol.In(ORDERS),
                }
            ),
        )

    async def async_step_add_entity(self, user_input=None):
        if user_input is not None:
            self._entity_draft = dict(user_input)
            return await self.async_step_add_entity_details()
        self._entity_draft = None
        return self.async_show_form(
            step_id="add_entity", data_schema=self._entity_base_schema()
        )

    async def async_step_add_entity_details(self, user_input=None):
        draft = self._entity_draft or {}
        errors = {}
        if user_input is not None:
            try:
                values = {**draft, **user_input}
                entities = self._entities()
                key = generate_unique_key(
                    values["name"], {item["key"] for item in entities}
                )
                entity = self._entity_from_input(values, key)
                entities.append(entity.to_dict())
                return self._save(entities)
            except (TypeError, ValueError, json.JSONDecodeError):
                errors["base"] = "invalid_entity"
        return self.async_show_form(
            step_id="add_entity_details",
            data_schema=self._entity_details_schema(draft),
            errors=errors,
        )

    async def async_step_edit_entity_select(self, user_input=None):
        choices = self._choices()
        if not choices:
            return self.async_abort(reason="no_entities")
        if user_input is not None:
            self._selected_key = user_input["entity_key"]
            return await self.async_step_edit_entity()
        return self.async_show_form(
            step_id="edit_entity_select",
            data_schema=vol.Schema({vol.Required("entity_key"): vol.In(choices)}),
        )

    async def async_step_edit_entity(self, user_input=None):
        current = self._selected()
        if current is None:
            return self.async_abort(reason="entity_not_found")
        if user_input is not None:
            self._entity_draft = {**current, **user_input}
            if user_input["platform"] != current["platform"]:
                self._entity_draft.pop("device_class", None)
                self._entity_draft.pop("state_class", None)
            return await self.async_step_edit_entity_details()
        self._entity_draft = None
        return self.async_show_form(
            step_id="edit_entity", data_schema=self._entity_base_schema(current)
        )

    async def async_step_edit_entity_details(self, user_input=None):
        current = self._selected()
        if current is None:
            return self.async_abort(reason="entity_not_found")
        draft = self._entity_draft or current
        errors = {}
        if user_input is not None:
            try:
                entity = self._entity_from_input(
                    {**draft, **user_input}, current["key"]
                )
                entities = self._entities()
                entities = [
                    entity.to_dict() if item["key"] == self._selected_key else item
                    for item in entities
                ]
                return self._save(entities)
            except (TypeError, ValueError, json.JSONDecodeError):
                errors["base"] = "invalid_entity"
        return self.async_show_form(
            step_id="edit_entity_details",
            data_schema=self._entity_details_schema(draft),
            errors=errors,
        )

    async def async_step_delete_entity_select(self, user_input=None):
        choices = self._choices()
        if not choices:
            return self.async_abort(reason="no_entities")
        if user_input is not None:
            self._selected_key = user_input["entity_key"]
            return await self.async_step_delete_entity()
        return self.async_show_form(
            step_id="delete_entity_select",
            data_schema=vol.Schema({vol.Required("entity_key"): vol.In(choices)}),
        )

    async def async_step_delete_entity(self, user_input=None):
        current = self._selected()
        if current is None:
            return self.async_abort(reason="entity_not_found")
        if user_input is not None and user_input.get("confirm"):
            return self._save([item for item in self._entities() if item["key"] != self._selected_key])
        return self.async_show_form(
            step_id="delete_entity",
            data_schema=vol.Schema({vol.Required("confirm", default=False): bool}),
            description_placeholders={"entity": current["name"]},
        )

    async def async_step_import_profile(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                profile = ModbusProfile.from_dict(json.loads(user_input[CONF_PROFILE_JSON]))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                errors["base"] = "invalid_profile"
            else:
                data = profile.to_dict()
                data["defaults"] = self._profile_defaults(
                    data.get("defaults"), data["entities"]
                )
                data["entities"] = self._apply_profile_orders(
                    data["entities"], data["defaults"]
                )
                return self._save(data["entities"], data)
        return self.async_show_form(
            step_id="import_profile",
            data_schema=vol.Schema({vol.Required(CONF_PROFILE_JSON): str}),
            errors=errors,
        )

    async def async_step_export_profile(self, user_input=None):
        if user_input is not None:
            return await self.async_step_init()
        return self.async_show_form(
            step_id="export_profile",
            data_schema=vol.Schema(
                {vol.Required(CONF_PROFILE_JSON, default=json.dumps(self._profile(), indent=2, ensure_ascii=False)): str}
            ),
        )


    def _entities(self) -> list[dict[str, Any]]:
        return [
            ModbusEntityDefinition.from_dict(dict(item)).to_dict()
            for item in self.config_entry.options.get(CONF_ENTITIES, [])
        ]

    def _profile(self) -> dict[str, Any]:
        stored = dict(self.config_entry.options.get("profile", {}))
        entities = self._entities()
        return {
            "schema_version": PROFILE_SCHEMA_VERSION,
            "name": stored.get("name", self.config_entry.title),
            "manufacturer": stored.get("manufacturer", ""),
            "model": stored.get("model", ""),
            "description": stored.get("description", ""),
            "defaults": self._profile_defaults(stored.get("defaults"), entities),
            "entities": entities,
        }

    @staticmethod
    def _profile_defaults(defaults, entities):
        values = dict(defaults or {})
        first = entities[0] if entities else {}
        values.setdefault("byte_order", first.get("byte_order", "big"))
        values.setdefault("word_order", first.get("word_order", "big"))
        return values

    @staticmethod
    def _apply_profile_orders(entities, defaults):
        return [
            {
                **item,
                "byte_order": defaults["byte_order"],
                "word_order": defaults["word_order"],
            }
            for item in entities
        ]

    def _save(self, entities, profile=None):
        profile_data = dict(profile or self._profile())
        profile_data["schema_version"] = PROFILE_SCHEMA_VERSION
        profile_data["entities"] = entities
        options = dict(self.config_entry.options)
        options[CONF_ENTITIES] = entities
        options["profile"] = profile_data
        return self.async_create_entry(title="", data=options)

    def _choices(self):
        return {
            item["key"]: f'{item["name"]} ({item["platform"]}, {item["table"]} {item["register"]})'
            for item in self._entities()
        }

    def _entity_summary(self) -> str:
        entities = self._entities()
        if not entities:
            return "_No entities configured._"
        rows = ["| Name | Type | Register |", "| --- | --- | --- |"]
        rows.extend(
            f'| {item["name"].replace("|", "-")} | {item["platform"]} | '
            f'{item["table"]} {item["register"]} |'
            for item in entities
        )
        return "\n".join(rows)

    def _selected(self):
        return next((item for item in self._entities() if item["key"] == self._selected_key), None)

    @staticmethod
    def _entity_base_schema(current=None):
        value = current or {}
        return vol.Schema(
            {
                vol.Required("name", default=value.get("name", "")): str,
                vol.Required("platform", default=value.get("platform", "sensor")): vol.In(PLATFORMS),
                vol.Required("table", default=value.get("table", "holding_register")): vol.In(TABLES),
                vol.Required("register", default=value.get("register", 0)): vol.All(int, vol.Range(min=0)),
                vol.Required("data_type", default=value.get("data_type", "int16")): vol.In(DATA_TYPES),
                vol.Optional(
                    "feedback_table", default=value.get("feedback_table") or ""
                ): vol.In(FEEDBACK_TABLE_OPTIONS),
            }
        )

    @staticmethod
    def _entity_details_schema(value):
        platform = value.get("platform", "sensor")
        table = value.get("table", "holding_register")
        coil_sensor = platform == "sensor" and table == "coil"
        data_type = value.get("data_type", "int16")
        feedback_table = value.get("feedback_table") or ""
        schema = {}
        if data_type != "bool":
            schema[vol.Required("scale", default=value.get("scale", 1.0))] = vol.Coerce(float)
            schema[vol.Required("offset", default=value.get("offset", 0.0))] = vol.Coerce(float)
            if platform in {"sensor", "number"}:
                schema[vol.Optional("unit", default=value.get("unit") or "")] = SelectSelector(
                    SelectSelectorConfig(options=UNIT_OPTIONS, custom_value=True)
                )
        if platform in {"sensor", "number"} and data_type != "bool":
            schema[vol.Optional("display_precision", default=value.get("display_precision") if value.get("display_precision") is not None else "")] = vol.In({"": "None", **{str(item): str(item) for item in range(7)}})
        schema[vol.Optional("icon", default=value.get("icon") or "")] = str
        device_classes = sorted(DEVICE_CLASSES_BY_PLATFORM[platform])
        if coil_sensor:
            device_classes = [item for item in device_classes if item != "enum"]
        if device_classes:
            device_class = value.get("device_class") or ""
            if coil_sensor and device_class == "enum":
                device_class = ""
            schema[vol.Optional("device_class", default=device_class)] = vol.In(
                {"": "None", **{item: item for item in device_classes}}
            )
        if platform == "sensor":
            schema[vol.Optional("state_class", default=value.get("state_class") or "")] = vol.In(
                {"": "None", **{item: item for item in STATE_CLASSES}}
            )
        if platform in WRITABLE_PLATFORMS:
            schema[vol.Optional("read_only", default=not value.get("writable", platform in WRITABLE_PLATFORMS))] = bool
        if feedback_table:
            schema[vol.Optional("feedback_register", default=value.get("feedback_register") or 0)] = vol.All(
                int, vol.Range(min=0)
            )
            if platform in {"switch", "toggle_switch", "button"}:
                schema[vol.Required("command_on", default=int(value.get("command_on", 1)))] = int
                schema[vol.Required("command_off", default=int(value.get("command_off", 0)))] = int
        if platform in {"toggle_switch", "button"}:
            schema[vol.Optional("pulse_ms", default=value.get("pulse_ms") or 0)] = vol.All(
                int, vol.Range(min=0)
            )
        if platform == "number":
            schema[vol.Required("minimum", default=value.get("minimum", 0.0))] = vol.Coerce(float)
            schema[vol.Required("maximum", default=value.get("maximum", 100.0))] = vol.Coerce(float)
            schema[vol.Required("step", default=value.get("step", 1.0))] = vol.All(
                vol.Coerce(float), vol.Range(min=0.000001)
            )
        if platform in {"sensor", "binary_sensor", "select"} and not coil_sensor:
            schema[vol.Optional(
                "options_json",
                default=json.dumps(value.get("options", {}), ensure_ascii=False),
            )] = str
        return vol.Schema(schema)

    def _entity_from_input(self, user_input, key):
        name = user_input["name"].strip()
        if not name:
            raise ValueError("Invalid name")
        platform = user_input["platform"]
        coil_sensor = platform == "sensor" and user_input["table"] == "coil"
        options = {} if coil_sensor else json.loads(user_input.get("options_json") or "{}")
        if platform == "select" and not isinstance(options, dict):
            raise ValueError("Select options must be an object")
        if platform in {"sensor", "binary_sensor"} and not isinstance(options, (dict, list)):
            raise ValueError("Sensor options must be an object or list")
        device_class = user_input.get("device_class") or None
        if coil_sensor and device_class == "enum":
            device_class = None
        state_class = user_input.get("state_class") or None
        if device_class and device_class not in DEVICE_CLASSES_BY_PLATFORM[platform]:
            raise ValueError("Unsupported device class for platform")
        if options and platform == "sensor":
            device_class = "enum"
            state_class = None
            user_input["unit"] = None
        if state_class and platform != "sensor":
            raise ValueError("State class is only supported for sensors")
        display_precision = (
            int(user_input["display_precision"])
            if user_input.get("display_precision") not in (None, "")
            and platform in {"sensor", "number"}
            and user_input["data_type"] != "bool"
            else None
        )
        defaults = self._profile()["defaults"]
        return ModbusEntityDefinition.from_dict(
            {
                "key": key,
                "name": name,
                "platform": platform,
                "table": user_input["table"],
                "register": user_input["register"],
                "data_type": user_input["data_type"],
                "count": automatic_count_for_data_type(user_input["data_type"]),
                "scale": user_input.get("scale", 1.0),
                "offset": user_input.get("offset", 0.0),
                "unit": user_input.get("unit") or None,
                "icon": user_input.get("icon") or None,
                "display_precision": display_precision,
                "device_class": device_class,
                "state_class": state_class,
                "byte_order": defaults["byte_order"],
                "word_order": defaults["word_order"],
                "writable": platform in WRITABLE_PLATFORMS and not user_input.get("read_only", False),
                "feedback_table": user_input.get("feedback_table") or None,
                "feedback_register": user_input.get("feedback_register") if user_input.get("feedback_table") else None,
                "command_on": user_input.get("command_on", 1),
                "command_off": user_input.get("command_off", 0),
                "pulse_ms": user_input.get("pulse_ms") or None,
                "minimum": user_input.get("minimum", 0.0),
                "maximum": user_input.get("maximum", 100.0),
                "step": user_input.get("step", 1.0),
                "options": {str(label): int(raw) for label, raw in options.items()} if platform == "select" else ({str(raw): str(label) for raw, label in options.items()} if isinstance(options, dict) else [str(item) for item in options]),
            }
        )
