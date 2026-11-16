# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
