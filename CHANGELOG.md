# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.4.1] - 2026-11-20

### Fixed
- The reboot button had no name (it showed up as just "MAX! Cube"); it is called "Restart Cube" / "Cube neu starten" now.
  The button stays disabled by default.

## [1.4.0] - 2026-11-20

### Added
- **Home Assistant Integration Quality Scale: Gold** (`quality_scale.yaml`), `icons.json`,
  `PARALLEL_UPDATES`, descriptions for all dialog fields and README sections (configuration, supported
  devices and functions, data updates, use cases, troubleshooting, removal, known limitations).
- **Reconfigure flow:** change the Cube's address without removing the entry (only the same Cube, by its
  serial number, is accepted; identity and title stay).
- **Repair hints** for a low battery and a device error, and a **diagnostics download** with addresses,
  serial numbers and names removed; the diagnostics also show how many polls ran, failed and how long the last took.
- **Devices paired later get their entities at the next poll;** devices that left the Cube are removed after
  the next reload or restart and may be deleted in the UI.
- **Link-status diagnostics and a reboot button**, contributed by @helpmeifyoucan (pull request #3, rebased
  onto 1.3.3 in #17): the Cube's per-device flags (Error, Link error, Not initialized, No data received) as
  diagnostic sensors with the raw flag bytes as an attribute, and a button that reboots the Cube. "Radio fault",
  "Not initialized" and the reboot button are disabled by default.
- CI: ruff, mypy with the real Home Assistant types, xenon, CodeQL, 95 % coverage gate;
  [`docs/ENGINEERING.md`](docs/ENGINEERING.md) documents architecture, failure modes, measurements and decisions.

### Fixed
- **Poll and commands no longer overlap on the Cube's single connection** (a test showed two threads in a
  Cube call at once; calls are serialised now).
- A poll refused or reset by the Cube (for example while the MAX! app holds the connection) is repeated once.
- Read-backs after commands are merged for 2 s instead of 10 s.
- The reboot button no longer raises on a network error.

## [1.3.3] - 2026-11-20

### Changed
- **A Cube is identified by its serial number, not by its address.** The entry's unique id and its title are now
  the serial number (`MAX! Cube JEQ0355273`); before, both contained the address, which changed with every new
  address and showed a wrong title. Existing entries are migrated at the next start (a title you chose stays);
  devices, entities, areas and history are not touched. See [`docs/IDENTITY.md`](docs/IDENTITY.md).
- **Discovery:** Home Assistant now finds a Cube by its DHCP request (hardware address prefix of eQ-3): the first
  Cube appears under *Discovered*, and a known Cube that got a new address is followed. After startup the integration
  also scans once for Cubes it does not know or whose address changed.
- **One Cube, one entry:** a second entry for a Cube that already has one stops with a clear message instead of
  creating every device twice.
- **The Cube that answers must be the Cube of the entry:** a different Cube at the saved address is no longer taken
  over; the right one is looked up by its serial number.
- The entry reloads (once) when the options or the address change, scheduled by its update listener.

### Fixed
- The connection test of the setup dialog did not close its connection, so the Cube stayed occupied until it was
  cleaned up; an unexpected error in the dialog is shown as "unknown".
- A failed setup because the Cube is off logs one line instead of a full error trace.
- The broadcast search no longer raises when the machine has no usable network interface.

## [1.3.2] - 2026-11-20

### Fixed
- **The Cube is found again after it was off or restarted.** A Cube that has no DHCP lease yet
  answers the discovery broadcast from its factory address `192.168.0.222`. Version 1.3.1 saved that
  address, although it cannot be reached from the home network, and then stayed on it: the entry
  was stuck in *retry* and every device was unavailable. Now an address is only saved if the Cube's
  data port answers there, and the lookup by serial number also runs when Home Assistant starts or
  the entry is set up again, not only while it is running.

## [1.3.1] - 2026-11-20

### Changed
- **Writing the weekly programme: the read-back is checked again later.** On a real Cube the new
  programme shows up in the Cube's data only after the thermostat has taken it, about two minutes
  after the write. The service now reports `sent_not_confirmed` right away in that case (instead of
  suggesting a failure), checks again five minutes later and logs a warning if the Cube still shows
  the old programme. The README explains the delay.

## [1.3.0] - 2026-11-20

### Added
- **Setting the weekly heating programme.** The service `maxcube_local.set_schedule` writes a daily
  programme to chosen days of one or more radiator thermostats (periods with the temperature that applies
  until a time; at most seven per day, 5-minute steps, half degrees, the last period ends at 24:00).
  `dry_run: true` only checks the request. After writing, the programme is read back from the Cube and
  checked; a day the Cube did not take raises an error. It refuses to write when the Cube has used 90 %
  of its radio time.
- Tests for the validation, for the radio message (identical to the library's for a full day) and for
  the read-back.

### Changed
- The radio message is built in the integration instead of with the library's `set_programme`, which
  skips a write when its own (half-degree-cutting) copy looks equal and pads a short day with one byte
  instead of two.

## [1.2.0] - 2026-11-20

### Added
- **Weekly heating programme (read-only).** The programme of each radiator thermostat is shown in the
  climate entity's `schedule` attribute: for every day the setpoints with the time until which each
  temperature applies. Wall thermostats show the programme of a radiator thermostat in the same room.
  `scheduled_temperature` is the temperature the programme sets right now. The programme is decoded
  with exact half degrees (the `maxcube-api` library cuts 21.5 to 21), and the large attribute is kept
  out of the history database.
- **Service `maxcube_local.get_schedule`** returns the weekly programme of the chosen thermostats as a
  response.
- Tests for the decoding (day order, half degrees, end of day, the C message).

## [1.1.0] - 2026-11-20

### Added
- **Cube diagnostics.** Two diagnostic sensors on the Cube device: the radio **duty cycle** (%) and
  the number of **free memory slots**. At a duty cycle of 100 % the Cube sends no radio commands for
  about an hour, so this is worth watching when many settings are changed.
- **The Cube is found again after an IP change.** The Cube's serial number is saved; when a poll
  fails, the integration looks for a Cube with that serial number on the network and saves its new
  address (at most every five minutes).
- **Service `maxcube_local.reconnect`** closes the connection to the Cube and reads everything again
  (optionally for one Cube).
- Tests for the status values and for finding the Cube by its serial number (new CI workflow).

### Changed
- Every poll now opens its own short connection to the Cube and closes it again. This keeps the
  duty cycle and the free memory slots current (the Cube reports them when a connection starts) and
  leaves the Cube free for other clients between polls.

## [1.0.0] - 2026-11-20

The integration is stable: entities, configuration data and services stay as they are. From
now on version numbers follow [Semantic Versioning](https://semver.org/): a breaking change
raises the major version, a new feature the minor version, a fix the patch version.

### Changed
- README (en/de): the installation section now starts with finding **eQ-3 MAX! Cube** through
  HACS search (the integration is in the HACS catalog); the custom repository steps stay as a
  fallback.

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
