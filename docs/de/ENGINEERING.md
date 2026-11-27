> Deutsche Übersetzung von docs/ENGINEERING.md. Maschinell erstellt, Muttersprachlerprüfung offen.

# Technische Notizen: Architektur, Fehlerbilder, Messungen, Qualitätsprüfungen

Diese Seite beschreibt, wie die Integration funktioniert, wohin ihre Zeit fließt, was schiefgehen
kann und wie sie sich erholt, was automatisch geprüft wird und welche Optionen verworfen wurden
und warum. Zahlen sind gemessen, mit Datum und Methode angegeben. Letzte Aktualisierung: 2026-11-25 (nach der Live-Prüfung v1.8.5 und den Schutzmaßnahmen gegen veraltete Cache-Werte).

## 1. Architektur und Datenfluss

```
 Home Assistant                       Integration "maxcube_local"                      außen
 ───────────────                      ───────────────────────────                      ───────
 climate / Dienste ──► climate.py ──► coordinator.async_cube_call()  (ein Aufruf nach dem anderen)
 Poll alle 60 s ──────► coordinator._async_poll()  ──────────────────► Executor-Thread
                                                                           │ Bibliothek maxcube-api
                                                                           ▼
                                                               TCP 62910  ──────────►  MAX! Cube
 config flow ─────────► discovery.discover_cubes()  UDP 23272 Broadcast ──────────►  (findet den Cube)
 Setup / fehlgeschlagener Poll ─► coordinator._async_find_new_host()  (Seriennummer, nur erreichbare Adresse)
```

- **Eine Verbindung pro Poll.** Der Cube akzeptiert nur einen Client. Jeder Poll öffnet eine kurze
  Verbindung und schließt sie wieder, damit die MAX!-App dazwischen den Cube nutzen kann und jeder
  Poll mit einer frischen `H`-Nachricht beginnt (Funkauslastung, freie Speicherplätze). Die
  Bibliothek ist synchron: jeder Aufruf läuft im Executor, niemals auf der Event-Loop.
- **Discovery bindet lokal UDP 23272.** Der Cube adressiert seine Antwort an den Port des Absenders,
  nicht an einen beliebigen Quellport (hardwareverifiziert in `app-maxcube`, `HARDWARE-VERIFY.md` §3).
  Gehört dieser Port bereits einem anderen Prozess, liefert die Discovery kein Ergebnis, statt von
  einem Port zu senden, auf dem die Antwort nie ankommen kann.
- **Wochenprogramm:** gelesen aus den `C`-Nachrichten des Cube; geschrieben mit einer in `schedule.py`
  gebauten Nachricht (der `set_programme` der Bibliothek verliert halbe Grade); geprüft durch
  erneutes Lesen nach etwa fünf Minuten. Seit 1.8.1 wird ein Tag, der noch abweicht, einmal erneut
  gesendet; die eigene Folgeprüfung warnt nur. Schreibvorgänge werden bei 90 % Funkauslastung
  verweigert, und auch der erneute Versand hält sich an dieses Limit (siehe §3 und §7).
- **Entitäten:** Climate, Sensoren, Binärsensoren, Button pro Cube; später hinzugekommene Geräte
  erhalten ihre Entitäten beim nächsten Poll (`async_add_devices_as_they_appear`).

## 2. Nebenläufigkeit und Lebenszyklus

- **Polls, Befehle, Snapshots und Trennung teilen sich einen eigenen Worker-Thread**
  (`coordinator._async_io_call`, ein `ThreadPoolExecutor(max_workers=1)`). Ein `asyncio.Lock` würde
  freigegeben, wenn eine Home-Assistant-Aufgabe abgebrochen wird, während ihr Executor-Thread noch
  mit dem Cube spricht; der nächste Aufruf könnte dann auf dem Single-Client-Port überlappen. Ein
  zweites, unabhängiges Lock hält eine Programm-Schreibung und ihre Rücklesung zusammen. Vor 1.4.0
  liefen ein Poll und ein Befehl in verschiedenen Executor-Threads und konnten sich überlappen; ein
  Abbruch-Test beweist jetzt, dass selbst ein abgebrochener Aufruf den nächsten blockiert, bis er
  beendet ist. Kurze Verbindungsprüfungen bei Discovery, config flow und UDP-Reboot nutzen den
  gemeinsamen Executor von Home Assistant; sie sind kurz, aber nicht Teil dieser Serialisierung
  pro Eintrag.
- **Die Worker-Warteschlange ist bewusst unbegrenzt.** Sie gehört zu einem Config Entry, jeder
  Aufruf wird von seinem Aufrufer abgewartet und Aktualisierungen werden vom Coordinator
  entprellt. Ein Semaphor um `submit` würde den Abbruchfehler wieder einführen: Es würde
  freigegeben, während der Worker noch den Port des Cube hält.
- **Snapshots werden im selben Worker kopiert**, sodass die Kopie nicht mit Cube-I/O überlappen
  kann. Sie ist nicht atomar mit dem Poll: Identitätsprüfungen und Metadaten-Schreibvorgänge
  laufen auf der Event-Loop, und eine andere Aufgabe kann dazwischen einen Befehl einreihen.
  Früher lief die Kopie ohne Lock in einem anderen Executor-Thread, und ein Befehl konnte die
  Bibliotheksobjekte dabei verändern.
- **Rücklesen nach einem Befehl** wird 2 s lang zusammengefasst (Home Assistants Standard sind
  10 s, wodurch die zweite von zwei schnellen Änderungen so lange unsichtbar blieb). Es aktualisiert
  nur den Zustand von Home Assistant aus dem nächsten Poll; es ist **keine** Hardware-Bestätigung,
  und `climate.py` prüft es nicht. Gemessen am echten Cube am 2026-11-25 (C#-Gateway, separate
  Verbindung, `0x40`-Sollwert): eine sofort gestartete Lesung zeigte noch den alten Sollwert; eine
  etwa 2 s später gestartete Lesung zeigte den neuen Wert bei etwa 4 s; eine dritte Lesung bei
  etwa 11 s zeigte ihn weiterhin. Die Akzeptanz dauert auf dieser Hardware also einige Sekunden,
  sodass eine frühe Rücklesung berechtigt veraltet sein kann (siehe §4).
- **Die erste Aktualisierung liest den Cube zweimal** (`coordinator.py:157-176`, `:202-226`,
  `:249-265`, `:399-414`; `__init__.py:217`). Der Konstruktor `LinkStatusMaxCube` führt einen
  blockierenden Erstlesevorgang durch; `async_config_entry_first_refresh()` (Home Assistant Core
  2025.3, `helpers/update_coordinator.py:283-308`) ruft dann `_async_setup()` und unmittelbar
  danach `_async_refresh()` → `_async_update_data()` → `_async_poll()` → `cube.update()`. Das sind
  einmalige Kosten von etwa 2 × 700 ms beim Setup, keine wiederholte Rücklesung. Die Daten des
  Konstruktors weiterzuverwenden und den Poll zu überspringen wurde verworfen: Es würde die
  Identitätsprüfung und die Funkauslastungs-Behandlung für eine einmalige Ersparnis verändern. Ein
  Regressionstest zählt beide Lesevorgänge (`tests_ha/test_integration.py`).
- Der Eintrag hält die Cube-Adresse in seinen Daten; er wird neu geladen, wenn sich Optionen ändern.

## 3. Fehlerbilder und Wiederherstellung

| Fehler | Wirkung | Wiederherstellung / Abhilfe |
|---|---|---|
| Cube aus oder neu gestartet | alle Geräte nicht verfügbar | Polls schlagen fehl; der Cube wird über die Seriennummer gesucht (alle 5 min) |
| **Cube antwortet von seiner Werksadresse `192.168.0.222`** (noch keine DHCP-Lease) | 1.3.1 speicherte diese unerreichbare Adresse; der Eintrag blieb dauerhaft in *retry* (beobachtet 2026-11-20) | behoben in 1.3.2: eine Adresse wird nur gespeichert, wenn dort der Datenport antwortet; die Suche läuft auch beim Setup |
| Cube hat eine neue DHCP-Adresse | Polls schlagen fehl | über Seriennummer gefunden, gespeichert, Eintrag wird neu geladen |
| MAX!-App hält die einzige Verbindung | ein Poll wird verweigert | eine Wiederholung nach 1 s (nur bei verweigertem/zurückgesetztem Zustand); Timeouts werden nicht wiederholt |
| Poll und Befehl überlappen | einer wird verweigert | Aufrufe werden serialisiert (siehe oben) |
| Funkauslastung bei 90 % oder mehr | Programm-Schreibvorgänge würden verworfen | der Dienst verweigert das Schreiben; nach zehn Minuten erscheint ein Reparaturhinweis, der unter 80 % verschwindet |
| Cube länger als sechs Stunden unerreichbar | alle Geräte nicht verfügbar | Reparaturhinweis (Timer ab dem ersten fehlgeschlagenen Poll), durch den nächsten erfolgreichen Poll aufgehoben |
| Befehl erreicht den Cube nicht oder wird verweigert | die Nutzeraktion schlägt fehl | übersetzter `HomeAssistantError` (`cube_unreachable`, `command_rejected`) |
| Gerät aus dem Cube entfernt | veraltetes Gerät in Home Assistant | wird nach dem nächsten Neuladen oder Neustart aus der Registry entfernt (die Bibliothek fügt nur Geräte hinzu) |
| Leere Geräteliste nach fehlgeschlagenem Lesen | würde die Registry leeren | eine leere Liste wird niemals vertraut |
| **Low-Battery-Flag kommt und geht** (beobachtet 2026-11-20: Lücken von 1 bis 5 Minuten über Stunden bei einem Thermostat) | Sensor und Reparaturhinweis flackern; eine Automatisierung mit „on for 30 minutes" kann nicht auslösen | die Meldung wird 15 Minuten nach dem letzten Senden durch den Cube gehalten (`BatteryHold`) |
| **Nach einem Batteriewechsel behält der Cube das Gerät stundenlang im Fehler** (beobachtet 2026-11-21: `Error` von 09:41 bis 11:02, „not initialized" flackernd bis 13:12) | Status-Sensoren und Reparaturhinweis bleiben an, obwohl das Thermostat funktioniert | nicht möglich: der Cube setzt und löscht die Flags selbst, während er das Thermostat wieder einrichtet; der Hinweistext sagt das |

## 4. Wohin die Zeit fließt (gemessen)

Methode: die eigene Cube-Klasse der Integration gegen den echten Cube vom Entwicklungsrechner am
2026-11-20 (Integration getrennt, also kein Wettbewerb um die einzelne Verbindung), `cProfile` für einen Poll.

| Aktion | Eine Verbindung pro Poll (wie gebaut) | Dauerhafte Verbindung |
|---|---|---|
| Poll | Median 700 ms (601 bis 1699 ms) | 99 ms |
| Zieltemperatur setzen | Median 900 ms (erster Aufruf 1,9 s) | 198 ms |
| CPU-Zeit eines Polls | praktisch 0 (die Zeit sind `connect`/`recv`-Wartezeiten im Executor) | – |

Eine dauerhafte Verbindung wäre etwa 7-mal schneller, sperrt aber die MAX!-App aus und verzögert
die Funkauslastungs-Auslesung, deshalb wurde sie nicht gebaut. Eine Nutzeraktion wird einmal
rückgelesen: Befehl plus Rücklesung sind etwa 1,6 s, deutlich unter den 2 bis 10 s, die das Ziel
waren. Nebeneffekt des Benchmarks: sechs Sollwert-Schreibvorgänge ohne Änderung erhöhten die
Funkauslastung des Cube von 4 % auf 21 % (sie fällt von selbst ab). Identische Solltemperaturen
und Modi werden daher übersprungen, bevor ein Telegramm gesendet wird.

Am 2026-11-25 erneut am echten Cube geprüft, mit dem `CubeGateway` der App selbst (Raum 2, `0x40`
`setpoint 17.0 → 17.5 °C`, danach auf 17.0 °C zurückgesetzt): `S: dutyCycle=3`, sofortige Lesung
`Permanently / 17.0`, etwa 2 s später gestartete Lesung `Permanently / 17.5` bei +4,1 s, dritte
Lesung weiterhin `17.5` bei +10,8 s; Rücksetz-Lesung `17.0` nach 6 s. **BEOBACHTUNG:** der vom
Cube gemeldete Zustand hinkt einem Sollwert-Befehl um einige Sekunden hinterher. **INFERENZ:** die
2-s-Entprellung ist eine pragmatische Zustandsaktualisierung, keine Bestätigung; ein veralteter
Wert bei der ersten Lesung ist erwartbar und der spätere Poll korrigiert ihn. Es wurde keine
Änderung vorgenommen (P3 als dokumentiertes Verhalten geschlossen).

## 5. Qualitätsprüfungen (alle laufen in CI)

| Prüfer | Prüfung | Ergebnis |
|---|---|---|
| Ruff (E, W, F, I, B, C4, UP, SIM, RET, PL, C901, ANN) | keine Befunde | bestanden (Tests sind von PLR2004, PLC0415 und ANN ausgenommen) |
| MyPy mit den echten Home-Assistant-Typen | keine Fehler | bestanden |
| pytest, Unit-Tests (Python 3.12, 3.13) | alle bestanden | 175 bestanden, 2 xfailed (lokale Nachprüfung 2026-11-25) |
| pytest in echtem Home-Assistant-Core (2025.3 und 2026.2) | alle bestanden | 128 bestanden jeweils für 1.8.3; 147 lokal bestanden für 1.8.6 (HA 2026.10.4, 2026-11-25) |
| Coverage (beide Suiten zusammen) | mindestens 95 % | 96,43 % |
| hassfest, HACS-Validierung | gültig | bestanden |
| xenon | absolut B, Module A, Durchschnitt A | bestanden |
| CodeQL (security-and-quality) | keine neuen Meldungen | bestanden |
| Home Assistant Quality Scale | `quality_scale.yaml` | Gold; Platinum offen (`async-dependency`, `strict-typing`) |

Lokal am 2026-11-25 für 1.8.6 nachgeprüft: Ruff sauber, Xenon sauber (`--max-absolute B`), MyPy
mit den echten Home-Assistant-Typen sauber, 175 Unit-Tests bestanden (2 xfailed), 147
Home-Assistant-Tests bestanden, `node --check` sauber und `git diff --check` sauber. CI führt
zusätzlich Hassfest und HACS `validate` aus, beide grün für 1.8.5 (1.8.6 ausstehend).

Lokal nicht verfügbar: SonarQube, Semgrep, py-spy und Scalene. Ein Live-Cube-Test war am
2026-11-25 möglich: die Integration ist in HAOS geladen (Log-Level nach der Untersuchung jetzt
`WARNING`), und rohe `s:`-Telegramme wurden im Log beobachtet. Es bestätigte, dass RF-Flag `04`
einen Raum adressiert und dass fünf Geräte falsche interne Raum-IDs in ihrer `C:`-Konfiguration
hatten, wodurch Sollwert-Befehle zwischen Räumen gekoppelt wurden. Das Korrigieren dieser IDs mit
`0x22` ist eine Cube-Konfigurationsänderung, kein Teil des Integrationscodes.

## 6. Entscheidungen und verworfene Optionen

- **Dauerhafte Verbindung:** verworfen (siehe 4).
- **Die Bibliothek als asynchronen Client neu schreiben:** strategische Option (Platinum
  `async-dependency`, Entfernen von Geräten zur Laufzeit); braucht Tests am echten Cube.
- **Link-Status-Diagnose eines Mitwirkenden (pull request #3):** in 1.4.0 veröffentlicht, nachdem
  die rebasierte Version in #17 und die Herkunfts-/Lizenzfrage geklärt waren; die aktuelle
  Diagnoseseite dokumentiert sie.
- **Moduswechsel in 1.8.3:** eine Zieltemperatur, `off`, `heat` und Temperatur-Presets senden
  alle einen kombinierten Befehl `MANUAL` + Sollwert. `off` ist `MANUAL` bei 4,5 °C; `heat`
  stellt den letzten echten Sollwert wieder her (Programmsollwert, sonst Komfort-Sollwert als
  Fallback). `set_target_temperature` allein lässt `AUTO` bestehen und das Programm überschreibt
  den Wert beim nächsten Poll.
- **Zwei Protokolle, ein lokaler Transport:** `B:/G:/J:/P:/O:/V:/W:` und `g:` gehören zum
  HTTP-Fernzugriffs-Proxy der MAX! Cloud (seit 2023-07-01 abgeschaltet) und werden hier
  bewusst nicht implementiert. `e:/d:` sind echte TCP-Befehle der Desktop-App, aber diese
  Integration nutzt sie nicht als Cloud-Transport. Hier spricht alles lokal über TCP/UDP mit dem Cube.

## 7. Offene Punkte

- Platinum-Regeln `async-dependency` und `strict-typing`.
- Die einmalige Wiederholung für ein Wochenprogramm projiziert die Funkkosten seiner Tage, nutzt
  aber weiterhin die Funkauslastung des letzten Polls; ein anderer Cube-Aufruf kann sie vor dem
  erneuten Versand erhöhen. Geringes Restrisiko.
- `split_l_entries` stoppt bei einem fehlerhaften Längenbyte ohne Resynchronisierung; der Rest
  dieser `L`-Nachricht wird verworfen. Dokumentiert und durch einen Test abgedeckt, nicht geändert (K2).
- Ein Tag mit 8..13 Schaltpunkten wird abgelehnt: ein Telegramm trägt sieben, und obwohl die
  ursprüngliche App ein zweites mit sechs und einem Flag in Byte 10 Bit 4 sendet, ist die
  Annahme dieses zweiten Telegramms durch den Cube nicht verifiziert. Die Änderung des
  Sieben-Punkte-Limits ist eine Aufgabe für die Hardwareverifizierung.
- Ein kurzer `L`-Eintrag lässt den Gerätemodus unbekannt; Home Assistant verlangt einen
  `hvac_mode`, daher meldet die Entität derzeit `AUTO`. Den letzten bekannten Modus zu halten
  würde die Automatisierungssemantik ändern und braucht eine Produktentscheidung.
- Teilfehler beim Schreiben mehrerer Sollwerte aus der Wochenplan-Karte markieren alle
  betroffenen Tage als geändert, sodass bereits bestätigte Sollwerte erneut geschrieben werden
  können. Eine Fehlerverfolgung pro Sollwert ist eine UI-Änderung, keine Funk-Sicherheitskorrektur.
- Pairing (`n:`/`N:`/`x:`) ist eine Produktentscheidung für 1.9.0 mit Admin-Schutz und Poll-Pause,
  kein Quickwin. Der Cloud-Fernzugriffs-Proxy und `e:`/`d:` als Cloud-Transport bleiben ausgeschlossen (siehe §6).

## 8. Geschlossen: P3-Rücklesung und die doppelte Lesung beim Setup (2026-11-25)

- **Korrektur der Zeilennummern:** `climate.py:407` ist `await self._set_mode(MAX_DEVICE_MODE_BOOST)`.
  Die Aktualisierungsaufrufe sind `climate.py:450` (Sollwert) und `:459` (Modus), beide
  `await self.coordinator.async_request_refresh()`.
- **Zweck der Rücklesung:** den Zustand von Home Assistant aktualisieren, nicht das Funktelegramm
  bestätigen. Kein Codepfad vergleicht den rückgelesenen Wert mit dem angeforderten oder bricht
  bei einer Abweichung ab. Die Hardwaremessung in §4 zeigt warum: am echten Cube erscheint der
  neue Sollwert erst nach einigen Sekunden in der Lesung, sodass eine sofortige Lesung den alten
  Wert melden kann, ohne dass das Schreiben fehlgeschlagen ist. Es als Bestätigung zu behandeln
  wäre falsch; es wurde keine Änderung vorgenommen.
- **Doppelte Setup-Lesung:** durch Code und durch Home Assistant Core 2025.3 bestätigt (§2). Es
  ist eine vollständige Lesung im Konstruktor der Bibliothek plus eine im ersten Poll. Die Kosten
  sind einmalig; die Korrektheit ist nicht betroffen. Das Überspringen der zweiten Lesung würde
  Änderungen an `_connect`, der Identitätsprüfung und der Aktualität der Funkauslastung für eine
  einmalige Ersparnis erfordern — verworfen als riskantere Änderung als die Kosten, die sie einspart.
- **Verifizierung:** der Regressionstest `tests_ha/test_integration.py` zählt eine Konstruktion
  und zwei Lesungen nach dem Setup sowie eine weitere nach einer Aktualisierung. Der Hinweis auf
  lokale HA-Tests galt nur für die reine Unit-Test-Umgebung; mit lokal installiertem HA
  (2026.10.4) laufen alle `tests_ha`-Tests. CI führt `tests_ha` gegen HA 2025.3 und 2026.2 aus.

## 9. Geschlossen: Schutz gegen unveränderte Werte mit veraltetem Cache (2026-11-25)

- **Live-Beobachtung:** nach einem `climate.set_temperature` wurde der neue Sollwert in HA erst
  beim nächsten 60-s-Poll sichtbar. Eine zweite, abweichende Anfrage innerhalb dieses Fensters
  konnte vom Schutz gegen unveränderte Werte verworfen werden: Er verglich die Anfrage mit dem
  Snapshot des letzten Polls, der noch den alten Wert enthielt. Dasselbe galt für `_set_mode`,
  nachdem ein Sollwert `MANUAL` im kombinierten Telegramm gesendet hatte.
- **Korrektur:** das Thermostat merkt sich den letzten gesendeten Temperatur- und Moduswert, bis
  ein Coordinator-Update den Snapshot ersetzt. Sowohl der Temperatur- als auch der Modus-Schutz
  vergleichen zuerst mit diesem ausstehenden Wert; der Snapshot wird nur verwendet, wenn nichts
  aussteht. Der ausstehende Temperaturwert wird auch für den gemeldeten Sollwert genutzt, sodass
  die UI sofort einen Sollwert zeigt, statt auf den Poll zu warten.
- **Funkkosten:** im Normalbetrieb unverändert. Das Wiederholen einer identischen Anfrage wird
  weiterhin unterdrückt, und es wird kein zusätzliches Telegramm gesendet, solange der Aufrufer
  nicht tatsächlich einen anderen Wert anfordert.
- **Verifizierung:** zwei Regressionstests in `tests_ha/test_climate_temperature.py` mocken
  `async_request_refresh`, um den fehlenden Poll zu simulieren; beide schlugen vor der Korrektur
  fehl und bestehen danach.

## 10. Beobachtbarkeit und Qualitäts-Gates (27.11.2026)

- **Telegramm-Korrelation (P1-1):** `telegram_log.py` zeichnet gesendete Telegramme auf und
  korreliert sie mit `L:`-Antworten und der `S:`-Antwort des Cube. Das dokumentierte Format ist
  `S:<Funkauslastung hex>,<Ergebnis>,<freie Plätze hex>`; `Ergebnis = 1` bedeutet, dass der Cube
  einen Befehl verworfen hat; es wird eine Warnung geloggt. Funkauslastung, freie Plätze sowie
  lokal ausstehende/verworfene Zähler erscheinen in den Diagnose-Sensoren und im redaktierten
  Diagnose-Download. Das Protokoll kennt keine Warteschlangenlänge; der irreführende Sensor
  „Wartende Funkaufträge" wurde in 1.9.1 entfernt. Das ist reine Beobachtung: die Ursache des live
  beobachteten Sollwert-Übersprechens ist weiterhin unbekannt, daher **mindestens 60 s Abstand
  zwischen Raumänderungen**.
- **Aktionen (P1-3):** integrationsweite Aktionen werden aus `services.py` über
  `async_setup_services` registriert, mit `CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)`.
  `get_schedule`/`set_schedule` nutzen ab HA 2025.10 den offiziellen Entity-Service-Helper und auf
  der deklarierten Mindestversion 2025.3 den Plattformweg, sodass keine Aktion doppelt registriert
  wird. Der Neustart ist eine Admin-Aktion und verwendet die vom Cube gelesene Seriennummer, nie
  ein Eingabefeld.
- **Gates (P1-4):** der kombinierte Lauf verlangt weiterhin 95 % insgesamt;
  `scripts/check_coverage.py` wendet die Grenze pro Modul an (zwei Socket-/Hardware-Module sind im
  Skript begründet ausgenommen). `mypy --strict --follow-imports=skip` läuft in CI auf die
  reinen Logikmodule. Die Diagnostics werden in `tests_ha/test_diagnostics.py` Schlüssel für
  Schlüssel geprüft, `tests/test_release_consistency.py` prüft Manifest-/Changelog-Version,
  DE/EN-Links und Übersetzungsparität.
- **Test-Framework (P2-1):** `pytest-homeassistant` ersetzt das defekte
  `pytest-homeassistant-custom-component`; der dauerhaft rote HA-2025.3-Job prüft jetzt die reine
  Logik auf der ältesten unterstützten Python-Version.
- **Parser und Reconnect (P2-3/P2-4):** der `M:`-Index wird geprüft, nur eine vollständige
  Nachricht ersetzt die gemerkte Konfiguration, und `L:`-Einträge bleiben innerhalb ihres
  Längenbytes. Ein fehlgeschlagener Verbindungsaufbau wird mit gedeckeltem Backoff gedrosselt und
  in den Diagnostics erfasst.
- **Async-Client (P2-2):** `async_client.py` ist ein typisierter asyncio-Baustein mit
  Zeilenframing, Timeouts, Serialisierung und cancellingsicherem Lock; er hat Strict-MyPy und
  Unit-Tests, ist aber **noch nicht in den Coordinator verdrahtet**. `async-dependency` bleibt
  daher `todo`.
- **Runbook (P2-5):** `RUNBOOK.md` beschreibt den `C:`↔`M:`-Vergleich und die 60-s-Regel. Die
  `0x22`-Korrektur wurde einmal beobachtet; ihre Stabilität ist unverifiziert.
