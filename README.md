# eQ-3 MAX! Cube — Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/default)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

A modern, UI-configurable Home Assistant integration for the **eQ-3 / ELV MAX!**
heating system. It talks **locally** to the original **MAX! Cube LAN gateway**
over TCP — the Cube stays in its original state (no flashing, no CUL/CUN, no cloud).

It is a config-flow replacement for the deprecated, YAML-only `maxcube`
integration that ships with Home Assistant Core.

**Language:** English · [Deutsch](README.de.md)

## Features

- **UI setup (config flow)** — just enter the Cube's IP address, no YAML.
- **Climate** entities for radiator and wall thermostats:
  - target temperature (0.5 °C steps),
  - HVAC modes Auto / Heat / Off,
  - presets Boost, Comfort, Eco, Away,
  - heating action derived from the valve position.
- **Binary sensors**: window/door contacts and per-device low-battery warnings.
- **Sensor**: valve opening percentage per radiator thermostat.
- **Options**: adjustable poll interval (30–600 s).
- Devices are grouped per MAX! room (suggested area).

## Requirements

- An **eQ-3 MAX! Cube LAN gateway** reachable on your network (default port `62910`).
- Home Assistant **2024.11** or newer.

## Installation (HACS)

1. HACS → three-dot menu → **Custom repositories**.
2. Add `https://github.com/Ebenhoeh80/ha-maxcube`, category **Integration**.
3. Install **eQ-3 MAX! Cube**, then restart Home Assistant.
4. **Settings → Devices & Services → Add Integration → eQ-3 MAX! Cube**, and enter
   the Cube's IP address.

(Or copy `custom_components/maxcube` into your `config/custom_components` folder.)

## Important notes

- **One connection at a time.** The Cube accepts only a single client connection.
  Close the MAX! smartphone app — and remove the old YAML `maxcube:` integration —
  before adding this one, otherwise setup fails with *cannot connect*.
- **Drop-in replacement.** This integration uses the same `maxcube` domain as the
  Core integration and shadows it. Remove any `maxcube:` block from
  `configuration.yaml` first.
- The MAX! cloud was shut down by eQ-3 in 2023; this integration never used it.

## Status

Early MVP (v0.1.0): climate + window/battery binary sensors + valve sensor, set up
via config flow. Reauth, auto-discovery and a test suite are planned.

## Credits

Built on the reverse-engineered MAX! protocol and the
[`maxcube-api`](https://github.com/uebelack/python-maxcube-api) library, and
inspired by the Home Assistant Core `maxcube` integration and the community fork
[MassiPi/maxcube](https://github.com/MassiPi/maxcube).

## License

MIT © 2026 Daniel Ebenhöh
