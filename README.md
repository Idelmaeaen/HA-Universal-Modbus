<p align="center">
  <img src="brand/icon.png" alt="Universal Modbus icon" width="72">
</p>

# Universal Modbus

Universal Modbus is a custom Home Assistant integration for Modbus TCP devices.
Connections and entities are configured through the Home Assistant UI; no YAML
configuration is required.

Universal Modbus is developed and maintained by **Edelmann Electronics**.

## Features

- Create and manage multiple Modbus TCP hubs in the sidebar
- Read coils, discrete inputs, holding registers, and input registers
- Write coils and holding registers
- Create `sensor`, `binary_sensor`, `switch`, `button`, `number`, and `select`
  entities, including pulsed ToggleSwitch entities
- Decode `bool`, `int16`, `uint16`, `int32`, `uint32`, `int64`, `uint64`, and `float32` values
- Configure scaling, offsets, byte order, and word order
- Use safe per-entity read and write formulas for advanced calculations
- Use a separate feedback register for writable entities
- Display and control entity values directly in the sidebar
- Import and export a complete hub
- English and German UI translations

The integration combines overlapping and adjacent reads from the same Modbus
table. A request contains at most 125 registers or 2,000 bits.

## Supported entity types

| Type | Behavior |
| --- | --- |
| `sensor` | Publishes numeric, boolean, or mapped text values. |
| `binary_sensor` | Converts the decoded value to an on/off state. |
| `switch` | Writes configurable on/off values and reports the polled state. |
| `toggle_switch` | Sends an on/off pulse whenever its state is changed. |
| `button` | Writes an on value and can optionally send an off value after a configured pulse duration. |
| `number` | Writes numeric values within the configured minimum, maximum, and step. |
| `select` | Maps labels to integer values and writes the selected value. |

Switches, buttons, numbers, and selects can also be configured as read-only.
Writable entities must use a coil or holding register as their write target.

## Installation

### HACS

1. In HACS, open **Integrations**.
2. Open the menu and select **Custom repositories**.
3. Add `https://github.com/Idelmaeaen/HA-Universal-Modbus` as an
   **Integration** repository.
4. Find and download **Universal Modbus**.
5. Restart Home Assistant.

### Manual installation

Copy `custom_components/universal_modbus` into the Home Assistant configuration
directory so that the final path is:

```text
<config>/custom_components/universal_modbus
```

Restart Home Assistant afterward.

## Initial setup

1. Open **Settings > Devices & services** in Home Assistant.
2. Select **Add integration** and search for **Universal Modbus**.
3. Enter the connection settings:

   | Field | Description | Default |
   | --- | --- | --- |
   | Device name | Name of the Home Assistant hub and device | None |
   | Host | Hostname or IP address of the Modbus TCP server | None |
   | Port | TCP port | `502` |
   | Unit ID | Modbus unit/slave ID (`0` to `247`) | `1` |
   | Scan interval | Polling interval in seconds | `5` |
   | Timeout | Connection timeout in seconds | `3` |

Port, scan interval, and timeout must be positive whole numbers. The port may
not exceed `65535`. Each combination of host, port, and Unit ID can be added
only once.

The device must be reachable during setup. If it is unavailable or all
configured reads fail, Home Assistant retries loading the integration.

## Sidebar editor

Open **Universal Modbus** in the Home Assistant sidebar. From there you can:

- Add, edit, select, and delete hubs
- Configure connection details and device metadata
- Add, duplicate, edit, and delete entities
- Sort entities and open their Home Assistant entity pages
- View connection status, response time, communication errors, and the last
  successful poll
- Refresh values manually and control writable entities
- Remove orphaned Home Assistant entities

**Settings > Devices & services > Universal Modbus > Configure** links to this
editor.

The upload and download buttons import or export the hub configuration and its
entities. For privacy, exports omit the IP address and exporter identity; the IP
address is requested during import.

### Screenshots

Hub overview:

![Universal Modbus hub overview](docs/images/hub-overview.png)

Hub settings:

![Universal Modbus hub settings](docs/images/hub-editor.png)

Entity settings:

![Universal Modbus entity settings](docs/images/entity-editor.png?v=20261020)

## Entity configuration

The editor shows only settings relevant to the selected entity type, register
area, and data type. The most important settings are:

- Name, entity type, icon, and Home Assistant device/state class
- Modbus table and zero-based register address
- Data type, scale, offset, unit, and displayed decimal places
- Optional advanced read and write formulas
- Optional feedback table and register
- Modbus write mode for writable coils and holding registers
- Write commands and pulse duration for switch-like entities
- Minimum, maximum, and step for numbers
- Value mappings for enum sensors and selects

Entity keys are generated from the name and stay unchanged during normal edits.
Regenerating keys changes Home Assistant unique IDs and can affect entity IDs,
history, dashboards, and automations.

### Register areas and data types

| Register area | Access | Supported data types |
| --- | --- | --- |
| Coil | Read/write | `bool` |
| Discrete input | Read-only | `bool` |
| Holding register | Read/write | All supported types |
| Input register | Read-only | All supported types |

`bool`, `int16`, and `uint16` use one bit or register. `int32`, `uint32`, and
`float32` use two registers. `int64` and `uint64` use four registers.

### Addressing and conversion

- Addresses are zero-based and are passed directly to pymodbus. Documentation
  addresses such as `40001` are not converted automatically.
- Register values are calculated as `value = raw value × scale + offset`.
  Writes reverse this calculation before encoding.
- Byte order controls the bytes inside each register. Word order controls the
  registers of a multi-register value. Both settings apply to the complete hub.
- A feedback register lets a writable entity read its state from a different
  Modbus address than its write target.
- Enum sensors can map raw values to text. Select options map displayed labels
  to integer values.

### Write modes

Writable coil and holding-register entities can select the exact Modbus write
function required by the device documentation:

| Register area | Mode | Function |
| --- | --- | --- |
| Coil | `Auto` | `0x05 Write Single Coil` |
| Coil | `0x05 Write Single Coil` | Write one coil explicitly |
| Coil | `0x0F Write Multiple Coils` | Write a list containing one coil |
| Holding register | `Auto` | `0x06` for one register, `0x10` for multiple registers |
| Holding register | `0x06 Write Single Register` | Write one 16-bit register explicitly |
| Holding register | `0x10 Write Multiple Registers` | Write one or more registers as a list |

`Auto` preserves the behavior of profiles created before version 1.2.0. The
single-register option is unavailable for data types that occupy more than one
register.

### Advanced calculations

Enable **Advanced calculation** in an entity editor to replace the fixed scale
and offset conversion with formulas. Existing entities and entities with the
option disabled continue to use the normal conversion.

The read formula is prefilled with:

```text
register_value * scale + offset
```

`register_value` is the decoded Modbus value after the configured data type,
byte order, and word order have been applied. `scale` and `offset` are the
entity's configured values.

Writable entity types also show a write formula. It converts the Home Assistant
value back to the raw value that is encoded into the register and defaults to:

```text
(value - offset) / scale
```

Formulas are single expressions. They support `+`, `-`, `*`, `/`, `//`, `%`,
comparisons, boolean operators, and conditional expressions. The available
functions are `abs`, `min`, `max`, `round`, `int`, `float`, and `bool`.

Examples:

```text
None if register_value == 65535 else register_value / 10
100 if register_value > 0 else 0
round(max(register_value, 0) * scale + offset, 2)
```

Returning `None` from a read formula creates an unknown value. Formulas are
validated when the profile is saved and run in a restricted evaluator; Python
imports, attributes, indexing, and function definitions are not allowed. If a
read formula fails at runtime, only the affected entity becomes unavailable.

Only administrators should create or import profiles. A profile author is
effectively an administrator: besides formulas, `pulse_ms` can pause a write
for an unrestricted, profile-defined duration. Only use profiles from trusted
sources.

## Error handling and diagnostics

If one register read fails, the affected entity becomes unavailable while
other valid entities continue updating. The sidebar shows the current error.
Each hub also provides diagnostic entities for response time, communication
error count, and the last successful poll.

After a successful write, the integration requests an immediate refresh.

## Known limitations

- Only Modbus TCP is supported; Modbus RTU/serial is not implemented.
- Writes are limited to coils and holding registers.
- Strings, bitfields, and custom encodings are not supported.
- Device discovery is not implemented.
- The editor does not verify whether an address, data type, or command is valid
  for the physical device.
- A writable entity can currently be assigned a read-only table, but the write
  then fails at runtime.
- A scale of `0` is accepted, but cannot be reversed for writes.

## Contributing

Bug reports and focused pull requests are welcome. Include the Home Assistant
and integration versions, entity configuration, Modbus table and address, and
relevant logs when reporting a reproducible issue.

Do not publish credentials, private device registers, or other sensitive data
in exported hubs, logs, issues, or commits.
