# eQ-3 MAX! Cube

A modern, UI-configurable Home Assistant integration for the **eQ-3 / ELV MAX!**
heating system, talking locally to the original **MAX! Cube LAN gateway**
(no flashing, no cloud).

- Set up entirely from the UI (config flow) — the Cube is auto-discovered on
  your network and its IP address is pre-filled.
- Radiator and wall thermostats as `climate` entities (target temperature,
  auto/manual/off, boost/comfort/eco/away presets, heating action from the valve).
- Measured temperature and valve opening as `sensor` entities.
- Window/door contacts and low-battery warnings as `binary_sensor` entities.
- The Cube shows up as a hub device with its firmware version.

> The Cube accepts only **one** connection at a time — disconnect the MAX!
> smartphone app before adding the integration.
