# Engineering notes: architecture, failure modes, measurements, quality gates

This page records how the integration works, where its time goes, what can fail and how it
recovers, what is checked automatically, and which options were rejected and why. Numbers are
measured, with date and method. Last updated: 2026-11-20 (after release 1.3.2).

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
- **Weekly programme:** read from the Cube's `C` messages; written with a message built in `schedule.py`
  (the library's `set_programme` loses half degrees); verified by reading back after about five minutes.
- **Entities:** climate, sensors, binary sensors, button per Cube; devices that appear later get their
  entities at the next poll (`async_add_devices_as_they_appear`).

## 2. Concurrency and lifecycle

- **All Cube calls are serialised** (`coordinator.async_cube_call`, an `asyncio.Lock`; a second lock keeps a programme write and its read-back together and cannot be merged with the first, which the read-back needs). Before 1.4.0 a poll
  and a command ran in different executor threads on the same connection object and could overlap. A test
  that records how many threads are inside a Cube call at once failed on the old code
  (`assert 2 == 1`) and passes now.
- **Read-back after a command** is merged for 2 s (Home Assistant's default is 10 s, which left the second
  of two quick changes unseen for that long).
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

## 5. Quality gates (all run in CI)

| Judge | Gate | Result 2026-11-20 |
|---|---|---|
| Ruff (E, W, F, I, B, C4, UP, SIM, RET, PL, C901, ANN) | no findings | pass (tests are exempt from PLR2004, PLC0415 and ANN) |
| MyPy with the real Home Assistant types | no errors | pass (12 before) |
| pytest, unit tests (Python 3.12, 3.13) | all pass | 46 passed |
| pytest in a real Home Assistant core | all pass | 38 passed |
| Coverage (both suites combined) | at least 95 % | 95.7 % |
| hassfest, HACS validation | valid | pass |
| xenon | absolute B, modules A, average A | pass |
| CodeQL (security-and-quality) | no new alerts | pass |
| Home Assistant Quality Scale | `quality_scale.yaml` | Gold; Platinum open (`async-dependency`, `strict-typing`) |

Not run: SonarQube, Semgrep, py-spy, Scalene (not available on the development machine).

## 6. Decisions and rejected options

- **Standing connection:** rejected (see 4).
- **Rewriting the library as an asynchronous client:** strategic option (Platinum `async-dependency`, removal of
  devices at run time); needs tests at the real Cube.
- **Link-status diagnostics from a contributor (pull request #3):** the technical review is done and a rebased
  branch exists, but it is not released until the contributor confirms the origin of the code (the docstrings
  cite GPL sources while this repository is MIT).

## 7. Open items

- Platinum rules.
