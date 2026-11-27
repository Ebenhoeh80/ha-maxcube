> Deutsche Übersetzung von docs/IDENTITY.md. Maschinell erstellt, Muttersprachlerprüfung offen.

# Identität eines Cube

Ein physischer MAX! Cube ist ein Leben lang ein Gerät, ganz gleich, wie sich seine Netzwerkadresse ändert.
Diese Seite hält fest, was was identifiziert, welche Regeln der Code befolgt und wie bestehende
Installationen migriert wurden.

## Was was identifiziert

| Sache | Identität | Stabil? |
|---|---|---|
| Config Entry (`unique_id`) | Seriennummer des Cube (zum Beispiel `JEQ0355273`) | ja, auf dem Cube aufgedruckt |
| In der Integrationsliste angezeigter Titel | `MAX! Cube <serial>` (ein vom Nutzer gewählter Name bleibt erhalten) | ja |
| Hub-Gerät in der Geräte-Registry | Kennung `(maxcube_local, <serial>)` | ja (unverändert seit 1.1) |
| Thermostate, Kontakte, Wandthermostate | Kennung `(maxcube_local, <radio address>)` | ja, Funkadressen ändern sich nicht |
| Entitäten | Unique ID `<radio address>…` oder `<serial>_…` | ja (unverändert) |
| **Netzwerkadresse** | nur in `data["host"]` gespeichert | **nein**, sie sind Daten, keine Identität |

Die Adresse eines Cube ändert sich: durch DHCP, einen neuen Router, und ein Cube, der ohne Lease
startet, antwortet von seiner Werksadresse `192.168.0.222`. Vor 1.3.3 war die Adresse die Unique
ID und Teil des Titels, sodass jede solche Änderung die Identität brach (beobachtet am
2026-11-20: der Eintrag behielt den Titel `MAX! Cube (192.168.10.60)`, obwohl er auf
`192.168.0.222` zeigte).

## Regeln im Code

1. **Ein neuer Eintrag übernimmt die Seriennummer vom Cube** (config flow: verbinden, die Seriennummer
   aus der ersten Nachricht lesen, `async_set_unique_id(serial)`); `_abort_if_unique_id_configured(updates={host, port})`
   sorgt dafür, dass ein zweiter Versuch für einen bekannten Cube die Adresse aktualisiert, statt ein Duplikat
   anzulegen.
2. **Discovery nutzt die offiziellen Discovery-Flows.**
   - **DHCP** (`manifest.json`: Präfix der Hardwareadresse `001A22*`, eQ-3): Home Assistant sieht die
     DHCP-Anfrage eines Cube beim Start oder bei einer neuen Adresse und startet den Flow. So wird der
     **erste** Cube ohne Eintrag gefunden und ein bekannter Cube zu seiner neuen Adresse verfolgt.
     Andere eQ-3-Geräte teilen das Präfix; der Flow verbindet sich zuerst und ignoriert alles, was nicht
     als Cube antwortet.
   - **Broadcast-Scan** (UDP 23272) einmal nach dem Start, für weitere Cubes und für bekannte, deren
     Adresse sich geändert hat, während Home Assistant aus war (`integration_discovery`). Er läuft nur,
     solange die Integration geladen ist (es gibt einen Eintrag); ein Cube, der unter derselben Adresse
     eingerichtet ist, wird übersprungen und nicht kontaktiert.
   - Ein neuer Cube erscheint unter *Discovered*; ein bekannter Cube bekommt seine neue Adresse gespeichert.
     Ein Cube, der nur von einer unerreichbaren Adresse antwortet (der Werksadresse), wird nie angeboten oder gespeichert.
3. **Eine geänderte Adresse sind nur Daten, und der Update-Listener lädt neu.** Wer auch immer die neue
   Adresse erfährt (Discovery-Flow oder der Coordinator nach einem fehlgeschlagenen Poll oder Setup: er
   sucht den Cube anhand der Seriennummer und prüft, dass der Datenport antwortet), speichert
   `data["host"]`; der Update-Listener des Eintrags plant ein einmaliges Neuladen, wenn sich Optionen
   oder Adresse geändert haben (das von Home Assistant geforderte Muster; die Flows laden nicht selbst neu).
   Identität und Titel bleiben.
4. **Der antwortende Cube muss der Cube des Eintrags sein.** Jede Verbindung vergleicht die Seriennummer
   in der ersten Nachricht mit `data["cube_serial"]`. Ein anderer Cube unter der gespeicherten Adresse
   (eine übernommene Adresse, ein ersetzter Cube) löst `WrongCubeError` aus: beim Setup wird der richtige
   Cube anhand der Seriennummer gesucht, sonst versucht der Eintrag es erneut; während eines Polls
   schlägt die Aktualisierung mit einem eigenen Identitätsfehler fehl, statt Geräte zu vermischen. Die
   Geräte eines Cube werden nie in den Eintrag eines anderen Cube gemischt.
5. **Ein Cube, ein Eintrag** (die Prüfung und die Beanspruchung der Identität erfolgen ohne `await`
   dazwischen, sodass zwei gleichzeitig startende Einträge nicht beide gewinnen können). Ein zweiter
   Eintrag, dessen Cube bereits zu einem anderen Eintrag gehört, bricht beim Setup mit dem Fehler
   "already managed by the entry …" ab (`ConfigEntryError`); er erzeugt keine Geräte. Ein Cube, der
   manuell hinzugefügt wird, während eine Discovery für ihn wartet, funktioniert (`raise_on_progress=False`).
6. **Der Verbindungstest schließt die Verbindung** (der Cube akzeptiert nur einen Client gleichzeitig);
   ein unerwarteter Fehler im Dialog wird als "unknown" angezeigt, statt den Dialog scheitern zu lassen.
7. **Ein Eintrag, dessen Unique ID überschrieben wurde** (zum Beispiel durch Version 1.3.2 nach einem
   Downgrade) wird beim nächsten Setup korrigiert: die Identität wird gegen die Seriennummer des
   antwortenden Cube geprüft, nicht nur gegen die Minor-Version.

## Migration bestehender Installationen

Einträge, die von 1.0 bis 1.3.2 erstellt wurden, haben `version 1, minor_version 1` und die Adresse
als Unique ID. `async_migrate_entry` hebt sie auf **Minor-Version 2**, ohne etwas zu entfernen und
neu hinzuzufügen:

- Ist die Seriennummer im Eintrag gespeichert (jeder Eintrag mit einem erfolgreichen Setup seit 1.1):
  `unique_id` wird die Seriennummer, ein generierter Titel (`MAX! Cube (address)`) wird zu
  `MAX! Cube <serial>`; ein vom Nutzer gewählter Titel bleibt.
- Ist sie nicht gespeichert: der Eintrag bleibt in Minor-Version 1 und wird beim nächsten
  erfolgreichen Setup abgeschlossen, wenn der Cube antwortet.
- Verwendet ein anderer Eintrag diese Seriennummer bereits, behält der Eintrag seine Adresse als
  Identität (und protokolliert dies), statt ein Duplikat zu erzeugen.
- Ein Eintrag einer neueren Major-Version wird abgelehnt (`False`), wie Home Assistant es verlangt.
- **Es wird kein Registry-Eintrag erzeugt, entfernt oder neu vergeben:** Geräte und Entitäten wurden
  nie über die Adresse identifiziert, daher bleiben vom Nutzer gewählte Entity-IDs, Bereiche und
  Gerätenamen erhalten. Das wird getestet: die Mengen der Entity- und Geräte-IDs vor und nach der
  Migration sind gleich. (Die Integration aktualisiert den Namen und die Firmware des Hubs sowie die
  Namen der Geräte aus den Daten des Cube; ein in Home Assistant vom Nutzer gewählter Name wird nie
  überschrieben.)
- Ein Downgrade auf 1.3.2 funktioniert weiter: der Eintrag ist immer noch Version 1; der ältere Code
  liest einfach die Adresse aus seinen Daten. 1.3.2 schreibt die Adresse bei einer neuen Cube-Adresse
  wieder in die Unique ID; das nächste Setup mit dieser Version korrigiert es (Regel 7). Ein Cube, der
  unter 1.3.2 erneut manuell hinzugefügt wird, kann ein Duplikat erzeugen; das lässt sich von hier
  nicht verhindern.
- Ein Eintrag, der beim ersten Start nicht migriert werden kann (keine Seriennummer gespeichert und
  der Cube antwortet nicht), wird beim nächsten erfolgreichen Setup abgeschlossen.

## Entscheidungen und verworfene Optionen

- **Minor, nicht Major-Version:** die Daten bleiben für älteren Code lesbar, genau das bedeutet eine
  Minor-Version.
- **Die Adresse im Coordinator statt nur über den Discovery-Flow aktualisieren:** der Discovery-Flow
  kann während des Setups eines Eintrags nicht laufen (dann gibt es kein Neuladen), und ein
  fehlgeschlagener Poll braucht die neue Adresse sofort. Beide Wege nehmen dieselbe Änderung vor
  (`data["host"]`), im Code dokumentiert.
- **MAC-Adresse als Verbindung in der Geräte-Registry:** der Cube meldet seine MAC-Adresse im
  Protokoll nicht; die Seriennummer ist das einzige stabile Kennzeichen, das er meldet.
- **Ein ersetzter Cube** (neue Seriennummer an der alten Adresse) wird abgelehnt (`WrongCubeError`,
  der Eintrag versucht es erneut): seine Geräte dürfen nicht in den Eintrag des alten Cube gemischt
  werden. Eintrag entfernen und den neuen Cube hinzufügen; es gibt keine automatische Übernahme.
  Der Reconfigure-Flow ist kein Ersatz dafür: er dient einer manuellen Adressänderung, während die
  automatische Wiedererkennung unten den realen Fall (derselbe Cube hat eine neue Adresse) ohne
  Nutzerabfrage abdeckt.
- **Spoofing:** das Protokoll des Cube kennt keine Authentifizierung, daher kann ein Host im lokalen
  Netzwerk, der auf den Broadcast antwortet und die Verbindung annimmt, sich als Cube ausgeben, und
  die behauptete Seriennummer ist kein Beweis. Der Seriennummervergleich bei jeder Verbindung
  (`WrongCubeError`) schützt vor *Verwechslungen* (zwei Cubes, eine übernommene Adresse), nicht vor
  Fälschung. Eine Adresse wird erst gespeichert, nachdem das Gerät unter dieser Adresse mit der
  erwarteten Seriennummer geantwortet hat, und ein Kandidat ohne Seriennummer wird verworfen
  (`_async_connect_at`). Wenn ein bestehender Eintrag umgeleitet werden soll, prüft der config flow
  die behauptete Seriennummer auch am neuen Host. Das verhindert, dass eine gefälschte Discovery-Antwort
  einen Eintrag dauerhaft verschiebt; es authentifiziert den Cube selbst nicht.
- **Reauth:** nicht anwendbar, der Cube hat keine Authentifizierung. Eine geänderte Adresse wird nach
  einem fehlgeschlagenen Poll oder beim Start anhand der Seriennummer gefunden und automatisch
  gespeichert; der Reconfigure-Flow dient nur der manuellen Adresseingabe.
- **Reparatur für einen unerreichbaren Cube:** seit 1.5.0 erscheint nach sechs Stunden ohne Antwort
  ein Hinweis (von der Integration nicht behebbar); davor zeigen die nicht verfügbaren Entitäten und
  die Logzeile über einen umgezogenen Cube dies an.
