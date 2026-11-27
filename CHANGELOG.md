# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.9.1] - 2026-11-27

### Fixed
- **Der `S:`-Parser liest wieder echte Cube-Antworten.** Die Protokollreferenz definiert `S:<Funkauslastung hex>,<Ergebnis>,<freie Plätze hex>` mit drei Feldern. Die Fassung 1.9.0 erwartete vier Felder in falscher Reihenfolge und verwarf damit jede echte Antwort: `cube_status` blieb leer und eine verworfene Befehlswarnung konnte nicht auslösen. Ein lokales `S:26,0,31` wird jetzt als 38 % Funkauslastung, Ergebnis 0 und 49 freie Plätze gelesen; `S:FF,1,00` als 100 %, verworfen, 0 Plätze.
- **Der Sensor „Wartende Funkaufträge" wurde entfernt.** Er behauptete eine Warteschlangenlänge, die das Protokoll nicht meldet. `pending_telegrams` bleibt als Beobachtung lokal gesendeter, noch nicht per `L:` bestätigter Telegramme in den Diagnose-Sensoren und im Diagnosebericht sichtbar; es ist weiterhin kein Beweis für eine Ankunft am Thermostat. Das Runbook beschreibt jetzt das korrekte Format und die Bedeutung der Felder.

## [1.9.0] - 2026-11-27

> Hinweis: Pairing ist weiterhin **nicht** unterstützt und ist nicht Teil dieser Version.

### Added
- **Funkaufträge sind beobachtbar.** Gesendete Telegramme werden mit den `L:`-Antworten der Geräte korreliert; der `S:`-Status des Cube (1 = verworfen), wartende Aufträge, freie Slots und Funkauslastung erscheinen als Attribute der Diagnose-Sensoren und in den Diagnostics. Ein verworfener Befehl löst eine Warnung mit dem Hinweis auf mindestens 60 Sekunden Abstand zwischen Raumbefehlen aus. Das ist eine Beobachtung, kein Root-Cause-Fix für die live beobachtete Sollwert-Kopplung.
- **Neuer Sensor „Wartende Funkaufträge"** zeigt die aktuelle Warteschlange des Cube; ein fehlgeschlagener Verbindungsaufbau wird mit Backoff gedrosselt und in den Diagnostics sichtbar gemacht.
- **Neustart als Admin-Aktion.** Der Reboot nutzt die vom Cube gelesene Seriennummer und ist nur für Administratoren aufrufbar; das Werksreset bleibt tabu.
- **Runbook (DE/EN)** für den `C:`↔`M:`-Vergleich und die 60-s-Regel bei Raumwechseln.
- **Typisierter Async-Client-Baustein** mit Zeilenframing, Timeouts und cancellingsicherem Lock; er ist noch nicht im Coordinator aktiviert.

### Changed
- Actions werden zentral in `services.py` registriert; Entity-Actions nutzen ab HA 2025.10 den offiziellen Helper, ältere Cores behalten den Plattformweg. Das Test-Framework nutzt `pytest-homeassistant`, und der dauerhaft blockierende Mindest-HA-Job prüft jetzt die reine Logik auf der ältesten unterstützten Python-Version.
- Der `M:`-Parser prüft Index/Gesamtzahl und ersetzt die gemerkte Konfiguration nur durch eine vollständige Nachricht.
- Qualitäts-Gates: Coverage-Grenze pro Modul mit begründeten Ausnahmen für Socketpfade, `mypy --strict` für die reinen Logikmodule, Diagnostics- und Release-Konsistenzprüfung inklusive DE/EN-Parität. `strict-typing` und `async-dependency` bleiben als Platinum-Ziele dokumentiert.

## [1.8.6] - 2026-11-25

### Fixed
- **Ein zweiter Sollwert innerhalb eines Poll-Intervalls geht nicht mehr verloren.** Der Cube bestätigt ein Telegramm in Sekunden, der nächste HA-Poll kann aber eine Minute auf sich warten lassen. Die "Keine Änderung"-Prüfung verglich bisher nur den Poll-Cache: Wurde erst ein neuer Wert gesetzt und dann innerhalb dieses Fensters der alte Wert erneut angefordert, wurde das zweite Telegramm unterdrückt und der Cube blieb auf dem ersten Wert. Sollwert und Modus werden jetzt bis zur nächsten Bestätigung als "gesendet" vorgemerkt und gegen diesen Wert geprüft.
- **Ein direkter Moduswechsel nach einem Sollwert wird nicht mehr verschluckt.** Ein Sollwert sendet Modus `MANUAL` zusammen mit der Temperatur. Eine direkt danach kommende Anfrage auf `Auto` sah im veralteten Cache noch `Auto` und wurde verworfen; jetzt gilt auch hier der vorgemerkte Modus.
- **Die Anzeige aktualisiert den Sollwert sofort nach dem Senden.** Bisher war der neue Wert erst nach dem nächsten Poll (bis zu 60 s) in Home Assistant sichtbar.

## [1.8.5] - 2026-11-25

### Fixed
- **Wandthermostate zeigen keinen erfundenen Status „Leerlauf" mehr.** `hvac_action` hat fehlendes Ventilfeedback (`valve_position = None`) wie ein geschlossenes Ventil behandelt. Ohne Stellrückmeldung wird jetzt gar keine Aktion gemeldet; `Aus` bleibt weiterhin `off`, und Heizkörper mit bekanntem Ventil behalten `heating`/`idle`.
- **Ein expliziter Sollwert bleibt auch bei `hvac_mode: auto` erhalten.** Seit 1.8.4 hat die Kombination aus Temperatur und `auto` die Temperatur verworfen und auf den Wochenprogramm-Sollwert zurückgesetzt – das konnte Räume ungewollt herunterregeln. Ein reiner Moduswechsel auf `Auto` nutzt weiterhin das Wochenprogramm; `off` und `heat` sind unverändert.
- **Ursache der beobachteten Sollwert-Kopplung zwischen Zimmern identifiziert und live behoben.** Fünf von neun MAX!-Geräten hatten abweichende geräteinterne Raumcodes in der `C:`-Konfiguration; Sollwertbefehle mit RF-Flag `04` (Gruppe/Raum) erreichten dadurch falsche Zimmer. Die Raumadressen wurden per `0x22` korrigiert und mit Isolationstests verifiziert. Das ist eine Konfigurationsmaßnahme am Cube und keine Code-Änderung dieser Version: Die Integration liest die maßgebliche Raum-ID unverändert aus der `M:`-Nachricht und behält die gruppenadressierten Befehle bei (ein Telegram für alle Geräte eines Raums).

## [1.8.4] - 2026-11-25

### Fixed
- **Unveränderte Sollwerte und Modi senden kein Funktelegramm mehr.** Automationen, die denselben Wert erneut setzen, erhöhten sonst den Duty Cycle des Cube (im Benchmark von 4 % auf 21 %).
- **Temperatur- und Modus-Befehle prüfen jetzt das Funkbudget.** Ab 90 % Duty Cycle wird der Befehl abgelehnt, statt dass die Bibliothek bis zu 30 s retryt und den einen Worker blockiert.
- **`climate.set_temperature` berücksichtigt jetzt `hvac_mode`.** `auto` behält das Wochenprogramm, `off` schaltet aus, `heat` setzt die übergebene Temperatur als MANUAL-Sollwert.
- **Sollwerte werden auf halbe Grade gerundet** statt vom Cube abgeschnitten zu werden (21,4 °C → 21,5 °C).
- **Der Wechsel auf `AUTO` funktioniert jetzt auch bei Wandthermostaten.** Die Bibliothek rief nach dem Senden `get_programmed_temp_at()` auf, das nur Heizkörperthermostate haben; der Service endete mit `AttributeError`, obwohl das Telegramm bereits gesendet war. Der Programmsollwert wird jetzt aus der eigenen, verlustfreien Wochentabelle gelesen.
- **Discovery bricht ab, wenn Port 23272 belegt ist.** Der Cube antwortet nachweislich auf den Absenderport 23272; ein stiller Fallback auf einen ephemeralen Port ließ die Antwort unerreichbar und die Suche erfolglos.
- **Das Wochenprogramm projiziert jetzt den Funkverbrauch aller Tage.** Sieben Tage bei 85 % Duty Cycle wurden bisher zugelassen, obwohl sie den Cube rechnerisch auf über 100 % bringen; dieselbe Projektion gilt jetzt für den einmaligen automatischen Nachversand.
- **Eine beschädigte gespeicherte `M:`-Nachricht lässt den Poll nicht mehr scheitern.** Der Fallback auf den Cache ist jetzt geschützt und verwirft unlesbare Inhalte.
- **Der Reboot-Button bleibt auch bei Socketfehlern still.** Die Socket-Erzeugung liegt jetzt im Fehlerbereich, und die Seriennummer wird wie bei der Discovery auf erlaubte Zeichen geprüft.
- **Die Wochenplan-Karte korrigiert das Löschen der letzten Zone.** Die verbleibende letzte Zone endet wieder bei 24:00; außerdem wird der „Geändert"-Tooltip jetzt korrekt übersetzt statt als Platzhalter angezeigt.
- **Zeitstempel und Staleness-Prüfung nutzen die injizierte Uhr**, sodass `L:`-Nachrichten auch in Tests und bei abweichender Systemzeit konsistent bewertet werden.
- **Ein ungültiger Längenbyte in einer `L:`-Nachricht verwirft jetzt den Rest der Nachricht**, statt Folgedaten falsch zuzuordnen.
- **Unerwartete Fehler beim Reconnect werden dem Nutzer als `unknown` gemeldet**, statt still verschluckt zu werden; nicht-numerische Temperaturwerte werden sauber als `bad_temperature` abgelehnt.

## [1.8.3] - 2026-11-24

### Fixed
- **„Aus" und Zieltemperaturen bleiben jetzt stehen.** Der Cube akzeptiert eine Solltemperatur nur zusammen mit einem Modus. Bisher wurde beim Setzen von `Aus`, `Heizen`, einer Zieltemperatur oder eines temperaturbasierten Presets der alte Modus beibehalten: Im Wochenprogramm (`AUTO`) verschwand der Wert beim nächsten Poll wieder, und die Anzeige blieb auf „Auto". Alle diese Befehle senden jetzt einen kombinierten `set_temperature_mode`-Befehl mit `MANUAL`. `Aus` ist damit `MANUAL` + 4,5 °C und wird auch so angezeigt.
- **„Heizen" stellt den letzten echten Sollwert wieder her** statt der 4,5 °C, die der Cube im Aus-Zustand meldet. Ist kein eigener Wert bekannt, wird der aktuelle Programmsollwert (sonst der Komfort-Sollwert) verwendet.
- Die Climate-Kacheln im Heizungs-Dashboard zeigen jetzt einen Modus-Umschalter (`climate-hvac-modes`), damit Auto / Heizen / Aus direkt aus der Kachel bedient werden kann.

## [1.8.2] - 2026-11-23

### Fixed
- **A cancelled Home Assistant task can no longer let two Cube calls overlap.** Polls, commands, writes and snapshots now share one dedicated worker thread, so a cancelled task cannot release a lock while its socket call is still running. A regression test proves that the next call waits for the cancelled one to finish.
- **A discovered address is saved only after the device at that address confirms the expected serial.** Discovery replies are unauthenticated; a candidate without a serial is rejected, and a flow that would redirect an existing entry checks the claimed serial at the new host. A forged reply can no longer move an entry permanently. This is a mix-up guard, not authentication.
- **A window contact with no status bit in its telegram reports `unknown` instead of a guessed `closed`.**
- **Impossible times and temperatures in a weekly programme are discarded** instead of appearing as setpoints or as the current target temperature; a damaged programme is refused on write.
- **Serial numbers were removed from log messages**; identity errors are now `HomeAssistantError` and no longer reported as connection failures.
- **Shutdown closes the worker without blocking the event loop** and tolerates repeated calls, a failing disconnect and a refresh that races the unload.
- **A device renamed on the Cube gets the new name in Home Assistant** at the next poll; a name the user chose in Home Assistant is never overwritten.

## [1.8.1] - 2026-11-22

### Fixed
- **A weekly programme that the Cube has not taken is resent once.** After a write the Cube often still shows the old
  programme until the thermostat confirms it. That check now repeats the write once (never above the 90 % radio limit);
  its own follow-up check only warns. A new write by the user re-enables the single retry. No endless retry loop.
- **A defensive release of the Cube's client slot on shutdown.** Every poll and command already closes its own short
  connection, so the extra `disconnect` is normally a no-op. It waits for an in-flight call to finish before releasing
  a socket that may still be held; it cannot free the port earlier than that.
- **A weekly-programme check already in flight stops at shutdown.** Guards prevent a retry write and a new verification
  timer from being armed while the entry is going away.

## [1.8.0] - 2026-11-22

### Added
- Two buttons per wall thermostat, `Show room temperature` and `Show setpoint`, set what its display shows. Each press sends one radio telegram. It is refused, and nothing is sent, when the Cube is at 90 % of its radio time. The current setting cannot be read back from the Cube, so the integration shows no state for it. The telegram is not verified on a real wall thermostat yet (taken from the protocol description and the official software).

## [1.7.1] - 2026-11-22

### Fixed
- A Cube that sends its rooms and devices as an empty `M:` line no longer loses its devices after a restart. The last readable list is saved and used; a repair hint appears when the Cube sends no readable list for three polls in a row and goes away with the next readable one.

## [1.7.0] - 2026-11-21

### Added
- `maxcube_local.set_schedule` takes `by_day`: its own periods for each day, instead of one list of periods for all the
  days in `days`. The old form (`days` and `periods`) works as before.
- Service `maxcube_local.copy_schedule` copies the weekly programme of a radiator thermostat to other radiator
  thermostats of the same Cube, for all days or for the days given. Only the days that differ are written. The radio
  time is checked before the first telegram (about 2.8 % per telegram plus the current duty cycle); the request is
  refused, and nothing is sent, if the Cube would reach 90 %. The response gives the result per thermostat and day.

### Changed
- Entities read an immutable snapshot taken after each poll instead of the library's mutable objects.

## [1.6.1] - 2026-11-21

### Changed
- The minimum Home Assistant version is now 2025.3 because the integration imports `AddConfigEntryEntitiesCallback`, which Home Assistant added in 2025.3.
- Tests: a fake Cube (synthetic frames) for tests without hardware.

### Fixed
- A short (5-byte) or window contact (6-byte) entry as the last entry of the Cube's L message no longer drops the link status of all devices.
- The values of a device with a short or window entry are no longer read from the bytes of the next entry.

## [1.6.0] - 2026-11-21

### Added
- Lovelace card for the weekly heating programme, contributed by @helpmeifyoucan (#25). It is served by the
  integration itself (no resource to add), lists radiator thermostats only, sends only changed days and asks for
  confirmation before many radio telegrams.

### Changed
- The manifest now lists `frontend` and `http` as dependencies (both are part of every normal Home Assistant
  setup); they are needed to serve and load the card.

## [1.5.1] - 2026-11-21

### Changed
- **The four status sensors of a device are named after what they report, not after the fault.** "Device error" is now
  "Device status", "No data received" is "Data reception", "Not initialized" is "Setup" and "Radio fault" is
  "Radio link" (German: Gerätezustand, Datenempfang, Einrichtung, Funkverbindung). They still show "OK" or "Problem";
  what they report and their entity ids do not change.

### Fixed
- **A low-battery report is held for 15 minutes after the Cube stops sending it.** The Cube reports that flag unevenly (on a
  real thermostat it came and went every few minutes for hours), so the sensor and the repair hint flapped, and an
  automation waiting for "on for 30 minutes" could not fire.
- The repair hint for a device error says that after a battery change it can take a few hours until the Cube has set the
  thermostat up again.

## [1.5.0] - 2026-11-21

### Added
- **Repair hints for the Cube itself:** one when the Cube has not answered for more than six hours, and one
  when its radio duty cycle stays at 90 % or more for ten minutes (it goes away below 80 %; at 100 % the Cube stops
  sending commands for about an hour). Both clear by themselves.
- **Translated names for the thermostat presets** (none, boost, comfort, eco, away, on) in English and German.
- `SECURITY.md` with the supported versions, the threat model (the MAX! protocol has no authentication; use the
  Cube in a trusted network only) and private reporting through GitHub Security Advisories.

### Changed
- **A command that cannot reach the Cube fails with a clear, translated message** instead of a raw network error
  (target temperature, mode and preset, and programme writes); a command the Cube does not accept (a false answer,
  for example when its radio time is used up) is reported the same way. This makes the Silver rule
  `action-exceptions` of the quality scale true.
- **Discovery** ignores a datagram whose serial number is not ten capital letters or digits, and the `until` time of
  the `set_schedule` service must be plain `H:MM`/`HH:MM` with ASCII digits.
- A programme write keeps one pending check per device instead of registering a new callback for every write; the
  two locks of the coordinator are documented (they cannot be merged).
- The diagnostics redact the entry title and unique id as well (they are not part of the report today); a test searches
  the whole report for addresses, serial numbers and names.
- CI: read-only token permissions, third-party actions (and the release workflow of `Ebenhoeh80/.github`) pinned to
  commit SHAs, ruff rules RET, PL, C901 and ANN.

## [1.4.2] - 2026-11-20

### Changed
- **The entry title shows the serial number in parentheses:** "MAX! Cube (JEQ0355273)". An entry with a
  generated title is renamed at the next start; a title you chose stays.
- Clearer names: the reboot button is "Restart" (it appears under the Cube device), the error sensor of a device is
  "Device error" ("Gerätefehler").

## [1.4.1] - 2026-11-20

### Fixed
- The reboot button had no name (it showed up as just "MAX! Cube"); it is called "Restart Cube" / "Cube neu starten" now.
  The button stays disabled by default.

## [1.4.0] - 2026-11-20

### Added
- **Home Assistant Integration Quality Scale: Gold** (`quality_scale.yaml`), `icons.json`,
  `PARALLEL_UPDATES`, descriptions for all dialog fields and README sections (configuration, supported
  devices and functions, data updates, use cases, troubleshooting, removal, known limitations).
- **Reconfigure flow:** change the Cube's address without removing the entry (only the same Cube, by its
  serial number, is accepted; identity and title stay).
- **Repair hints** for a low battery and a device error, and a **diagnostics download** with addresses,
  serial numbers and names removed; the diagnostics also show how many polls ran, failed and how long the last took.
- **Devices paired later get their entities at the next poll;** devices that left the Cube are removed after
  the next reload or restart and may be deleted in the UI.
- **Link-status diagnostics and a reboot button**, contributed by @helpmeifyoucan (pull request #3, rebased
  onto 1.3.3 in #17): the Cube's per-device flags (Error, Link error, Not initialized, No data received) as
  diagnostic sensors with the raw flag bytes as an attribute, and a button that reboots the Cube. "Radio fault",
  "Not initialized" and the reboot button are disabled by default.
- CI: ruff, mypy with the real Home Assistant types, xenon, CodeQL, 95 % coverage gate;
  [`docs/ENGINEERING.md`](docs/ENGINEERING.md) documents architecture, failure modes, measurements and decisions.

### Fixed
- **Poll and commands no longer overlap on the Cube's single connection** (a test showed two threads in a
  Cube call at once; calls are serialised now).
- A poll refused or reset by the Cube (for example while the MAX! app holds the connection) is repeated once.
- Read-backs after commands are merged for 2 s instead of 10 s.
- The reboot button no longer raises on a network error.

## [1.3.3] - 2026-11-20

### Changed
- **A Cube is identified by its serial number, not by its address.** The entry's unique id and its title are now
  the serial number (`MAX! Cube JEQ0355273`); before, both contained the address, which changed with every new
  address and showed a wrong title. Existing entries are migrated at the next start (a title you chose stays);
  devices, entities, areas and history are not touched. See [`docs/IDENTITY.md`](docs/IDENTITY.md).
- **Discovery:** Home Assistant now finds a Cube by its DHCP request (hardware address prefix of eQ-3): the first
  Cube appears under *Discovered*, and a known Cube that got a new address is followed. After startup the integration
  also scans once for Cubes it does not know or whose address changed.
- **One Cube, one entry:** a second entry for a Cube that already has one stops with a clear message instead of
  creating every device twice.
- **The Cube that answers must be the Cube of the entry:** a different Cube at the saved address is no longer taken
  over; the right one is looked up by its serial number.
- The entry reloads (once) when the options or the address change, scheduled by its update listener.

### Fixed
- The connection test of the setup dialog did not close its connection, so the Cube stayed occupied until it was
  cleaned up; an unexpected error in the dialog is shown as "unknown".
- A failed setup because the Cube is off logs one line instead of a full error trace.
- The broadcast search no longer raises when the machine has no usable network interface.

## [1.3.2] - 2026-11-20

### Fixed
- **The Cube is found again after it was off or restarted.** A Cube that has no DHCP lease yet
  answers the discovery broadcast from its factory address `192.168.0.222`. Version 1.3.1 saved that
  address, although it cannot be reached from the home network, and then stayed on it: the entry
  was stuck in *retry* and every device was unavailable. Now an address is only saved if the Cube's
  data port answers there, and the lookup by serial number also runs when Home Assistant starts or
  the entry is set up again, not only while it is running.

## [1.3.1] - 2026-11-20

### Changed
- **Writing the weekly programme: the read-back is checked again later.** On a real Cube the new
  programme shows up in the Cube's data only after the thermostat has taken it, about two minutes
  after the write. The service now reports `sent_not_confirmed` right away in that case (instead of
  suggesting a failure), checks again five minutes later and logs a warning if the Cube still shows
  the old programme. The README explains the delay.

## [1.3.0] - 2026-11-20

### Added
- **Setting the weekly heating programme.** The service `maxcube_local.set_schedule` writes a daily
  programme to chosen days of one or more radiator thermostats (periods with the temperature that applies
  until a time; at most seven per day, 5-minute steps, half degrees, the last period ends at 24:00).
  `dry_run: true` only checks the request. After writing, the programme is read back from the Cube and
  checked; a day the Cube did not take raises an error. It refuses to write when the Cube has used 90 %
  of its radio time.
- Tests for the validation, for the radio message (identical to the library's for a full day) and for
  the read-back.

### Changed
- The radio message is built in the integration instead of with the library's `set_programme`, which
  skips a write when its own (half-degree-cutting) copy looks equal and pads a short day with one byte
  instead of two.

## [1.2.0] - 2026-11-20

### Added
- **Weekly heating programme (read-only).** The programme of each radiator thermostat is shown in the
  climate entity's `schedule` attribute: for every day the setpoints with the time until which each
  temperature applies. Wall thermostats show the programme of a radiator thermostat in the same room.
  `scheduled_temperature` is the temperature the programme sets right now. The programme is decoded
  with exact half degrees (the `maxcube-api` library cuts 21.5 to 21), and the large attribute is kept
  out of the history database.
- **Service `maxcube_local.get_schedule`** returns the weekly programme of the chosen thermostats as a
  response.
- Tests for the decoding (day order, half degrees, end of day, the C message).

## [1.1.0] - 2026-11-20

### Added
- **Cube diagnostics.** Two diagnostic sensors on the Cube device: the radio **duty cycle** (%) and
  the number of **free memory slots**. At a duty cycle of 100 % the Cube sends no radio commands for
  about an hour, so this is worth watching when many settings are changed.
- **The Cube is found again after an IP change.** The Cube's serial number is saved; when a poll
  fails, the integration looks for a Cube with that serial number on the network and saves its new
  address (at most every five minutes).
- **Service `maxcube_local.reconnect`** closes the connection to the Cube and reads everything again
  (optionally for one Cube).
- Tests for the status values and for finding the Cube by its serial number (new CI workflow).

### Changed
- Every poll now opens its own short connection to the Cube and closes it again. This keeps the
  duty cycle and the free memory slots current (the Cube reports them when a connection starts) and
  leaves the Cube free for other clients between polls.

## [1.0.0] - 2026-11-20

The integration is stable: entities, configuration data and services stay as they are. From
now on version numbers follow [Semantic Versioning](https://semver.org/): a breaking change
raises the major version, a new feature the minor version, a fix the patch version.

### Changed
- README (en/de): the installation section now starts with finding **eQ-3 MAX! Cube** through
  HACS search (the integration is in the HACS catalog); the custom repository steps stay as a
  fallback.

### Fixed
- **No more deprecation warnings on Home Assistant 2026.11.** The thermostats now
  provide `native_current_temperature`, `native_target_temperature` and
  `_attr_native_temperature_unit` (the old names stop working in Home Assistant
  2027.11), and the devices are linked to the Cube hub with `via_device_id`
  (`via_device` stops working in 2027.8). Older Home Assistant versions keep
  using the previous names, so the minimum version is unchanged.

## [0.4.0] - 2026-11-17

### Added
- **Automatic Cube discovery** in the config flow: the integration sends a UDP
  broadcast on the local network and pre-fills the Cube's IP address, so you no
  longer have to look it up. Manual entry still works as a fallback.
- The **device serial number** (e.g. `JEQ…`/`KEQ…`) is now shown on each MAX!
  device and on the Cube hub, via Home Assistant's device registry.
- Release assets are now **counted downloads**: each release ships a
  `maxcube_local.zip` asset and HACS installs from it (`zip_release`).

### Changed
- Documentation/licensing: added a `NOTICE` file crediting the Apache-2.0
  licensed Home Assistant Core `maxcube` integration (from which the climate
  platform is derived) and including the Apache License 2.0 text. The READMEs now
  state that `MassiPi/maxcube` was used only as a reference, with no code taken
  from it. This addresses the HACS default-store review (PR hacs/default#14273).

## [0.3.1] - 2026-11-16

### Added
- **Connectivity** binary sensor on the Cube device (on = the Cube is reachable /
  the last poll succeeded), giving the hub its own status entity. It stays
  available even when the Cube is offline, so it can report the disconnected state.

## [0.3.0] - 2026-11-16

### Changed
- **Renamed the integration domain `maxcube` → `maxcube_local`** so it no longer
  collides with the Home Assistant core integration — a requirement for HACS
  default-store inclusion. **After updating, delete the old integration entry and
  add it again.** Entity IDs (e.g. `climate.<name>`) stay the same, so recorder
  history continues.

### Added
- Measured temperature is now shown to **0.1 °C** (climate current temperature and
  the temperature sensor). Setpoints stay in 0.5 °C steps, as the Cube requires.

## [0.2.0] - 2026-11-16

### Added
- **Temperature sensor** per thermostat (the measured room temperature),
  usable for graphs and automations instead of only the climate attribute.
- The **Cube appears as a hub device** with its firmware version; all
  thermostats and contacts group under it and are assigned to their MAX! room.
- **Comfort/eco setpoints and valve position** exposed as climate attributes.
- Donation/support section in the READMEs and a `.github/FUNDING.yml`.

## [0.1.1] - 2026-11-16

### Fixed
- Entity setup crashed with
  `is_thermostat() takes 1 positional argument but 2 were given` because the
  device-type checks were called on the Cube instead of the device, so **no
  entities were created**. They are now called on the device.

## [0.1.0] - 2026-11-16

### Added
- Initial MVP: config flow, `climate` entities for radiator and wall thermostats,
  window/battery `binary_sensor` entities, a valve-position `sensor`, and an
  options flow for the poll interval. Local TCP via `maxcube-api`, no cloud.
