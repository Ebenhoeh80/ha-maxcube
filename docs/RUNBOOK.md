# Runbook: room assignment and radio commands (MAX! Cube)

This is an **operating guide**, not a code fix. It documents how to read the
Cube's answers when a command appears to reach the wrong room. It changes
nothing on the hardware by itself.

## Before changing several rooms

Wait **at least 60 seconds** between commands that change different rooms.
Six room changes 15 seconds apart were observed to cross-talk on one system;
a single change did not. The cause is still unknown, so this is an operating
rule and not a claimed fix. The integration does not queue or resend commands —
the Cube owns its queue.

## Observe before theorising

1. Download **Diagnostics** for the integration entry (⋮ → Download diagnostics).
2. Look at `cube.queue_status`, `cube.pending_telegrams`,
   `cube.rejected_commands` and `telegram_observation`. The Cube's `S:` answer is
   `S:<duty hex>,<result>,<free slots hex>`; it has **no** queue-length field.
   - `queue_status.status = 1`: the Cube **discarded** a command. The integration
     logs a warning in this case.
   - `queue_status.duty_cycle = 100`: the radio budget is exhausted; commands
     are refused.
   - `queue_status.free_memory_slots`: free slots reported by the Cube.
   - `pending_telegrams`: telegrams sent by Home Assistant that have not yet
     been acknowledged by an `L:` answer. This is **not** a Cube queue count
     and **not** proof that a setting arrived at a thermostat.
3. Only then decide whether this was a rejected command, a busy radio or a
   wrong room.

## Compare `C:` with `M:` after a restart or programme change

Each thermostat keeps its own room code in its `C:` answer; the Cube lists the
rooms in the `M:` answer. These are two different sources. A deviation was
observed on five of nine devices on one system; a correction with `0x22` worked
there, but its stability after a Cube restart or weekly-programme change is
**not verified**.

1. Take a raw protocol trace around a Cube restart or a weekly-programme write.
2. Read the room code from each device's `C:` frame and compare it with the
   room list from `M:`.
3. If they differ, correct the device with the MAX! software and repeat the
   comparison. Do not treat the correction as permanently verified.
4. Do **not** switch group-addressed commands to one telegram per device just
   because of this: group addressing deliberately saves radio budget.

The integration reads room IDs from `M:` and does **not** write `C:` codes.
Factory reset (`a:`) is intentionally not offered.

## What stays open

- The root cause of setpoint deviations after a Home Assistant restart.
- Port 62910 refusing connections after a pairing/metadata session (ping and
  UDP discovery still work). The integration records failed attempts with
  backoff in diagnostics; it does not claim a fix.
- The exact duty-cycle limit and the stability of the `0x22` correction.
- The meaning of the second of the 13 weekly-programme slots ("7 + 6").

None of these are asserted as solved. See `ENGINEERING.md` for the known limits.
