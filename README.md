# eQ-3 MAX! Cube — Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/default)
[![GitHub Release](https://img.shields.io/github/v/release/Ebenhoeh80/ha-maxcube)](https://github.com/Ebenhoeh80/ha-maxcube/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.11+-41BDF5.svg?logo=home-assistant&logoColor=white)](https://www.home-assistant.io)
[![Donate via PayPal](https://img.shields.io/badge/❤%20Donate-PayPal-00457C.svg?logo=paypal&logoColor=white)](https://www.paypal.com/pool/9p84qTHCFr?sr=wccr)
[![Buy Me a Coffee](https://img.shields.io/badge/%E2%98%95%20Buy%20me%20a%20coffee-FFDD00.svg?logo=buymeacoffee&logoColor=black)](https://buymeacoffee.com/daneben)

[English](README.md) | [Deutsch](README.de.md)

A modern, UI-configurable Home Assistant integration for the **eQ-3 / ELV MAX!**
heating system. It talks **locally** to the original **MAX! Cube LAN gateway**
over TCP — the Cube stays in its original state (no flashing, no CUL/CUN, no cloud).

It is a config-flow replacement for the deprecated, YAML-only `maxcube`
integration that ships with Home Assistant Core.

---

## ✨ Features

- **UI setup (config flow)** — the Cube is **auto-discovered** on your network
  (its IP address is pre-filled); no YAML.
- **Climate** entities for radiator and wall thermostats:
  - target temperature (0.5 °C steps),
  - HVAC modes Auto / Heat / Off,
  - presets Boost, Comfort, Eco, Away,
  - heating action derived from the valve position,
  - comfort/eco setpoints and valve position as extra attributes.
- **Sensors**: measured temperature per thermostat and valve opening (%) per
  radiator thermostat.
- **Binary sensors**: window/door contacts and per-device low-battery warnings.
- **Cube diagnostics**: the radio **duty cycle** (%) and the number of **free memory slots**,
  read at every poll. The Cube may only use a limited share of the radio time; at 100 % it
  sends no radio commands for about an hour, so watch the duty cycle when you change many settings.
- **Finds the Cube again after an IP change** (DHCP): the Cube is looked up by its serial number
  and the new address is saved automatically.
- **Service `maxcube_local.reconnect`** closes the connection to the Cube and reads everything again.
- The **Cube** appears as a hub device with its firmware version; all devices
  group under it and are assigned to their MAX! room.
- **Options**: adjustable poll interval (30–600 s).

---

## 📦 Requirements

- An **eQ-3 MAX! Cube LAN gateway** reachable on your network (default port `62910`).
- Home Assistant **2024.11** or newer.

---

## ⬇️ Installation (HACS)

1. In HACS, search for **eQ-3 MAX! Cube** and install it.
2. Restart Home Assistant.
3. **Settings → Devices & Services → Add Integration → eQ-3 MAX! Cube**, and enter
   the Cube's IP address (it is pre-filled when the Cube is found automatically).

If you do not find it in HACS yet, add it as a custom repository instead: HACS →
three-dot menu → **Custom repositories**, add
`https://github.com/Ebenhoeh80/ha-maxcube` with category **Integration**, then install
it as above.

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

This integration is built on the
[`maxcube-api`](https://github.com/uebelack/python-maxcube-api) library.

Its climate platform is **derived from the Home Assistant Core `maxcube`
integration**, which is licensed under the Apache License 2.0. The required
attribution and a copy of that license are in the [`NOTICE`](NOTICE) file.

The community project
[MassiPi/maxcube](https://github.com/MassiPi/maxcube) was consulted **only as a
reference** — it carries no license, and no code from it is included here.

---

## 🗺️ Roadmap & ideas

Planned and under consideration — **give a 👍 to what matters to you**, and bring your own ideas:

- 🔜 Weekly schedule: view and set the heating programme
- 💡 Repair notice when the Cube is unreachable
- 💡 Diagnostic sensors (comfort/eco/min/max setpoints)

➡️ All ideas & voting: **[Discussions → Ideas](https://github.com/Ebenhoeh80/ha-maxcube/discussions/categories/ideas)**

---

## ❤️ Support this project

<div align="center">

**I build and maintain this integration in my free time, and cover the running costs — my time, electricity, and the development tools and IT equipment I use — out of my own pocket.**

If it saves you time or trouble, a small voluntary tip helps keep the project going. Every contribution, however small, is hugely appreciated. Thank you! 🙏

<a href="https://www.paypal.com/pool/9p84qTHCFr?sr=wccr">
  <img src="https://img.shields.io/badge/Buy%20me%20a%20coffee-PayPal-00457C?style=for-the-badge&logo=paypal&logoColor=white" alt="Donate via PayPal" height="42">
</a>
<a href="https://buymeacoffee.com/daneben">
  <img src="https://img.shields.io/badge/%E2%98%95%20Buy%20me%20a%20coffee-FFDD00?style=for-the-badge&logo=buymeacoffee&logoColor=black" alt="Buy Me a Coffee" height="42">
</a>

</div>

---

## 📄 License

MIT © 2026 Daniel Ebenhöh — see [LICENSE](LICENSE).

Portions of the climate platform are derived from the Apache-2.0-licensed Home
Assistant Core `maxcube` integration; see [`NOTICE`](NOTICE) for the attribution
and the Apache License 2.0 text.
