"""Polling coordinator for Universal Modbus."""
from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from pymodbus.client import ModbusTcpClient

from .codec import decode_registers, encode_registers, required_registers
from .const import (
    CONF_ENTITIES,
    CONF_SCAN_INTERVAL,
    CONF_SLAVE,
    CONF_TIMEOUT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SLAVE,
    DEFAULT_TIMEOUT,
    DOMAIN,
)
from .models import ModbusEntityDefinition

_LOGGER = logging.getLogger(__name__)


class UniversalModbusCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinate polling and writes for one Modbus TCP device."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self.entities = [
            ModbusEntityDefinition.from_dict(item)
            for item in entry.options.get(CONF_ENTITIES, [])
        ]
        self._slave = int(entry.data.get(CONF_SLAVE, DEFAULT_SLAVE))
        self._client = ModbusTcpClient(
            host=entry.data[CONF_HOST],
            port=int(entry.data.get(CONF_PORT, 502)),
            timeout=float(entry.data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)),
        )

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(
                seconds=int(entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
            ),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self.hass.async_add_executor_job(self._read_all)
        except Exception as err:
            raise UpdateFailed(f"Modbus update failed: {err}") from err

    def _ensure_connected(self) -> None:
        if not self._client.connected and not self._client.connect():
            raise ConnectionError("Unable to connect to Modbus device")

    def _read_all(self) -> dict[str, Any]:
        self._ensure_connected()
        values: dict[str, Any] = {}

        for definition in self.entities:
            table = definition.feedback_table or definition.table
            address = (
                definition.feedback_address
                if definition.feedback_address is not None
                else definition.address
            )
            values[definition.key] = self._read_value(definition, table, address)

        return values

    def _read_value(
        self,
        definition: ModbusEntityDefinition,
        table: str,
        address: int,
    ) -> Any:
        if table == "coil":
            response = self._client.read_coils(
                address, count=max(1, definition.count), slave=self._slave
            )
            payload = [1 if bit else 0 for bit in response.bits]
        elif table == "discrete_input":
            response = self._client.read_discrete_inputs(
                address, count=max(1, definition.count), slave=self._slave
            )
            payload = [1 if bit else 0 for bit in response.bits]
        else:
            count = max(definition.count, required_registers(definition.data_type))
            if table == "holding_register":
                response = self._client.read_holding_registers(
                    address, count=count, slave=self._slave
                )
            elif table == "input_register":
                response = self._client.read_input_registers(
                    address, count=count, slave=self._slave
                )
            else:
                raise ValueError(f"Unsupported Modbus table: {table}")
            payload = list(response.registers)

        if response.isError():
            raise RuntimeError(
                f"Modbus read error for {definition.key} at {table}:{address}: {response}"
            )
        return decode_registers(payload, definition)

    async def async_write_value(
        self, definition: ModbusEntityDefinition, value: Any
    ) -> None:
        try:
            await self.hass.async_add_executor_job(
                self._write_value, definition, value
            )
        except Exception as err:
            raise UpdateFailed(f"Modbus write failed for {definition.key}: {err}") from err
        await self.async_request_refresh()

    def _write_value(self, definition: ModbusEntityDefinition, value: Any) -> None:
        self._ensure_connected()

        if definition.table == "coil":
            response = self._client.write_coil(
                definition.address, bool(value), slave=self._slave
            )
        elif definition.table == "holding_register":
            registers = encode_registers(value, definition)
            if len(registers) == 1:
                response = self._client.write_register(
                    definition.address, registers[0], slave=self._slave
                )
            else:
                response = self._client.write_registers(
                    definition.address, registers, slave=self._slave
                )
        else:
            raise ValueError(
                f"Table {definition.table} is read-only and cannot be written"
            )

        if response.isError():
            raise RuntimeError(
                f"Modbus write error for {definition.key} at "
                f"{definition.table}:{definition.address}: {response}"
            )

    async def async_pulse(self, definition: ModbusEntityDefinition) -> None:
        await self.async_write_value(definition, definition.command_on)
        await asyncio.sleep((definition.pulse_ms or 100) / 1000)
        await self.async_write_value(definition, definition.command_off)

    async def async_shutdown(self) -> None:
        await self.hass.async_add_executor_job(self._client.close)
