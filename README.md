# eQ-3 MAX! Cube — Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/default)
[![GitHub Release](https://img.shields.io/github/v/release/Ebenhoeh80/ha-maxcube)](https://github.com/Ebenhoeh80/ha-maxcube/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.11+-41BDF5.svg?logo=home-assistant&logoColor=white)](https://www.home-assistant.io)
[![Donate via PayPal](https://img.shields.io/badge/❤%20Donate-PayPal-00457C.svg?logo=paypal&logoColor=white)](https://www.paypal.com/pool/9p84qTHCFr?sr=wccr)

[English](README.md) | [Deutsch](README.de.md)

A modern, UI-configurable Home Assistant integration for the **eQ-3 / ELV MAX!**
heating system. It talks **locally** to the original **MAX! Cube LAN gateway**
over TCP — the Cube stays in its original state (no flashing, no CUL/CUN, no cloud).

It is a config-flow replacement for the deprecated, YAML-only `maxcube`
integration that ships with Home Assistant Core.

---

## ✨ Features

- **UI setup (config flow)** — just enter the Cube's IP address, no YAML.
- **Climate** entities for radiator and wall thermostats:
  - target temperature (0.5 °C steps),
  - HVAC modes Auto / Heat / Off,
  - presets Boost, Comfort, Eco, Away,
  - heating action derived from the valve position,
  - comfort/eco setpoints and valve position as extra attributes.
- **Sensors**: measured temperature per thermostat and valve opening (%) per
  radiator thermostat.
- **Binary sensors**: window/door contacts and per-device low-battery warnings.
- The **Cube** appears as a hub device with its firmware version; all devices
  group under it and are assigned to their MAX! room.
- **Options**: adjustable poll interval (30–600 s).

---

## 📦 Requirements

- An **eQ-3 MAX! Cube LAN gateway** reachable on your network (default port `62910`).
- Home Assistant **2024.11** or newer.

---

## ⬇️ Installation (HACS)

1. HACS → three-dot menu → **Custom repositories**.
2. Add `https://github.com/Ebenhoeh80/ha-maxcube`, category **Integration**.
3. Install **eQ-3 MAX! Cube**, then restart Home Assistant.
4. **Settings → Devices & Services → Add Integration → eQ-3 MAX! Cube**, and enter
   the Cube's IP address.

(Or copy `custom_components/maxcube_local` into your `config/custom_components` folder.)

---

## 🔁 Migration from the legacy integration

The built-in `maxcube` integration is YAML-only and has no config entry, so there
is nothing Home Assistant can migrate automatically. Because both integrations
derive entity IDs from the **same Cube device names**, your history, dashboards
and automations are preserved if you switch cleanly:

1. Remove the `maxcube:` block from `configuration.yaml` → **restart** Home Assistant.
2. Add this integration and enter the Cube's IP.

The new entities reclaim the same `climate.<name>` IDs, so recorder history
continues. Adjust any that don't match exactly under *Settings → Entities*.

---

## ⚠️ Important notes

- **One connection at a time.** The Cube accepts only a single client connection.
  Close the MAX! smartphone app — and remove the old YAML `maxcube:` integration —
  before adding this one, otherwise setup fails with *cannot connect*.
- **Separate from the core integration.** Remove any legacy `maxcube:` block from
  `configuration.yaml` first — otherwise the old integration keeps holding the
  Cube's single connection.
- The MAX! cloud was shut down by eQ-3 in 2023; this integration never used it.

---

## 🙏 Credits

Built on the reverse-engineered MAX! protocol and the
[`maxcube-api`](https://github.com/uebelack/python-maxcube-api) library, and
inspired by the Home Assistant Core `maxcube` integration and the community fork
[MassiPi/maxcube](https://github.com/MassiPi/maxcube).

---

## ❤️ Support this project

<div align="center">

**I build and maintain this integration in my free time — and cover the running costs out of my own pocket.**

If it saves you time or trouble, a small voluntary tip keeps the project alive and motivates new features.
Every contribution, however small, is hugely appreciated. Thank you! 🙏

<a href="https://www.paypal.com/pool/9p84qTHCFr?sr=wccr">
  <img src="https://img.shields.io/badge/Buy%20me%20a%20coffee-PayPal-00457C?style=for-the-badge&logo=paypal&logoColor=white" alt="Donate via PayPal" height="42">
</a>

</div>

---

## 📄 License

MIT © 2026 Daniel Ebenhöh — see [LICENSE](LICENSE).
