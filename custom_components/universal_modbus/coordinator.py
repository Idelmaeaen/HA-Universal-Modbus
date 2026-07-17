"""Polling coordinator for Universal Modbus."""
from __future__ import annotations

from datetime import timedelta
from typing import Any
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from pymodbus.client import ModbusTcpClient

from .const import CONF_ENTITIES, CONF_SCAN_INTERVAL, CONF_SLAVE, CONF_TIMEOUT, DEFAULT_SCAN_INTERVAL, DEFAULT_SLAVE, DEFAULT_TIMEOUT
from .models import ModbusEntityDefinition

_LOGGER = logging.getLogger(__name__)


class UniversalModbusCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Read all configured entities for one Modbus TCP device."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name=entry.title,
            update_interval=timedelta(seconds=entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
        )
        self.entry = entry
        self.unit = entry.data.get(CONF_SLAVE, DEFAULT_SLAVE)
        self.entities = [ModbusEntityDefinition.from_dict(item) for item in entry.options.get(CONF_ENTITIES, [])]
        self.client = ModbusTcpClient(
            entry.data[CONF_HOST],
            port=entry.data[CONF_PORT],
            timeout=entry.data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self.hass.async_add_executor_job(self._read_all)
        except Exception as err:
            raise UpdateFailed(str(err)) from err

    def _read_all(self) -> dict[str, Any]:
        if not self.client.connect():
            raise ConnectionError("Unable to connect to Modbus device")
        values: dict[str, Any] = {}
        for entity in self.entities:
            response = self._read(entity)
            if response.isError():
                raise ConnectionError(f"Read failed for {entity.key}: {response}")
            raw = response.bits[0] if entity.table in {"coil", "discrete_input"} else response.registers[0]
            values[entity.key] = raw if isinstance(raw, bool) else raw * entity.scale + entity.offset
        return values

    def _read(self, entity: ModbusEntityDefinition):
        kwargs = {"address": entity.address, "count": entity.count, "device_id": self.unit}
        return {
            "coil": self.client.read_coils,
            "discrete_input": self.client.read_discrete_inputs,
            "holding_register": self.client.read_holding_registers,
            "input_register": self.client.read_input_registers,
        }[entity.table](**kwargs)

    async def async_shutdown(self) -> None:
        await self.hass.async_add_executor_job(self.client.close)
