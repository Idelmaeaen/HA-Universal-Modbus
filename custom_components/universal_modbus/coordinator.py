"""Polling coordinator for Universal Modbus."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
import logging
from threading import Lock
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

_MAX_REGISTER_READ = 125
_MAX_BIT_READ = 2000


@dataclass(frozen=True, slots=True)
class _ReadItem:
    """One entity value inside a Modbus read batch."""

    definition: ModbusEntityDefinition
    table: str
    address: int
    count: int


@dataclass(frozen=True, slots=True)
class _ReadBatch:
    """A contiguous Modbus range read with one request."""

    table: str
    address: int
    count: int
    items: tuple[_ReadItem, ...]


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
        self._client_lock = Lock()
        self._read_batches = self._build_read_batches()

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(
                seconds=int(entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
            ),
        )

    def _build_read_batches(self) -> tuple[_ReadBatch, ...]:
        """Build safe contiguous ranges grouped by Modbus table."""
        items: list[_ReadItem] = []
        for definition in self.entities:
            table = definition.feedback_table or definition.table
            address = (
                definition.feedback_address
                if definition.feedback_address is not None
                else definition.address
            )
            count = max(1, definition.count)
            if table in {"holding_register", "input_register"}:
                count = max(count, required_registers(definition.data_type))
            items.append(_ReadItem(definition, table, address, count))

        batches: list[_ReadBatch] = []
        for table in ("coil", "discrete_input", "holding_register", "input_register"):
            table_items = sorted(
                (item for item in items if item.table == table),
                key=lambda item: item.address,
            )
            max_count = (
                _MAX_BIT_READ
                if table in {"coil", "discrete_input"}
                else _MAX_REGISTER_READ
            )

            current: list[_ReadItem] = []
            start = 0
            end = 0
            for item in table_items:
                item_end = item.address + item.count
                if not current:
                    current = [item]
                    start = item.address
                    end = item_end
                    continue

                merged_end = max(end, item_end)
                is_contiguous = item.address <= end
                fits_protocol_limit = merged_end - start <= max_count
                if is_contiguous and fits_protocol_limit:
                    current.append(item)
                    end = merged_end
                    continue

                batches.append(
                    _ReadBatch(table, start, end - start, tuple(current))
                )
                current = [item]
                start = item.address
                end = item_end

            if current:
                batches.append(
                    _ReadBatch(table, start, end - start, tuple(current))
                )

        return tuple(batches)

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self.hass.async_add_executor_job(self._read_all)
        except Exception as err:
            raise UpdateFailed(f"Modbus update failed: {err}") from err

    def _ensure_connected(self) -> None:
        if not self._client.connected and not self._client.connect():
            raise ConnectionError("Unable to connect to Modbus device")

    def _read_all(self) -> dict[str, Any]:
        with self._client_lock:
            try:
                self._ensure_connected()
                values: dict[str, Any] = {}
                for batch in self._read_batches:
                    payload = self._read_batch(batch)
                    for item in batch.items:
                        offset = item.address - batch.address
                        entity_payload = payload[offset : offset + item.count]
                        values[item.definition.key] = decode_registers(
                            entity_payload, item.definition
                        )
                return values
            except Exception:
                self._client.close()
                raise

    def _read_batch(self, batch: _ReadBatch) -> list[int]:
        """Read one batch and normalize registers or bits to integers."""
        if batch.table == "coil":
            response = self._client.read_coils(
                batch.address, count=batch.count, slave=self._slave
            )
        elif batch.table == "discrete_input":
            response = self._client.read_discrete_inputs(
                batch.address, count=batch.count, slave=self._slave
            )
        elif batch.table == "holding_register":
            response = self._client.read_holding_registers(
                batch.address, count=batch.count, slave=self._slave
            )
        elif batch.table == "input_register":
            response = self._client.read_input_registers(
                batch.address, count=batch.count, slave=self._slave
            )
        else:
            raise ValueError(f"Unsupported Modbus table: {batch.table}")

        if response.isError():
            raise RuntimeError(
                f"Modbus read error at {batch.table}:{batch.address} "
                f"(count {batch.count}): {response}"
            )

        if batch.table in {"coil", "discrete_input"}:
            return [1 if bit else 0 for bit in response.bits[: batch.count]]
        return list(response.registers)

    async def async_write_value(
        self, definition: ModbusEntityDefinition, value: Any
    ) -> None:
        """Write one entity value and refresh coordinator data."""
        await self._async_write_value(definition, value)
        await self.async_request_refresh()

    async def _async_write_value(
        self, definition: ModbusEntityDefinition, value: Any
    ) -> None:
        try:
            await self.hass.async_add_executor_job(
                self._write_value, definition, value
            )
        except Exception as err:
            raise UpdateFailed(
                f"Modbus write failed for {definition.key}: {err}"
            ) from err

    def _write_value(self, definition: ModbusEntityDefinition, value: Any) -> None:
        with self._client_lock:
            try:
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
            except Exception:
                self._client.close()
                raise

    async def async_pulse(self, definition: ModbusEntityDefinition) -> None:
        """Write the on command, wait, then write the off command."""
        await self._async_write_value(definition, definition.command_on)
        await asyncio.sleep((definition.pulse_ms or 100) / 1000)
        await self._async_write_value(definition, definition.command_off)
        await self.async_request_refresh()

    async def async_shutdown(self) -> None:
        """Close the Modbus client without blocking Home Assistant."""
        await self.hass.async_add_executor_job(self._close_client)

    def _close_client(self) -> None:
        with self._client_lock:
            self._client.close()
