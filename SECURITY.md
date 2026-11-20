# Security Policy

## Supported Versions

Security fixes are made in the latest release of the 1.x line.

| Version | Supported          |
| ------- | ------------------ |
| 1.x     | :white_check_mark: |
| < 1.0   | :x:                |

## Security considerations

This integration talks to an eQ-3 MAX! Cube on the local network. It has no cloud component, stores
no account data and makes no contact with the internet.

- **The MAX! protocol has no authentication.** Anyone who can reach TCP port 62910 of the Cube can read
  and change everything (temperatures, programmes, pairing) and can occupy its single connection; anyone in
  the same broadcast domain can send the UDP datagram (port 23272) that reboots the Cube. The integration
  cannot change this. **Keep the Cube in a trusted network** (home LAN, or its own VLAN) and never forward
  these ports to the internet.
- **The serial number in a discovery answer is unauthenticated.** A host on the LAN can claim any serial
  number. The integration only accepts a serial number of the shape `^[A-Z0-9]{10}$`, compares the serial
  number of the Cube that answers with the one of the entry on every connection (this protects against
  mix-ups, not against forgery, see [docs/IDENTITY.md](docs/IDENTITY.md)), and saves a new address only after
  the data port answered there.
- **What is stored:** the Cube's address, port and serial number in the config entry. There are no passwords
  or tokens. The diagnostics download redacts addresses, serial numbers, names and the entry title.
- **Commands are validated:** a programme is checked (times, half degrees, at most seven periods) before it
  is sent, and not written while the Cube's radio duty cycle is at 90 % or more.

## Reporting a Vulnerability

If you discover a security vulnerability within this project:

1. **Do NOT open a public GitHub issue.**
2. Report the vulnerability privately via **GitHub Private Vulnerability Reporting** at:
   `https://github.com/Ebenhoeh80/ha-maxcube/security/advisories/new`
3. Include reproduction steps, the affected version of the integration and of Home Assistant, and a proof
   of concept if you have one.

We will acknowledge receipt within a few days and work with you on a coordinated disclosure.
