# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- **No more deprecation warnings on Home Assistant 2026.11.** The thermostats now
  provide `native_current_temperature`, `native_target_temperature` and
  `_attr_native_temperature_unit` (the old names stop working in Home Assistant
  2027.11), and the devices are linked to the Cube hub with `via_device_id`
  (`via_device` stops working in 2027.8). Older Home Assistant versions keep
  using the previous names, so the minimum version is unchanged.

## [0.4.0] - 2026-11-17

### Added
- **Automatic Cube discovery** in the config flow: the integration sends a UDP
  broadcast on the local network and pre-fills the Cube's IP address, so you no
  longer have to look it up. Manual entry still works as a fallback.
- The **device serial number** (e.g. `JEQ…`/`KEQ…`) is now shown on each MAX!
  device and on the Cube hub, via Home Assistant's device registry.
- Release assets are now **counted downloads**: each release ships a
  `maxcube_local.zip` asset and HACS installs from it (`zip_release`).

### Changed
- Documentation/licensing: added a `NOTICE` file crediting the Apache-2.0
  licensed Home Assistant Core `maxcube` integration (from which the climate
  platform is derived) and including the Apache License 2.0 text. The READMEs now
  state that `MassiPi/maxcube` was used only as a reference, with no code taken
  from it. This addresses the HACS default-store review (PR hacs/default#14273).

## [0.3.1] - 2026-11-16

### Added
- **Connectivity** binary sensor on the Cube device (on = the Cube is reachable /
  the last poll succeeded), giving the hub its own status entity. It stays
  available even when the Cube is offline, so it can report the disconnected state.

## [0.3.0] - 2026-11-16

### Changed
- **Renamed the integration domain `maxcube` → `maxcube_local`** so it no longer
  collides with the Home Assistant core integration — a requirement for HACS
  default-store inclusion. **After updating, delete the old integration entry and
  add it again.** Entity IDs (e.g. `climate.<name>`) stay the same, so recorder
  history continues.

### Added
- Measured temperature is now shown to **0.1 °C** (climate current temperature and
  the temperature sensor). Setpoints stay in 0.5 °C steps, as the Cube requires.

## [0.2.0] - 2026-11-16

### Added
- **Temperature sensor** per thermostat (the measured room temperature),
  usable for graphs and automations instead of only the climate attribute.
- The **Cube appears as a hub device** with its firmware version; all
  thermostats and contacts group under it and are assigned to their MAX! room.
- **Comfort/eco setpoints and valve position** exposed as climate attributes.
- Donation/support section in the READMEs and a `.github/FUNDING.yml`.

## [0.1.1] - 2026-11-16

### Fixed
- Entity setup crashed with
  `is_thermostat() takes 1 positional argument but 2 were given` because the
  device-type checks were called on the Cube instead of the device, so **no
  entities were created**. They are now called on the device.

## [0.1.0] - 2026-11-16

### Added
- Initial MVP: config flow, `climate` entities for radiator and wall thermostats,
  window/battery `binary_sensor` entities, a valve-position `sensor`, and an
  options flow for the poll interval. Local TCP via `maxcube-api`, no cloud.
