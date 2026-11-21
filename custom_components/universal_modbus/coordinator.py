"""Polling coordinator for Universal Modbus."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from threading import Lock
from time import perf_counter
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from pymodbus.client import ModbusTcpClient

from .codec import (
    apply_write_formula,
    decode_registers,
    encode_registers,
    required_registers,
)
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
    unit_id: int


class UniversalModbusCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinate polling and writes over one Modbus TCP connection."""

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
        self._scan_interval = int(
            entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )
        self._client = ModbusTcpClient(
            host=entry.data[CONF_HOST],
            port=int(entry.data.get(CONF_PORT, 502)),
            timeout=float(entry.data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)),
        )
        self._device_id_parameter = modbus_device_parameter(
            self._client.read_holding_registers
        )
        self._client_lock = Lock()
        self._operation_lock = asyncio.Lock()
        self._read_batches = self._build_read_batches()
        self._next_poll = dict.fromkeys(self._read_batches, 0)
        self._force_refresh = False
        self.last_response_time_ms: int | None = None
        self.communication_error_count = 0
        self.last_successful_update: datetime | None = None
        self.entity_errors: dict[str, str] = {}
        self.last_error: str | None = None

        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(seconds=self._scan_interval),
        )

    def _unit_id(self, definition: ModbusEntityDefinition) -> int:
        return self._slave if definition.unit_id is None else definition.unit_id

    @staticmethod
    def _read_item(definition: ModbusEntityDefinition) -> _ReadItem:
        table = definition.feedback_table or definition.table
        register = (
            definition.feedback_register
            if definition.feedback_register is not None
            else definition.register
        )
        count = max(1, definition.count)
        if table in {"holding_register", "input_register"}:
            count = max(count, required_registers(definition.data_type))
        return _ReadItem(definition, table, register, count)

    def _build_read_batches(self) -> dict[int, list[_ReadBatch]]:
        """Group contiguous reads by interval, unit ID and table."""
        groups: dict[tuple[int, int, str], list[_ReadItem]] = {}
        for definition in self.entities:
            item = self._read_item(definition)
            interval = definition.scan_interval or self._scan_interval
            group = (interval, self._unit_id(definition), item.table)
            groups.setdefault(group, []).append(item)

        batches: dict[int, list[_ReadBatch]] = {}
        for (interval, unit_id, table), items in groups.items():
            interval_batches = batches.setdefault(interval, [])
            max_count = (
                _MAX_BIT_READ
                if table in {"coil", "discrete_input"}
                else _MAX_REGISTER_READ
            )

            current: list[_ReadItem] = []
            start = 0
            end = 0
            for item in sorted(items, key=lambda item: item.register):
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

                interval_batches.append(
                    _ReadBatch(table, start, end - start, tuple(current), unit_id)
                )
                current = [item]
                start = item.register
                end = item_end

            if current:
                interval_batches.append(
                    _ReadBatch(table, start, end - start, tuple(current), unit_id)
                )

        return batches

    async def async_request_refresh(self) -> None:
        """Allow explicit Home Assistant refreshes to poll every group."""
        self._force_refresh = True
        await super().async_request_refresh()

    async def _async_update_data(self) -> dict[str, Any]:
        async with self._operation_lock:
            # Home Assistant schedules coordinator refreshes on whole seconds
            # with a fixed offset to stagger them.
            now = int(self.hass.loop.time())
            batches = []
            for interval, deadline in self._next_poll.items():
                if self._force_refresh or deadline <= now:
                    batches.extend(self._read_batches[interval])
                    self._next_poll[interval] = now + interval
            self._force_refresh = False
            try:
                if batches or not self.entities:
                    return await self.hass.async_add_executor_job(self._read_all, batches)
                if not self.last_update_success:
                    raise UpdateFailed(self.last_error or "All Modbus reads failed")
                return self.data
            except UpdateFailed:
                raise
            except Exception as err:
                raise UpdateFailed(f"Modbus update failed: {err}") from err
            finally:
                if self._next_poll:
                    delay = min(self._next_poll.values()) - int(self.hass.loop.time())
                    self.update_interval = timedelta(seconds=max(1, delay))

    def _ensure_connected(self) -> None:
        if not self._client.connected and not self._client.connect():
            raise ConnectionError("Unable to connect to Modbus device")

    def _read_all(self, batches: list[_ReadBatch]) -> dict[str, Any]:
        with self._client_lock:
            started = perf_counter()
            try:
                self._ensure_connected()
            except Exception as err:
                self.communication_error_count += 1
                self.last_error = str(err)
                self.entity_errors = {item.key: str(err) for item in self.entities}
                self._client.close()
                raise

            # Keep previous values and errors for groups that are not due yet.
            values = dict(self.data or {})
            errors: dict[str, str] = {}
            updated: dict[str, Any] = {}
            for batch in batches:
                try:
                    updated.update(self._decode_batch(batch))
                except Exception as batch_err:
                    # Retry a failed range one entity at a time to isolate bad addresses.
                    if len(batch.items) == 1:
                        errors[batch.items[0].definition.key] = str(batch_err)
                        continue
                    for item in batch.items:
                        try:
                            updated.update(self._decode_batch(self._single_batch(item)))
                        except Exception as item_err:
                            errors[item.definition.key] = str(item_err)
            for key in updated:
                self.entity_errors.pop(key, None)
            self.entity_errors.update(errors)
            self.last_error = self._format_read_errors(self.entity_errors)
            if errors:
                self.communication_error_count += 1
            if self.entities and len(self.entity_errors) == len(self.entities):
                self._client.close()
                raise RuntimeError(self.last_error or "All Modbus reads failed")
            if updated or not self.entities:
                self.last_response_time_ms = round((perf_counter() - started) * 1000)
                self.last_successful_update = dt_util.now()
            values.update(updated)
            return values

    def _single_batch(self, item: _ReadItem) -> _ReadBatch:
        return _ReadBatch(
            item.table, item.register, item.count, (item,), self._unit_id(item.definition)
        )

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
            item = self._read_item(definition)
            details.append(f"{definition.name} ({item.table}:{item.register}): {error}")
        return "; ".join(details)

    def _read_batch(self, batch: _ReadBatch) -> list[int]:
        """Read one batch and normalize registers or bits to integers."""
        device = {self._device_id_parameter: batch.unit_id}
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
        """Write one entity value and publish its acknowledged or confirmed state."""
        await self._async_write_value(definition, value)

    async def _async_write_value(
        self,
        definition: ModbusEntityDefinition,
        value: Any,
        *,
        publish: bool = True,
    ) -> None:
        async with self._operation_lock:
            try:
                await self.hass.async_add_executor_job(
                    self._write_value, definition, value
                )
            except Exception as err:
                raise UpdateFailed(
                    f"Modbus write failed for {definition.key}: {err}"
                ) from err
            if not publish:
                return
            if definition.feedback_table and definition.write_confirmation:
                try:
                    value = await self.hass.async_add_executor_job(
                        self._read_feedback, definition
                    )
                except Exception as err:
                    self.entity_errors[definition.key] = str(err)
                    self.last_error = self._format_read_errors(self.entity_errors)
                    self.communication_error_count += 1
                    self.async_update_listeners()
                    raise UpdateFailed(
                        f"Modbus write acknowledged for {definition.key}, "
                        f"but feedback failed: {err}"
                    ) from err
            elif definition.platform == "switch":
                value = value == definition.command_on
            elif definition.data_type == "bool":
                value = bool(value)

            self.entity_errors.pop(definition.key, None)
            self.last_error = self._format_read_errors(self.entity_errors)
            self.data = {**(self.data or {}), definition.key: value}
            self.async_update_listeners()

    def _read_feedback(self, definition: ModbusEntityDefinition) -> Any:
        with self._client_lock:
            batch = self._single_batch(self._read_item(definition))
            return self._decode_batch(batch)[definition.key]

    def _write_value(self, definition: ModbusEntityDefinition, value: Any) -> None:
        with self._client_lock:
            try:
                self._ensure_connected()
                device = {self._device_id_parameter: self._unit_id(definition)}

                if definition.table == "coil":
                    if definition.advanced_calculation:
                        value = apply_write_formula(value, definition)
                    if definition.write_mode == "multiple":
                        response = self._client.write_coils(
                            definition.register, [bool(value)], **device
                        )
                    else:
                        response = self._client.write_coil(
                            definition.register, bool(value), **device
                        )
                elif definition.table == "holding_register":
                    registers = encode_registers(value, definition)
                    if definition.write_mode == "single" or (
                        definition.write_mode == "auto" and len(registers) == 1
                    ):
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
        await self._async_write_value(definition, definition.command_on, publish=False)
        await asyncio.sleep((definition.pulse_ms or 100) / 1000)
        # A pulse command does not describe the state of a separate feedback register.
        await self._async_write_value(
            definition,
            definition.command_off,
            publish=not definition.feedback_table or definition.write_confirmation,
        )

    async def async_shutdown(self) -> None:
        """Close the Modbus client without blocking Home Assistant."""
        await super().async_shutdown()
        async with self._operation_lock:
            await self.hass.async_add_executor_job(self._close_client)

    def _close_client(self) -> None:
        with self._client_lock:
            self._client.close()
