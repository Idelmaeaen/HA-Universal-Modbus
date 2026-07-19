"""Polling coordinator for Universal Modbus."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from time import perf_counter
from threading import Lock
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
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
from .helpers import modbus_device_parameter
from .models import ModbusEntityDefinition

_LOGGER = logging.getLogger(__name__)

_MAX_REGISTER_READ = 125
_MAX_BIT_READ = 2000


@dataclass(frozen=True, slots=True)
class _ReadItem:
    """One entity value inside a Modbus read batch."""

    definition: ModbusEntityDefinition
    table: str
    register: int
    count: int


@dataclass(frozen=True, slots=True)
class _ReadBatch:
    """A contiguous Modbus range read with one request."""

    table: str
    register: int
    count: int
    items: tuple[_ReadItem, ...]


class UniversalModbusCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinate polling and writes for one Modbus TCP device."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        profile_defaults = entry.options.get("profile", {}).get("defaults", {})
        entity_data = []
        for item in entry.options.get(CONF_ENTITIES, []):
            values = dict(item)
            for order in ("byte_order", "word_order"):
                if order in profile_defaults:
                    values[order] = profile_defaults[order]
            entity_data.append(values)
        self.entities = [ModbusEntityDefinition.from_dict(item) for item in entity_data]
        self._slave = int(entry.data.get(CONF_SLAVE, DEFAULT_SLAVE))
        self._client = ModbusTcpClient(
            host=entry.data[CONF_HOST],
            port=int(entry.data.get(CONF_PORT, 502)),
            timeout=float(entry.data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)),
        )
        self._device_id_parameter = modbus_device_parameter(
            self._client.read_holding_registers
        )
        self._client_lock = Lock()
        self._read_batches = self._build_read_batches()
        self.last_response_time_ms: int | None = None
        self.communication_error_count = 0
        self.last_successful_update: datetime | None = None
        self.entity_errors: dict[str, str] = {}
        self.last_error: str | None = None

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
            register = (
                definition.feedback_register
                if definition.feedback_register is not None
                else definition.register
            )
            count = max(1, definition.count)
            if table in {"holding_register", "input_register"}:
                count = max(count, required_registers(definition.data_type))
            items.append(_ReadItem(definition, table, register, count))

        batches: list[_ReadBatch] = []
        for table in ("coil", "discrete_input", "holding_register", "input_register"):
            table_items = sorted(
                (item for item in items if item.table == table),
                key=lambda item: item.register,
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
                item_end = item.register + item.count
                if not current:
                    current = [item]
                    start = item.register
                    end = item_end
                    continue

                merged_end = max(end, item_end)
                is_contiguous = item.register <= end
                fits_protocol_limit = merged_end - start <= max_count
                if is_contiguous and fits_protocol_limit:
                    current.append(item)
                    end = merged_end
                    continue

                batches.append(_ReadBatch(table, start, end - start, tuple(current)))
                current = [item]
                start = item.register
                end = item_end

            if current:
                batches.append(_ReadBatch(table, start, end - start, tuple(current)))

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
            started = perf_counter()
            self.entity_errors = {}
            self.last_error = None
            try:
                self._ensure_connected()
                # Keep the last known value for a temporarily failed entity. Its
                # entity is marked unavailable through ``entity_errors`` below.
                values: dict[str, Any] = dict(self.data or {})
                entity_errors: dict[str, str] = {}
                successful_reads = 0
                for batch in self._read_batches:
                    try:
                        batch_values = self._decode_batch(batch)
                    except Exception as batch_err:
                        # A single illegal address can make a combined Modbus
                        # request fail. Retry its entities separately so valid
                        # neighbours continue to update.
                        if len(batch.items) == 1:
                            item = batch.items[0]
                            entity_errors[item.definition.key] = str(batch_err)
                            continue
                        batch_values = {}
                        for item in batch.items:
                            item_batch = _ReadBatch(
                                item.table,
                                item.register,
                                item.count,
                                (item,),
                            )
                            try:
                                batch_values.update(self._decode_batch(item_batch))
                            except Exception as item_err:
                                entity_errors[item.definition.key] = str(item_err)
                    values.update(batch_values)
                    successful_reads += len(batch_values)

                self.entity_errors = entity_errors
                self.last_error = self._format_read_errors(entity_errors)
                if entity_errors:
                    self.communication_error_count += 1
                if self._read_batches and successful_reads == 0:
                    self._client.close()
                    raise RuntimeError(self.last_error or "All Modbus reads failed")
                self.last_response_time_ms = round((perf_counter() - started) * 1000)
                self.last_successful_update = dt_util.now()
                return values
            except Exception:
                if not self.entity_errors:
                    self.communication_error_count += 1
                    self._client.close()
                raise

    def _decode_batch(self, batch: _ReadBatch) -> dict[str, Any]:
        """Read and decode all entity values contained in one batch."""
        payload = self._read_batch(batch)
        values: dict[str, Any] = {}
        for item in batch.items:
            offset = item.register - batch.register
            entity_payload = payload[offset : offset + item.count]
            values[item.definition.key] = decode_registers(
                entity_payload, item.definition
            )
        return values

    def _format_read_errors(self, errors: dict[str, str]) -> str | None:
        """Create a compact diagnostic for the current failed entities."""
        if not errors:
            return None
        definitions = {item.key: item for item in self.entities}
        details = []
        for key, error in errors.items():
            definition = definitions[key]
            table = definition.feedback_table or definition.table
            register = (
                definition.feedback_register
                if definition.feedback_register is not None
                else definition.register
            )
            details.append(f"{definition.name} ({table}:{register}): {error}")
        return "; ".join(details)

    def _read_batch(self, batch: _ReadBatch) -> list[int]:
        """Read one batch and normalize registers or bits to integers."""
        device = {self._device_id_parameter: self._slave}
        if batch.table == "coil":
            response = self._client.read_coils(
                batch.register, count=batch.count, **device
            )
        elif batch.table == "discrete_input":
            response = self._client.read_discrete_inputs(
                batch.register, count=batch.count, **device
            )
        elif batch.table == "holding_register":
            response = self._client.read_holding_registers(
                batch.register, count=batch.count, **device
            )
        elif batch.table == "input_register":
            response = self._client.read_input_registers(
                batch.register, count=batch.count, **device
            )
        else:
            raise ValueError(f"Unsupported Modbus table: {batch.table}")

        if response.isError():
            raise RuntimeError(
                f"Modbus read error at {batch.table}:{batch.register} "
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
            await self.hass.async_add_executor_job(self._write_value, definition, value)
        except Exception as err:
            raise UpdateFailed(
                f"Modbus write failed for {definition.key}: {err}"
            ) from err

    def _write_value(self, definition: ModbusEntityDefinition, value: Any) -> None:
        with self._client_lock:
            try:
                self._ensure_connected()
                device = {self._device_id_parameter: self._slave}

                if definition.table == "coil":
                    response = self._client.write_coil(
                        definition.register, bool(value), **device
                    )
                elif definition.table == "holding_register":
                    registers = encode_registers(value, definition)
                    if len(registers) == 1:
                        response = self._client.write_register(
                            definition.register, registers[0], **device
                        )
                    else:
                        response = self._client.write_registers(
                            definition.register, registers, **device
                        )
                else:
                    raise ValueError(
                        f"Table {definition.table} is read-only and cannot be written"
                    )

                if response.isError():
                    raise RuntimeError(
                        f"Modbus write error for {definition.key} at "
                        f"{definition.table}:{definition.register}: {response}"
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
