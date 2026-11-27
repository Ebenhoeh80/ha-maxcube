# Runbook: Raumzuordnung und Funkaufträge (MAX! Cube)

Dies ist eine **Betriebsanleitung**, kein Code-Fix. Sie beschreibt, wie die
Antworten des Cube ausgewertet werden, wenn ein Befehl offenbar das falsche
Zimmer erreicht. Allein durch dieses Dokument wird nichts an der Hardware
geändert.

## Vor mehreren Raumänderungen

Warte **mindestens 60 Sekunden** zwischen Befehlen, die verschiedene Räume
ändern. Sechs Raumwechsel im Abstand von 15 Sekunden führten auf einem System zu
Übersprechen, ein einzelner Wechsel nicht. Die Ursache ist unbekannt; daher ist
dies eine Betriebsregel und kein behaupteter Fix. Die Integration queuesweder
Befehle noch sendet sie erneut — die Warteschlange gehört dem Cube.

## Erst beobachten, dann vermuten

1. Lade unter **Diagnose** des Integrationseintrags ⋮ → „Diagnostics herunterladen“.
2. Prüfe `cube.queue_status`, `cube.pending_telegrams`,
   `cube.rejected_commands` und `telegram_observation`.
   - `queue_status.status = 1`: der Cube hat einen Befehl **verworfen**. Die
     Integration schreibt in diesem Fall eine Warnung.
   - `queued_telegrams`: noch wartende Telegramme im Cube.
   - `pending_telegrams`: von Home Assistant gesendete Telegramme, für die noch
     keine `L:`-Antwort kam. Das ist **kein** Beweis, dass ein Sollwert angekommen ist.
   - `duty_cycle = 100`: das Funkbudget ist aufgebraucht, Befehle werden abgelehnt.
3. Erst danach entscheiden: verworfener Befehl, überlastetes Funk oder falsches Zimmer.

## `C:` mit `M:` nach Neustart oder Programmwechsel vergleichen

Jedes Thermostat speichert seinen Raumcode in der `C:`-Antwort; der Cube listet
die Räume in der `M:`-Antwort. Das sind zwei verschiedene Quellen. Auf einem
System wichen neun von fünf Geräten ab; eine Korrektur per `0x22` war dort
erfolgreich, ihre Stabilität nach Cube-Neustart oder Wochenprogrammwechsel ist
**nicht verifiziert**.

1. Mitschritt eines Rohprotokolls rund um einen Cube-Neustart oder ein
   Wochenprogramm-Schreiben erstellen.
2. Den Raumcode aus der `C:`-Antwort jedes Geräts mit der Raumliste aus `M:`
   vergleichen.
3. Bei Abweichung das Gerät mit der MAX!-Software korrigieren und erneut
   vergleichen. Die Korrektur darf nicht als dauerhaft verifiziert gelten.
4. Gruppenadressierte Befehle **nicht** wegen dieser Abweichung auf ein
   Telegramm je Gerät umstellen: Gruppenadressierung spart bewusst Funkbudget.

Die Integration liest Raum-IDs aus `M:` und schreibt **keine** `C:`-Codes. Ein
Werksreset (`a:`) wird bewusst nicht angeboten.

## Weiterhin offen

- Die Ursache von Sollwert-Abweichungen nach einem Home-Assistant-Neustart.
- Port 62910 verweigert nach Pairing-/Metadatensitzungen Verbindungen (Ping und
  UDP-Discovery funktionieren). Die Integration zeichnet Fehlversuche mit
  Backoff in den Diagnostics auf, behauptet aber keinen Fix.
- Die genaue Duty-Cycle-Grenze und die Stabilität der `0x22`-Korrektur.
- Die Bedeutung des zweiten der 13 Wochenprogramm-Slots („7 + 6").

Nichts davon gilt als gelöst. Bekannte Grenzen stehen in `ENGINEERING.md`.
</think:6124c78e><tool_call:6124c78e>edit<arg_key:6124c78e>path</arg_key:6124c78e><arg_value:6124c78e>C:\Users\ebenh\OneDrive\Coding\ha-maxcube\docs\de\RUNBOOK.md