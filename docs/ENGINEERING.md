# Engineering notes: architecture, failure modes, measurements, quality gates

This page records how the integration works, where its time goes, what can fail and how it
recovers, what is checked automatically, and which options were rejected and why. Numbers are
measured, with date and method. Last updated: 2026-11-25 (after the v1.8.5 live verification and the stale-cache write guards).

## 1. Architecture and data flow

```
 Home Assistant                       integration "maxcube_local"                      outside
 ───────────────                      ───────────────────────────                      ───────
 climate / services ──► climate.py ──► coordinator.async_cube_call()  (one call at a time)
 poll every 60 s ─────► coordinator._async_poll()  ──────────────────► executor thread
                                                                          │ library maxcube-api
                                                                          ▼
                                                              TCP 62910  ──────────►  MAX! Cube
 config flow ─────────► discovery.discover_cubes()  UDP 23272 broadcast ──────────►  (finds the Cube)
 setup / failed poll ─► coordinator._async_find_new_host()  (serial number, reachable address only)
```

- **One connection per poll.** The Cube accepts a single client. Every poll opens a short connection and
  closes it again, so the MAX! app can use the Cube in between, and each poll starts with a fresh `H`
  message (radio duty cycle, free memory slots). The library is synchronous: every call runs in the
  executor, never on the event loop.
- **Discovery binds UDP 23272 locally.** The Cube addresses its reply to the sender's port, not to an
  arbitrary source port (hardware-verified in `app-maxcube`, `HARDWARE-VERIFY.md` §3). If that port is
  already owned by another process, discovery returns no result instead of sending from a port on
  which the reply can never arrive.
- **Weekly programme:** read from the Cube's `C` messages; written with a message built in `schedule.py`
  (the library's `set_programme` loses half degrees); verified by reading back after about five minutes.
  Since 1.8.1 a day that still differs is resent once; its own follow-up check only warns. Writes are
  refused at 90 % radio duty cycle and the retry obeys the same limit (see §3 and §7).
- **Entities:** climate, sensors, binary sensors, button per Cube; devices that appear later get their
  entities at the next poll (`async_add_devices_as_they_appear`).

## 2. Concurrency and lifecycle

- **Polls, commands, snapshots and disconnect share one dedicated worker thread**
  (`coordinator._async_io_call`, a `ThreadPoolExecutor(max_workers=1)`). An `asyncio.Lock` would be released
  when a Home Assistant task is cancelled while its executor thread still talks to the Cube; the next call
  could then overlap on the single-client port. A second, independent lock keeps a programme write and its
  read-back together. Before 1.4.0 a poll and a command ran in different executor threads and could overlap;
  a cancellation test now proves that even a cancelled call still blocks the next one until it has finished.
  Short connection checks during discovery, the config flow and the UDP reboot use Home Assistant's shared
  executor; they are brief but are not part of this per-entry serialisation.
- **The worker queue is intentionally unbounded.** It belongs to one config entry, every call is awaited
  by its caller and refreshes are debounced by the coordinator. Adding a semaphore around `submit` would
  reintroduce the cancellation bug: it would be released while the worker still holds the Cube's port.
- **Snapshots are copied in the same worker**, so the copy cannot overlap Cube I/O. It is not atomic with
  the poll: identity checks and metadata writes run on the event loop, and another task can queue a command
  in between. Previously the copy ran unlocked in another executor thread and a command could mutate the
  library objects during it.
- **Read-back after a command** is merged for 2 s (Home Assistant's default is 10 s, which left the second
  of two quick changes unseen for that long). It only refreshes Home Assistant's state from the next
  poll; it is **not** a hardware confirmation, and `climate.py` does not validate it. Measured on the
  real Cube on 2026-11-25 (C# gateway, separate connection, `0x40` setpoint): a read started at once
  still showed the old setpoint; a read started about 2 s later showed the new value at about 4 s; a
  third read at about 11 s still showed it. Acceptance therefore takes a few seconds on this
  hardware, so an early read-back can legitimately be stale (see §4).
- **The first refresh reads the Cube twice** (`coordinator.py:157-176`, `:202-226`, `:249-265`,
  `:399-414`; `__init__.py:217`). The `LinkStatusMaxCube` constructor performs a blocking initial
  read; `async_config_entry_first_refresh()` (Home Assistant core 2025.3,
  `helpers/update_coordinator.py:283-308`) then calls `_async_setup()` and immediately
  `_async_refresh()` → `_async_update_data()` → `_async_poll()` → `cube.update()`. This is a one-off
  cost of about 2 × 700 ms at setup, not a repeated read-back. Reusing the constructor data and
  skipping the poll was rejected: it would change identity checking and duty-cycle handling for a
  one-time saving. A regression test counts both reads (`tests_ha/test_integration.py`).
- The entry holds the Cube address in its data; it is reloaded when options change.

## 3. Failure modes and recovery

| Failure | Effect | Recovery / mitigation |
|---|---|---|
| Cube off or restarted | all devices unavailable | polls fail; the Cube is looked up by serial number (every 5 min) |
| **Cube answers from its factory address `192.168.0.222`** (no DHCP lease yet) | 1.3.1 saved this unreachable address; the entry stayed in *retry* for good (observed 2026-11-20) | fixed in 1.3.2: an address is saved only if the data port answers there; the lookup also runs at setup |
| Cube got a new DHCP address | polls fail | found by serial number, saved, entry reloads |
| MAX! app holds the single connection | a poll is refused | one repeat after 1 s (refused/reset only); timeouts are not repeated |
| Poll and command overlap | one is refused | calls are serialised (see above) |
| Duty cycle at 90 % or more | programme writes would be dropped | the service refuses to write; a repair hint appears after ten minutes and clears below 80 % |
| Cube unreachable for more than six hours | all devices unavailable | repair hint (timer from the first failed poll), cleared by the next successful poll |
| Command cannot reach the Cube, or is refused | the user action fails | translated `HomeAssistantError` (`cube_unreachable`, `command_rejected`) |
| Device removed from the Cube | stale device in Home Assistant | removed from the registry after the next reload or restart (the library only adds devices) |
| Empty device list after a failed read | would wipe the registry | an empty list is never trusted |
| **Low-battery flag comes and goes** (observed 2026-11-20: gaps of 1 to 5 minutes for hours on one thermostat) | the sensor and the repair hint flap; an automation with "on for 30 minutes" cannot fire | the report is held for 15 minutes after the last time the Cube sent it (`BatteryHold`) |
| **After a battery change the Cube keeps the device in error for hours** (observed 2026-11-21: `Error` from 09:41 to 11:02, "not initialized" flickering until 13:12) | the status sensors and the repair hint stay on although the thermostat works | none possible: the Cube sets and clears the flags itself while it sets the thermostat up again; the hint text says so |

## 4. Where the time goes (measured)

Method: the integration's own cube class run against the real Cube from the development machine on
2026-11-20 (integration disconnected, so no competition for the single connection), `cProfile` for one poll.

| Action | One connection per poll (as built) | Standing connection |
|---|---|---|
| Poll | median 700 ms (601 to 1699 ms) | 99 ms |
| Set a target temperature | median 900 ms (first call 1.9 s) | 198 ms |
| CPU time of a poll | practically 0 (the time is `connect`/`recv` waits in the executor) | – |

A standing connection would be about 7 times faster, but it locks out the MAX! app and delays the
duty-cycle reading, so it was not built. A user action is read back once: command plus read-back is
about 1.6 s, well below the 2 to 10 s that were the target. Side effect of the benchmark: six
no-change target writes raised the Cube's duty cycle from 4 % to 21 % (it decays by itself).
Identical target temperatures and modes are therefore skipped before a telegram is sent.

Rechecked on the real Cube on 2026-11-25 with the app's own `CubeGateway` (room 2, `0x40`
`setpoint 17.0 → 17.5 °C`, restored to 17.0 °C afterwards): `S: dutyCycle=3`, immediate read
`Permanently / 17.0`, read started about 2 s later `Permanently / 17.5` at +4.1 s, third read
still `17.5` at +10.8 s; restore read `17.0` after 6 s. **BEOBACHTUNG:** the Cube's reported
state lags a setpoint command by a few seconds. **INFERENZ:** the 2 s debounce is a pragmatic
state refresh, not a confirmation; a stale value in the first read is expected and the later
poll corrects it. No code change was made (P3 closed as documented behaviour).

## 5. Quality gates (all run in CI)

| Judge | Gate | Result |
|---|---|---|
| Ruff (E, W, F, I, B, C4, UP, SIM, RET, PL, C901, ANN) | no findings | pass (tests are exempt from PLR2004, PLC0415 and ANN) |
| MyPy with the real Home Assistant types | no errors | pass |
| pytest, unit tests (Python 3.12, 3.13) | all pass | 175 passed, 2 xfailed (local recheck 2026-11-25) |
| pytest in a real Home Assistant core (2025.3 and 2026.2) | all pass | 128 passed in each for 1.8.3; 147 passed locally for 1.8.6 (HA 2026.10.4, 2026-11-25) |
| Coverage (both suites combined) | at least 95 % | 96.43 % |
| hassfest, HACS validation | valid | pass |
| xenon | absolute B, modules A, average A | pass |
| CodeQL (security-and-quality) | no new alerts | pass |
| Home Assistant Quality Scale | `quality_scale.yaml` | Gold; Platinum open (`async-dependency`, `strict-typing`) |

Rechecked locally on 2026-11-25 for 1.8.6: Ruff clean, Xenon clean (`--max-absolute B`), MyPy clean
with the real Home Assistant types, 175 unit tests passed (2 xfailed), 147 Home Assistant tests passed,
`node --check` clean and `git diff --check` clean. CI additionally runs Hassfest and HACS `validate`,
both green for 1.8.5 (1.8.6 pending).

Not available locally: SonarQube, Semgrep, py-spy and Scalene. A live Cube test was possible on
2026-11-25: the integration is loaded in HAOS (log level now `WARNING` after the investigation), and raw `s:` telegrams were observed
in the log. It confirmed that RF flag `04` addresses a room and that five devices had wrong internal
room IDs in their `C:` configuration, which coupled setpoint commands between rooms. Correcting those
IDs with `0x22` is a Cube configuration change, not part of the integration code.

## 6. Decisions and rejected options

- **Standing connection:** rejected (see 4).
- **Rewriting the library as an asynchronous client:** strategic option (Platinum `async-dependency`, removal of
  devices at run time); needs tests at the real Cube.
- **Link-status diagnostics from a contributor (pull request #3):** released in 1.4.0 after the rebased
  version in #17 and the origin/licence question were resolved; the current diagnostics page documents it.
- **Mode changes in 1.8.3:** a target temperature, `off`, `heat` and temperature presets all send a
  combined `MANUAL` + setpoint command. `off` is `MANUAL` at 4.5 °C; `heat` restores the last real setpoint
  (programme setpoint, then comfort setpoint as fallback). `set_target_temperature` alone leaves `AUTO`
  in place and the programme overwrites the value at the next poll.
- **Two protocols, one local transport:** `B:/G:/J:/P:/O:/V:/W:` and `g:` belong to the HTTP remote proxy
  of the MAX! Cloud (shut down since 2023-07-01) and are deliberately not implemented here. `e:/d:` are
  real TCP commands of the desktop app, but this integration does not use them as a cloud transport.
  Everything here talks local TCP/UDP to the Cube.

## 7. Open items

- Platinum rules `async-dependency` and `strict-typing`.
- The single retry for a weekly programme projects the radio cost of its days, but still uses the
  duty cycle of the last poll; another Cube call can raise it before the resend. Low residual risk.
- `split_l_entries` stops at a bad length byte without resync; the rest of that `L` message is discarded.
  Documented and covered by a test, not changed (K2).
- A day with 8..13 switch points is refused: one telegram carries seven, and although the original
  app sends a second one with six and a flag in byte 10 bit 4, the Cube's acceptance of that second
  telegram is not verified. Changing the seven-point limit is a hardware-verification task.
- A short `L` entry leaves the device mode unknown; Home Assistant requires an `hvac_mode`, so the
  entity currently reports `AUTO`. Holding the last known mode would change automation semantics and
  needs a product decision.
- Partial failures when writing several targets from the schedule card leave all affected days
  marked as changed, so already confirmed targets may be written again. Per-target error tracking is
  a UI change, not a radio-safety fix.
- Pairing (`n:`/`N:`/`x:`) is a product decision for 1.9.0 with an admin guard and a polling pause, not a
  quickwin. The Cloud remote proxy and `e:`/`d:` as cloud transport stay excluded (see §6).

## 8. Closed: P3 read-back and the double read at setup (2026-11-25)

- **Line-number correction:** `climate.py:407` is `await self._set_mode(MAX_DEVICE_MODE_BOOST)`.
  The refresh calls are `climate.py:450` (setpoint) and `:459` (mode), both
  `await self.coordinator.async_request_refresh()`.
- **Read-back purpose:** refresh Home Assistant's state, not confirm the radio telegram. No code
  path compares the read-back value with the requested one or raises on a mismatch. The hardware
  measurement in §4 shows why: on a real Cube the new setpoint appears in the read only after a
  few seconds, so an immediate read can report the old value without the write having failed.
  Treating it as confirmation would be wrong; no change was made.
- **Double setup read:** confirmed by code and by Home Assistant core 2025.3 (§2). It is one complete
  read in the library constructor plus one in the first poll. Cost is one-time; correctness is
  unaffected. Skipping the second read would require changing `_connect`, identity checking and
  duty-cycle freshness for a one-time saving — rejected as a riskier change than the cost it removes.
- **Verification:** regression test `tests_ha/test_integration.py` counts one construction and two
  reads after setup, plus one more after a refresh. The note about local HA tests only applied to
  the plain unit-test environment; with HA installed locally (2026.10.4) all `tests_ha` tests run.
  CI runs `tests_ha` against HA 2025.3 and 2026.2.

## 9. Closed: stale-cache no-change guards (2026-11-25)

- **Live observation:** after a `climate.set_temperature` the new target became visible in HA only
  at the next 60 s poll. A second, different request sent inside that window could be dropped by the
  no-change guard: it compared the request with the last poll's snapshot, which still held the old
  value. The same applied to `_set_mode` after a setpoint had sent `MANUAL` in the combined telegram.
- **Fix:** the thermostat remembers the last sent temperature and mode until a coordinator update
  replaces the snapshot. Both the temperature and the mode guard compare against that pending value
  first; the snapshot is only used when nothing is pending. The pending temperature is also used for
  the reported target, so the UI shows a setpoint immediately instead of waiting for the poll.
- **Radio cost:** unchanged for normal use. Repeating an identical request is still suppressed, and
  no extra telegram is sent unless the caller actually asks for a different value.
- **Verification:** two regression tests in `tests_ha/test_climate_temperature.py` mock
  `async_request_refresh` to simulate the missing poll; both failed before the fix and pass after it.

## 10. Observability and quality gates (2026-11-27)

- **Telegram correlation (P1-1):** `telegram_log.py` records sent telegrams and correlates them with
  `L:` answers and the Cube's `S:` status. The documented wire format is
  `S:<duty hex>,<result>,<free slots hex>`; `result = 1` means the Cube discarded a command and
  logs a warning. Duty cycle, free slots, locally pending/rejected counts appear on the diagnostic
  sensors and in the redacted diagnostics download. The protocol has no queue-length field, so
  the misleading "Queued telegrams" sensor was removed in 1.9.1. This is observation only: the
  cause of the live setpoint cross-talk is still unknown, so **wait at least 60 s between room
  changes**.
- **Actions (P1-3):** integration-wide actions are registered from `services.py` via
  `async_setup_services`, with `CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)`.
  `get_schedule`/`set_schedule` use the official entity-service helper on HA 2025.10+ and the
  platform route on the declared 2025.3 minimum, so no action is registered twice. Reboot is an
  admin action and uses the serial read from the Cube, never a user-supplied address.
- **Gates (P1-4):** the combined run still requires 95 % overall; `scripts/check_coverage.py`
  applies the floor per module (two socket-hardware modules are listed as exempt in the script).
  `mypy --strict --follow-imports=skip` runs on the pure-logic modules in CI. Diagnostics are
  checked key by key in `tests_ha/test_diagnostics.py`, and `tests/test_release_consistency.py`
  checks manifest/changelog version, DE/EN links and translation parity.
- **Test framework (P2-1):** `pytest-homeassistant` replaces the broken
  `pytest-homeassistant-custom-component`; the pinned HA-2025.3 job was permanently red and now
  guards pure logic on the oldest supported Python instead.
- **Parser and reconnect (P2-3/P2-4):** `M:` index/total is validated, only a complete message
  replaces the remembered configuration, and `L:` entries stay inside their length byte. A failed
  connection is slowed down with capped backoff and recorded in diagnostics.
- **Async client (P2-2):** `async_client.py` is a typed asyncio building block with line framing,
  timeouts, serialisation and a cancellation-safe lock; it has strict-mypy and unit coverage but
  is **not yet wired into the coordinator**. `async-dependency` therefore remains `todo`.
- **Runbook (P2-5):** `RUNBOOK.md` documents the `C:`↔`M:` comparison and the 60 s rule. The
  `0x22` correction was observed once; its stability is unverified.
