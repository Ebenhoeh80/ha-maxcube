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
2. **Discovery uses the official discovery flows.**
   - **DHCP** (`manifest.json`: hardware address prefix `001A22*`, eQ-3): Home Assistant sees the DHCP request of a
     Cube when it starts or gets a new address and starts the flow. This finds the **first** Cube without any entry
     and follows a known Cube to its new address. Other eQ-3 devices share the prefix; the flow connects first and
     ignores everything that does not answer as a Cube.
   - **Broadcast scan** (UDP 23272) once after startup, for further Cubes and for known ones whose address changed
     while Home Assistant was off (`integration_discovery`). It only runs while the integration is loaded (there is
     an entry); a Cube that is set up at the same address is skipped and not contacted.
   - A new Cube appears under *Discovered*; a known Cube gets its new address saved. A Cube that answers only from
     an address that cannot be reached (the factory address) is never offered or saved.
3. **A changed address is only data, and the update listener reloads.** Whoever learns the new address (discovery
   flow, or the coordinator after a failed poll or failed setup: it looks the Cube up by serial number and checks
   that the data port answers) saves `data["host"]`; the entry's update listener schedules one reload when the
   options or the address changed (the pattern Home Assistant asks for; the flows do not reload themselves).
   Identity and title stay.
4. **The Cube that answers must be the Cube of the entry.** Every connection compares the serial number in the
   first message with `data["cube_serial"]`. A different Cube at the saved address (an address taken over, a replaced
   Cube) raises `WrongCubeError`: at setup the right Cube is searched by serial number, otherwise the entry retries;
   during a poll the refresh fails with a distinct identity error instead of mixing devices. The devices of one Cube are
   never mixed into another Cube's entry.
5. **One Cube, one entry** (the check and the claim of the identity happen without an `await` in between, so two entries
   starting at the same time cannot both win). A second entry whose Cube already belongs to another entry stops at setup with the error
   "already managed by the entry …" (`ConfigEntryError`); it creates no devices. Adding a Cube by hand while a
   discovery for it is waiting works (`raise_on_progress=False`).
6. **The connection test closes the connection** (the Cube accepts one client at a time); an unexpected error in
   the dialog is shown as "unknown" instead of failing the dialog.
7. **An entry whose unique id was overwritten** (for example by version 1.3.2 after a downgrade) is put right at its
   next setup: the identity is checked against the serial number of the Cube that answers, not only the minor version.

## Migration of existing installations

Entries created by 1.0 to 1.3.2 have `version 1, minor_version 1` and the address as unique id.
`async_migrate_entry` raises them to **minor version 2** without removing and re-adding anything:

- If the serial number is stored in the entry (every entry that had a successful setup since 1.1): `unique_id` becomes
  the serial, a generated title (`MAX! Cube (address)`) becomes `MAX! Cube <serial>`; a title the user chose stays.
- If it is not stored: the entry stays minor version 1 and is finished at its next successful setup, when the Cube answers.
- If another entry already uses that serial number, the entry keeps its address as identity (and logs it) instead of
  creating a duplicate.
- An entry of a newer major version is refused (`False`), as Home Assistant requires.
- **No registry entry is created, removed or re-keyed:** devices and entities were never identified by the address, so
  entity ids, areas and device names chosen by the user stay. This is tested: the sets of entity and device ids
  before and after the migration are equal. (The integration refreshes the hub's name and firmware
  and the names of the devices from the Cube's data; a name the user chose in Home Assistant is never overwritten.)
- A downgrade to 1.3.2 keeps working: the entry is still version 1; the older code simply reads the address from its data.
  1.3.2 writes the address back into the unique id when the Cube gets a new address; the next setup with this version
  puts it right (rule 7). Adding the Cube again by hand while on 1.3.2 can create a duplicate; that cannot be
  prevented from here.
- An entry that cannot be migrated at the first start (no serial number stored and the Cube does not answer) is
  finished at its next successful setup.

## Decisions and rejected options

- **Minor, not major version:** the data stays readable by older code, which is what a minor version means.
- **Update the address inside the coordinator instead of only through the discovery flow:** the discovery flow cannot run
  while the entry is being set up (no reload then), and a failed poll needs the new address at once. Both paths make the
  same change (`data["host"]`), documented in the code.
- **MAC address as a connection in the device registry:** the Cube does not report its MAC address in the protocol; the
  serial number is the only stable identifier it reports.
- **A replaced Cube** (new serial number at the old address) is refused (`WrongCubeError`, the entry retries): its
  devices must not be mixed into the old Cube's entry. Remove the entry and add the new Cube; there is no automatic
  takeover. The reconfigure flow is not a replacement for it: it exists for a manual address change, while the automatic rediscovery below covers the
  real case (the same Cube got a new address) without asking the user to enter one.
- **Spoofing:** the Cube's protocol has no authentication, so a host on the local network that answers the broadcast and
  accepts the connection can pose as a Cube, and the serial number it claims is not proof. The serial-number comparison
  on every connection (`WrongCubeError`) protects against *mix-ups* (two Cubes, an address taken over), not against
  forgery. An address is only saved after the device at that address has answered with the expected serial, and a
  candidate without a serial is rejected (`_async_connect_at`). When an existing entry would be redirected, the
  config flow checks the claimed serial at the new host as well. This stops a forged discovery reply from moving an
  entry permanently; it does not authenticate the Cube itself.
- **Reauth:** not applicable, the Cube has no authentication. A changed address is found by serial number after a failed
  poll or at startup and saved automatically; the reconfigure flow is only for entering an address by hand.
- **Repair for an unreachable Cube:** since 1.5.0 a hint (not fixable by the integration) appears after six hours without an
  answer; before that, unavailable entities and the log line about a moved Cube show it.
