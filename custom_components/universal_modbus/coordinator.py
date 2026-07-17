"""Polling coordinator for Universal Modbus."""
from __future__ import annotations

from datetime import timedelta
from typing import Any
import logging
import time

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from pymodbus.client import ModbusTcpClient

from .codec import decode_registers, encode_registers, required_registers
from .const import CONF_ENTITIES, CONF_SCAN_INTERVAL, CONF_SLAVE, CONF_TIMEOUT, DEFAULT_SCAN_INTERVAL, DEFAULT_SLAVE, DEFAULT_TIMEOUT
from .models import ModbusEntityDefinition

_LOGGER = logging.getLogger(__name__)


class UniversalModbusCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Read and write configured entities for one Modbus TCP device."""

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

    def _ensure_connected(self) -> None:
        if not self.client.connect():
            raise ConnectionError("Unable to connect to Modbus device")

    def _read_all(self) -> dict[str, Any]:
        self._ensure_connected()
        values: dict[str, Any] = {}
        for entity in self.entities:
            response = self._read(entity)
            if response.isError():
                raise ConnectionError(f"Read failed for {entity.key}: {response}")
            if entity.table in {"coil", "discrete_input"}:
                values[entity.key] = bool(response.bits[0])
            else:
                values[entity.key] = decode_registers(response.registers, entity)
        return values

    def _read(self, entity: ModbusEntityDefinition):
        count = entity.count
        if entity.table in {"holding_register", "input_register"}:
            count = max(count, required_registers(entity.data_type))
        kwargs = {"address": entity.address, "count": count, "device_id": self.unit}
        return {
            "coil": self.client.read_coils,
            "discrete_input": self.client.read_discrete_inputs,
            "holding_register": self.client.read_holding_registers,
            "input_register": self.client.read_input_registers,
        }[entity.table](**kwargs)

    async def async_write_value(self, entity: ModbusEntityDefinition, value: Any) -> None:
        """Write an entity value and refresh coordinator data."""
        await self.hass.async_add_executor_job(self._write_value, entity, value)
        await self.async_request_refresh()

    def _write_value(self, entity: ModbusEntityDefinition, value: Any) -> None:
        self._ensure_connected()
        if entity.table == "coil":
            response = self.client.write_coil(address=entity.address, value=bool(value), device_id=self.unit)
        elif entity.table == "holding_register":
            registers = encode_registers(value, entity)
            if len(registers) == 1:
                response = self.client.write_register(address=entity.address, value=registers[0], device_id=self.unit)
            else:
                response = self.client.write_registers(address=entity.address, values=registers, device_id=self.unit)
        else:
            raise ValueError(f"Table {entity.table} is not writable")
        if response.isError():
            raise ConnectionError(f"Write failed for {entity.key}: {response}")

    async def async_pulse(self, entity: ModbusEntityDefinition) -> None:
        """Write the ON command and then reset it after the configured pulse time."""
        await self.hass.async_add_executor_job(self._pulse, entity)
        await self.async_request_refresh()

    def _pulse(self, entity: ModbusEntityDefinition) -> None:
        self._write_value(entity, entity.command_on)
        time.sleep(max(entity.pulse_ms or 250, 1) / 1000)
        self._write_value(entity, entity.command_off)

    async def async_shutdown(self) -> None:
        await self.hass.async_add_executor_job(self.client.close)
