# Changelog

## 1.4.1 - 2026-11-22

### Added

- Added Simplified Chinese translations (`zh` and `zh-Hans`) for the config
  flow, options flow, service descriptions, and diagnostic entities. The sidebar
  editor is also fully localized in Chinese.
- Added the `universal_modbus.write_register` service for writing one or more
  raw values to holding registers from **Settings > Tools > Actions** or an
  automation. A single value uses FC06 and a list uses FC16. The `hub` accepts
  either the hub name or its config entry ID, and an optional `slave` overrides
  the hub's default Unit ID for that write. See the
  [service documentation](custom_components/universal_modbus/docs/write_register.md).
- Added a diagnostic device-status `binary_sensor` for each hub. It is on when
  communication succeeds and off when the device is offline, and exposes
  request/response counters, the last successful update, host, port, last error
  time and message, and the communication error count as attributes.

### Changed

- The `last_successful_update` diagnostic sensor no longer records every poll
  in the Logbook. Its value, state class, and display are unchanged.

## 1.4.0 - 2026-11-21

### Added

- Entities can use different Modbus Unit IDs over one hub's TCP connection.
  Leaving an entity's Unit ID blank uses the hub default. [#7](https://github.com/Idelmaeaen/HA-Universal-Modbus/issues/7)
- Entities can override the hub's scan interval. Entities with the same interval
  are polled together, with contiguous reads batched by unit and register area. [#8](https://github.com/Idelmaeaen/HA-Universal-Modbus/issues/8)

### Changed

- Writable entities can read their feedback register immediately after a Modbus
  write acknowledgement or after the last command of a pulse. This confirmation
  is enabled by default when a feedback register is configured. Ordinary writes
  update the entity on acknowledgement without triggering a full hub scan. [#8](https://github.com/Idelmaeaen/HA-Universal-Modbus/issues/8)

### Fixed

- The **Add entity** button is available above the table. Long register names
  wrap, and live errors update without resetting the table's scroll position. [#6](https://github.com/Idelmaeaen/HA-Universal-Modbus/issues/6)
- Renaming a register updates the integration-provided entity name in Home
  Assistant and preserves the existing entity ID and any custom name. [#6](https://github.com/Idelmaeaen/HA-Universal-Modbus/issues/6)
- Hub creation, editing, and import now accept Unit ID 255. [#9](https://github.com/Idelmaeaen/HA-Universal-Modbus/issues/9)

## 1.3.2 - 2026-10-24

### Fixed

- The once-per-second sidebar refresh now updates live values and diagnostics
  in place instead of rebuilding the complete entity table, preventing the
  page from moving while it is scrolled.

## 1.3.1 - 2026-10-24

### Fixed

- The sidebar now preserves the vertical scroll position of the entity list
  while live Modbus values are refreshed.

## 1.3.0 - 2026-10-20

### Changed

- Register-area selectors and the entity table now display the corresponding
  Modbus read function codes and protocol names (`0x01` through `0x04`).
- The sidebar editor now remembers the selected hub across page reloads and
  later visits in the same browser.
- The entity table can now be scrolled horizontally on narrow mobile screens,
  keeping all values and controls accessible.
- Updated the entity-settings documentation and screenshot to show the new
  Modbus read-function labels.

### Fixed

- The mobile entity table now preserves its horizontal scroll position during
  live Modbus polling updates.

## 1.2.0 - 2026-10-19

### Added

- Added a per-entity Modbus write-mode selector with protocol function names:
  `0x05 Write Single Coil`, `0x0F Write Multiple Coils`,
  `0x06 Write Single Register`, and `0x10 Write Multiple Registers`.
- Added an `Auto` mode that preserves the previous write behavior for existing
  profiles.
- Documented how write modes map to Modbus function codes.

### Fixed

- Writable entities can now control devices that require function `0x0F` or
  `0x10` even when only one coil or holding register is written.

Earlier release notes are available on the
[GitHub releases page](https://github.com/Idelmaeaen/HA-Universal-Modbus/releases).
