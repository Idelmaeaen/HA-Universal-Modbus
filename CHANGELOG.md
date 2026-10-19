# Changelog

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
