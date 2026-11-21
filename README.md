# eQ-3 MAX! Cube — Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/default)
[![GitHub Release](https://img.shields.io/github/v/release/Ebenhoeh80/ha-maxcube)](https://github.com/Ebenhoeh80/ha-maxcube/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2025.3+-41BDF5.svg?logo=home-assistant&logoColor=white)](https://www.home-assistant.io)
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
- **Weekly heating programme** (read and write): the programme of each thermostat is shown in the
  climate entity's `schedule` attribute (for every day the setpoints with the time until which each
  temperature applies, with exact half degrees), together with `scheduled_temperature`, the temperature
  the programme sets right now. The service `maxcube_local.get_schedule` returns it as a response.
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

## 🗓️ Weekly heating programme

Every radiator thermostat shows its programme in the climate entity's `schedule` attribute and as
the response of `maxcube_local.get_schedule`. To **change** it, use `maxcube_local.set_schedule`
on one or more radiator thermostats (wall thermostats cannot be programmed here):

```yaml
action: maxcube_local.set_schedule
target:
  entity_id: climate.kinderzimmer_thermostat_kinderzimmer
data:
  days: [monday, tuesday, wednesday, thursday, friday]
  periods:
    - {until: "05:00", temperature: 17}
    - {until: "08:00", temperature: 21}
    - {until: "17:00", temperature: 18.5}
    - {until: "23:00", temperature: 21}
    - {until: "24:00", temperature: 17}
```

Each period gives the temperature that applies **until** the time shown; the last period must end at
`24:00`. At most seven periods per day, times in steps of 5 minutes, temperatures in half degrees from
4.5 ("off") to 30.5 ("on"). The same programme is written to every listed day; for other periods on other days use
`by_day` (see below). Add `dry_run: true` to only check the request: nothing is sent to the Cube.

- After writing, the integration reads the programme back from the Cube and reports for each day whether
  the Cube now shows exactly what you asked for: `confirmed`, or `sent_not_confirmed` when the Cube took the
  message but still shows the old programme. The Cube updates its copy only after the thermostat has taken the
  change, which takes about two minutes, so look at the `schedule` attribute a little later. If the old
  programme is still shown after five minutes, a warning is logged. A day the Cube refuses raises an error.
- Every day is one radio message. The service refuses to write when the Cube has already used 90 % of
  its radio time (see the *Radio duty cycle* sensor).
- The programme only matters while a thermostat is in **Auto** mode.
- The weekly programme is stored per thermostat. The MAX! software sets it per room; to keep a room
  consistent, select all radiator thermostats of the room as targets.

### Different periods per day

`by_day` gives each day its own periods, instead of `days` and `periods` (do not use them together):

```yaml
action: maxcube_local.set_schedule
target:
  entity_id: climate.kinderzimmer_thermostat_kinderzimmer
data:
  by_day:
    monday: [{until: "24:00", temperature: 17}]
    saturday: [{until: "08:00", temperature: 19}, {until: "24:00", temperature: 21}]
```

### Copy a programme to other thermostats

`maxcube_local.copy_schedule` copies the programme of one radiator thermostat (`source`) to other radiator
thermostats (`targets`), for all seven days or only for the days in `days`:

```yaml
action: maxcube_local.copy_schedule
data:
  source: climate.kinderzimmer_thermostat_kinderzimmer
  targets: [climate.schlafzimmer_thermostat, climate.gaestezimmer_thermostat]
  days: [saturday, sunday]   # optional, default: all seven days
```

Only the days that differ from a target's programme are written. Before the first radio telegram the
integration estimates the radio time (about 2.8 % per telegram, added to the current duty cycle). If the
Cube would reach 90 %, the request is refused and nothing is sent. The response gives the result per
thermostat and day (`unchanged`, `confirmed`, `sent_not_confirmed` or `failed`). Source and targets must be
radiator thermostats of the same Cube.

### Weekly programme card

The integration ships a Lovelace card to view and edit the programme: it appears in the card picker as
**MAX! Cube weekly programme** (no resource to add by hand; after an update press `Ctrl+Shift+R` so the
browser loads the new file).

```yaml
type: custom:maxcube-schedule-card
entity: climate.kinderzimmer_thermostat_kinderzimmer   # optional, the first thermostat is shown otherwise
size: medium                                           # small | medium | large
```

Drag the zones to change times, edit the temperature or end time below, copy a day to other days, and
select the thermostats to write to. Only radiator thermostats are listed (wall thermostats cannot be
programmed). Nothing is sent without a change, and only the changed days are written. **Every day written
to every thermostat is one radio message and uses about 2.8 % of the Cube's radio time**, so the card asks
for confirmation before writing to more than one thermostat or more than three days. Use the dry-run
option to check a programme without sending it. The card was contributed by @helpmeifyoucan.

---

## 📦 Requirements

- An **eQ-3 MAX! Cube LAN gateway** reachable on your network (default port `62910`).
- Home Assistant **2025.3** or newer.

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

## ⚙️ Configuration

| Setting | Where | Meaning |
| :--- | :--- | :--- |
| IP address | setup, or **Reconfigure** | Address of the Cube. Pre-filled when the Cube answers the discovery broadcast. |
| Port | setup, or **Reconfigure** | Default `62910`. |
| Poll interval | **Configure** (options), 30–600 s | How often the Cube is read. Default 60 s. Reading is cheap; radio time is used up mainly by writing settings. |

**Cube got a new address?** The integration looks for it by its serial number and saves the new address by
itself. If that does not work, use **⋮ → Reconfigure** on the integration entry and enter the new IP; devices,
names and history stay.

---

## 🖥️ Supported devices

| Device | Supported |
| :--- | :--- |
| MAX! Cube LAN gateway | yes (hub device, firmware, radio duty cycle, free memory slots) |
| Radiator thermostat / thermostat+ | yes (climate, temperature, valve position, battery, weekly programme read and write) |
| Wall thermostat | yes (climate, temperature, battery; the programme is shown, not written) |
| Window / door contact | yes (open/closed, battery) |
| Eco button | not yet |

## 🔧 Supported functions

Read: target and measured temperature, mode, presets, valve position, window state, battery, weekly programme,
radio duty cycle, free memory slots. Write: target temperature, HVAC mode, preset, weekly programme (radiator
thermostats). Not supported: pairing devices, changing comfort/eco/window temperatures, holiday mode.

## 🔄 Data updates

The integration polls the Cube (local, no cloud) every 60 s by default. Every poll opens a short connection
and closes it again, so other clients can use the Cube in between. Changes you make in Home Assistant are
sent immediately and read back at the next poll.

## 💡 Use cases

- **Heat the kids' room earlier on school days:** call `maxcube_local.set_schedule` (see above) from an
  automation or script.
- **Warn about a cold room:** an automation on `climate.<room>` with a template condition that compares
  `current_temperature` to `temperature`.
- **Save heating when away:** set the preset *Away* with `climate.set_preset_mode` when everybody has left.

## 🩺 Troubleshooting

| Problem | What to check |
| :--- | :--- |
| *Cannot connect* during setup | Close the MAX! app and remove any old `maxcube:` YAML block: the Cube accepts only one client. Check IP and port. |
| Entities become unavailable | The Cube is unreachable. Look at the **Connectivity** sensor; give the Cube a fixed address or rely on the automatic rediscovery. |
| A thermostat shows no temperature | Radiator thermostats report a measured temperature only in Auto/Manual mode, and only after the first radio contact. |
| Programme change not visible | The Cube shows it after about two minutes; look at the `schedule` attribute again. |
| Write refused (duty cycle) | The Cube used 90 % of its radio time. Wait; at 100 % it sends nothing for about an hour. |

## 🗑️ Removal

**Settings → Devices & Services → eQ-3 MAX! Cube → ⋮ → Delete.** The Cube and its devices are removed from
Home Assistant; nothing is changed on the Cube itself. Then remove the integration in HACS if you wish.

## ⚠️ Known limitations

- The Cube accepts only one client at a time.
- Wall thermostats cannot be programmed here, and pairing or deleting devices needs the MAX! software.
- Home Assistant does not store a thermostat's programme; it is read from the Cube.
- A device paired with the Cube appears at the next poll. A device removed from the Cube disappears from Home Assistant after the next reload or restart.

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

- ✅ Weekly schedule: view (1.2.0) and set (1.3.0) the heating programme
- ✅ Repair notices: Cube unreachable for six hours, radio time almost used up (1.5.0)
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
