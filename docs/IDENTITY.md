# Identity of a Cube

A physical MAX! Cube is one device for its whole life, however its network address changes. This page
records what identifies what, the rules the code follows, and how existing installations were migrated.

## What identifies what

| Thing | Identity | Stable? |
|---|---|---|
| Config entry (`unique_id`) | serial number of the Cube (for example `JEQ0355273`) | yes, printed on the Cube |
| Title shown in the integration list | `MAX! Cube <serial>` (a name chosen by the user is kept) | yes |
| Hub device in the device registry | identifier `(maxcube_local, <serial>)` | yes (unchanged since 1.1) |
| Thermostats, contacts, wall thermostats | identifier `(maxcube_local, <radio address>)` | yes, radio addresses do not change |
| Entities | unique id `<radio address>…` or `<serial>_…` | yes (unchanged) |
| **Network address** | stored in `data["host"]` only | **no**, it is data, not identity |

The address of a Cube changes: DHCP, a new router, and a Cube that starts without a lease answers from its
factory address `192.168.0.222`. Before 1.3.3 the address was the unique id and part of the title, so
every such change broke the identity (observed on 2026-11-20: the entry kept the title `MAX! Cube (192.168.10.60)`
while it pointed at `192.168.0.222`).

## Rules in the code

1. **A new entry takes its serial number from the Cube** (config flow: connect, read the serial from the first
   message, `async_set_unique_id(serial)`); `_abort_if_unique_id_configured(updates={host, port})` makes a second
   attempt for a known Cube update the address instead of adding a duplicate.
2. **Discovery uses the official integration-discovery flow.** After startup the integration broadcasts once
   (UDP 23272) and starts a flow for every Cube whose data port answers (`discovery_flow.async_create_flow`,
   source `integration_discovery`). A new Cube appears under *Discovered*; a known Cube gets its new address and
   the entry is reloaded once (`updates` with reload). A Cube that answers only from an address that cannot be
   reached (the factory address) is not offered and never saved.
3. **A changed address is only data.** The coordinator (failed poll, or failed setup) looks the Cube up by serial
   number, checks that the data port answers, saves `data["host"]` and reloads. Identity and title stay.
4. **The Cube that answers must be the Cube of the entry.** Every connection compares the serial number in the
   first message with `data["cube_serial"]`. A different Cube at the saved address (an address taken over, a replaced
   Cube) is treated like an unreachable one: the right Cube is searched by serial number, otherwise setup retries.
   The devices of one Cube are never mixed into another Cube's entry.
5. **The connection test closes the connection** (the Cube accepts one client at a time).
6. **Reloads:** only changed options reload the entry. A new address or identity is saved in the entry's data and
   reloaded by whoever saved it (discovery flow or coordinator), so there is exactly one reload.

## Migration of existing installations

Entries created by 1.0 to 1.3.2 have `version 1, minor_version 1` and the address as unique id.
`async_migrate_entry` raises them to **minor version 2** without removing and re-adding anything:

- If the serial number is stored in the entry (every entry that had a successful setup since 1.1): `unique_id` becomes
  the serial, a generated title (`MAX! Cube (address)`) becomes `MAX! Cube <serial>`; a title the user chose stays.
- If it is not stored: the entry stays minor version 1 and is finished at its next successful setup, when the Cube answers.
- If another entry already uses that serial number, the entry keeps its address as identity (and logs it) instead of
  creating a duplicate.
- An entry of a newer major version is refused (`False`), as Home Assistant requires.
- **Nothing in the registries changes:** devices and entities were never identified by the address, so the device
  and entity registry entries, entity ids, areas and customisations stay. This is tested: the sets of entity and device
  ids before and after the migration are equal.
- A downgrade to 1.3.2 keeps working: the entry is still version 1; the older code simply reads the address from its data.

## Decisions and rejected options

- **Minor, not major version:** the data stays readable by older code, which is what a minor version means.
- **Update the address inside the coordinator instead of only through the discovery flow:** the discovery flow cannot run
  while the entry is being set up (no reload then), and a failed poll needs the new address at once. Both paths make the
  same change (`data["host"]`), documented in the code.
- **MAC address as a connection in the device registry:** the Cube does not report its MAC address in the protocol; the
  serial number is the only stable identifier it reports.
- **Reauth:** not applicable, the Cube has no authentication. **Reconfigure** (change the address by hand) is part of the
  1.4.0 work and uses `_abort_if_unique_id_mismatch` so that a wrong Cube is refused.
- **Repair for an unreachable Cube:** not added; the integration cannot fix it, and unavailable entities and the log line
  about a moved Cube already show it.
