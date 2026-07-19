"""Constants for Universal Modbus."""

from __future__ import annotations

DOMAIN = "universal_modbus"
PLATFORMS = ["sensor", "binary_sensor", "switch", "button", "number", "select"]

CONF_ENTITIES = "entities"
CONF_PROFILE_NAME = "profile_name"
CONF_PROFILE_JSON = "profile_json"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_SLAVE = "slave"
CONF_TIMEOUT = "timeout"

DEFAULT_PORT = 502
DEFAULT_SCAN_INTERVAL = 5
DEFAULT_SLAVE = 1
DEFAULT_TIMEOUT = 3

PROFILE_SCHEMA_VERSION = 1
PROFILE_DIRECTORY = "universal_modbus_profiles"
SERVICE_EXPORT_PROFILE = "export_profile"
SERVICE_IMPORT_PROFILE = "import_profile"
