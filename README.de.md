# eQ-3 MAX! Cube — Home-Assistant-Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/default)
[![GitHub Release](https://img.shields.io/github/v/release/Ebenhoeh80/ha-maxcube)](https://github.com/Ebenhoeh80/ha-maxcube/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2025.3+-41BDF5.svg?logo=home-assistant&logoColor=white)](https://www.home-assistant.io)
[![Spenden via PayPal](https://img.shields.io/badge/❤%20Spenden-PayPal-00457C.svg?logo=paypal&logoColor=white)](https://www.paypal.com/pool/9p84qTHCFr?sr=wccr)

[English](README.md) | [Deutsch](README.de.md)

Eine moderne, per UI einrichtbare Home-Assistant-Integration für das
**eQ-3-/ELV-MAX!**-Heizsystem. Sie spricht **lokal** mit dem originalen
**MAX! Cube LAN-Gateway** über TCP — der Cube bleibt im Originalzustand
(kein Flashen, kein CUL/CUN, keine Cloud).

Sie ist ein Config-Flow-Ersatz für die veraltete, nur per YAML konfigurierbare
`maxcube`-Integration aus Home Assistant Core.

---

## ✨ Funktionen

- **Einrichtung per UI (Config-Flow)** — der Cube wird im Netzwerk **automatisch
  erkannt** (seine IP-Adresse wird vorausgefüllt); kein YAML.
- **Climate**-Entitäten für Heizkörper- und Wandthermostate:
  - Zieltemperatur (0,5-°C-Schritte),
  - HVAC-Modi Auto / Heizen / Aus („Aus" = Handbetrieb mit 4,5 °C; „Heizen" stellt den letzten Sollwert wieder her),
  - Presets Boost, Komfort, Eco, Abwesend,
  - Heizaktion aus der Ventilstellung abgeleitet,
  - Komfort-/Eco-Sollwerte und Ventilstellung als Zusatz-Attribute.
- **Wochen-Heizprogramm** (lesen und schreiben): Das Programm jedes Thermostats steht im Attribut `schedule`
  der Klima-Entität (je Tag die Schaltpunkte mit der Uhrzeit, bis zu der die jeweilige Temperatur gilt, mit
  genauen halben Grad), dazu `scheduled_temperature`, die Temperatur, die das Programm gerade vorgibt. Der
  Dienst `maxcube_local.get_schedule` gibt es als Antwort zurück.
- **Sensoren**: gemessene Temperatur je Thermostat und Ventilöffnung (%) je
  Heizkörperthermostat.
- **Cube-Diagnose**: die **Funkauslastung** (%) und die Zahl der **freien Speicherplätze**, bei jeder
  Abfrage gelesen. Der Cube darf nur einen begrenzten Teil der Funkzeit nutzen; bei 100 % sendet er etwa
  eine Stunde lang keine Funkbefehle, achte darauf besonders beim Ändern vieler Einstellungen.
- **Findet den Cube nach einem IP-Wechsel** (DHCP) wieder: Er wird über die Seriennummer gesucht, die neue
  Adresse wird automatisch gespeichert.
- **Dienst `maxcube_local.reconnect`** trennt die Verbindung zum Cube und liest alles erneut aus.
- **Binärsensoren**: Fenster-/Türkontakte und Batterie-schwach-Warnung je Gerät.
- Der **Cube** erscheint als Hub-Gerät mit Firmware-Version; alle Geräte werden
  darunter gruppiert und ihrem MAX!-Raum zugeordnet.
- **Optionen**: einstellbares Abfrageintervall (30–600 s).

---

## 🗓️ Wochen-Heizprogramm

Jedes Heizkörperthermostat zeigt sein Programm im Attribut `schedule` der Klima-Entität und als Antwort
von `maxcube_local.get_schedule`. Zum **Ändern** gibt es `maxcube_local.set_schedule` für ein oder mehrere
Heizkörperthermostate (Wandthermostate lassen sich hier nicht programmieren):

```yaml
action: maxcube_local.set_schedule
target:
  entity_id: climate.kinderzimmer_thermostat_kinderzimmer
data:
  days: [monday, tuesday, wednesday, thursday, friday]
  periods:
    - {until: "05:00", temperature: 17}
    - {until: "08:00", temperature: 21}
    - {until: "17:00", temperature: 18.5}
    - {until: "23:00", temperature: 21}
    - {until: "24:00", temperature: 17}
```

Jeder Abschnitt gibt die Temperatur an, die **bis** zur genannten Uhrzeit gilt; der letzte Abschnitt muss um
`24:00` enden. Höchstens sieben Abschnitte pro Tag, Zeiten in 5-Minuten-Schritten, Temperaturen in halben
Grad von 4,5 („aus“) bis 30,5 („an“). Dasselbe Programm wird auf jeden genannten Tag geschrieben; für andere Abschnitte an anderen
Tagen siehe `by_day` unten. Mit `dry_run: true` wird die Eingabe nur geprüft: Es wird nichts an den Cube
gesendet.

- Nach dem Schreiben liest die Integration das Programm vom Cube zurück und meldet je Tag, ob der Cube jetzt
  genau das zeigt, was du angegeben hast: `confirmed`, oder `sent_not_confirmed`, wenn der Cube die Nachricht
  angenommen hat, aber noch das alte Programm zeigt. Der Cube aktualisiert seine Kopie erst, nachdem das
  Thermostat die Änderung übernommen hat, das dauert etwa zwei Minuten; schau also etwas später ins Attribut
  `schedule`. Zeigt er nach fünf Minuten immer noch das alte Programm, wird eine Warnung ins Log geschrieben.
  Ein Tag, den der Cube verweigert, löst einen Fehler aus.
- Jeder Tag ist eine Funknachricht. Der Dienst schreibt nicht, wenn der Cube schon 90 % seiner Funkzeit
  verbraucht hat (siehe den Sensor *Funkauslastung*).
- Das Programm wirkt nur, solange ein Thermostat im **Automatik**-Modus ist.
- Das Wochenprogramm wird je Thermostat gespeichert. Die MAX!-Software setzt es je Raum; damit ein Raum
  einheitlich bleibt, wähle alle Heizkörperthermostate des Raums als Ziel.

### Verschiedene Abschnitte je Tag

`by_day` gibt jedem Tag eigene Abschnitte, statt `days` und `periods` (nicht zusammen verwenden):

```yaml
action: maxcube_local.set_schedule
target:
  entity_id: climate.kinderzimmer_thermostat_kinderzimmer
data:
  by_day:
    monday: [{until: "24:00", temperature: 17}]
    saturday: [{until: "08:00", temperature: 19}, {until: "24:00", temperature: 21}]
```

### Programm auf andere Thermostate kopieren

`maxcube_local.copy_schedule` kopiert das Programm eines Heizkörperthermostats (`source`) auf andere
Heizkörperthermostate (`targets`), für alle sieben Tage oder nur für die Tage in `days`:

```yaml
action: maxcube_local.copy_schedule
data:
  source: climate.kinderzimmer_thermostat_kinderzimmer
  targets: [climate.schlafzimmer_thermostat, climate.gaestezimmer_thermostat]
  days: [saturday, sunday]   # optional, Standard: alle sieben Tage
```

Geschrieben wird nur an den Tagen, die sich vom Programm des Ziels unterscheiden. Vor dem ersten Funktelegramm
schätzt die Integration die Funkzeit (etwa 2,8 % je Telegramm, zur aktuellen Funkauslastung addiert). Würde
der Cube 90 % erreichen, wird die Anfrage abgelehnt und nichts gesendet. Die Antwort nennt das Ergebnis je
Thermostat und Tag (`unchanged`, `confirmed`, `sent_not_confirmed` oder `failed`). Quelle und Ziele müssen
Heizkörperthermostate desselben Cubes sein.

### Karte für das Wochenprogramm

Die Integration bringt eine Lovelace-Karte zum Ansehen und Bearbeiten des Programms mit: Sie erscheint im
Kartenwähler als **MAX! Cube Wochenprogramm** (keine Ressource von Hand nötig; nach einem Update
`Strg+Shift+R` drücken, damit der Browser die neue Datei lädt).

```yaml
type: custom:maxcube-schedule-card
entity: climate.kinderzimmer_thermostat_kinderzimmer   # optional, sonst das erste Thermostat
size: medium                                           # small | medium | large
```

Zonen lassen sich ziehen, Temperatur und Endzeit darunter eintippen, ein Tag auf andere Tage kopieren und die
Thermostate zum Schreiben auswählen. Es werden nur Heizkörperthermostate angeboten (Wandthermostate lassen
sich nicht programmieren). Ohne Änderung wird nichts gesendet, und es werden nur geänderte Tage geschrieben.
**Jeder geschriebene Tag je Thermostat ist ein Funktelegramm und braucht etwa 2,8 % der Funkzeit des Cubes**;
darum fragt die Karte vor dem Schreiben auf mehr als ein Thermostat oder mehr als drei Tage nach. Mit der
Dry-Run-Option lässt sich ein Programm prüfen, ohne es zu senden. Die Karte stammt von @helpmeifyoucan.

---

## 🌡️ Anzeige am Wandthermostat

Das Display eines Wandthermostats zeigt entweder die Solltemperatur (Standard) oder die gemessene Raumtemperatur.
Pro Wandthermostat schalten zwei Schaltflächen um: **Raumtemperatur anzeigen** und **Solltemperatur anzeigen**. Jeder
Druck sendet ein Funktelegramm. Ist der Cube schon bei 90 % Funkzeit, wird der Druck abgelehnt. Den aktuellen
Zustand kann der Cube nicht melden, daher zeigt die Integration dafür keinen Zustand an. Heizkörperthermostate haben
diese Einstellung nicht.

---

## 📦 Voraussetzungen

- Ein **eQ-3 MAX! Cube LAN-Gateway**, im Netzwerk erreichbar (Standard-Port `62910`).
- Home Assistant **2025.3** oder neuer.

---

## ⬇️ Installation (HACS)

1. In HACS nach **eQ-3 MAX! Cube** suchen und installieren.
2. Home Assistant neu starten.
3. **Einstellungen → Geräte & Dienste → Integration hinzufügen → eQ-3 MAX! Cube**,
   IP-Adresse des Cubes eingeben (sie ist vorausgefüllt, wenn der Cube automatisch gefunden wird).

Findest du die Integration in HACS noch nicht, füge sie als benutzerdefiniertes
Repository hinzu: HACS → Drei-Punkte-Menü → **Benutzerdefinierte Repositories**,
`https://github.com/Ebenhoeh80/ha-maxcube` mit Kategorie **Integration** eintragen und
dann wie oben installieren.

(Alternativ `custom_components/maxcube_local` in den Ordner `config/custom_components`
kopieren.)

---

## 🔁 Umstieg von der Legacy-Integration

Die eingebaute `maxcube`-Integration ist reines YAML und hat keinen Config-Eintrag
— es gibt also nichts, was Home Assistant automatisch migrieren könnte. Da beide
Integrationen die Entity-IDs aus **denselben Cube-Gerätenamen** bilden, bleiben
History, Dashboards und Automationen bei einem sauberen Umstieg erhalten:

1. `maxcube:`-Block aus der `configuration.yaml` entfernen → Home Assistant **neu starten**.
2. Diese Integration hinzufügen und die Cube-IP eingeben.

Die neuen Entitäten übernehmen dieselben `climate.<name>`-IDs, die Recorder-History
läuft weiter. Einzelne, die nicht exakt passen, unter *Einstellungen → Entitäten*
angleichen.

---

## ⚠️ Wichtige Hinweise

- **Nur eine Verbindung gleichzeitig.** Der Cube akzeptiert nur einen Client.
  Schließe die MAX!-Smartphone-App — und entferne die alte YAML-`maxcube:`-
  Integration — bevor du diese hinzufügst, sonst schlägt die Einrichtung mit
  *Verbindung fehlgeschlagen* fehl.
- **Eigenständig (kein Core-Override).** Entferne zuvor jeden alten `maxcube:`-Block
  aus der `configuration.yaml` — sonst hält die alte Integration die einzige
  Verbindung des Cubes besetzt.
- Die MAX!-Cloud wurde 2023 von eQ-3 abgeschaltet; diese Integration nutzt sie nicht.

---

## ⚙️ Konfiguration

| Einstellung | Wo | Bedeutung |
| :--- | :--- | :--- |
| IP-Adresse | Einrichtung oder **Neu konfigurieren** | Adresse des Cubes. Vorbelegt, wenn der Cube auf die Suche antwortet. |
| Port | Einrichtung oder **Neu konfigurieren** | Standard `62910`. |
| Abfrageintervall | **Konfigurieren** (Optionen), 30–600 s | Wie oft der Cube gelesen wird. Standard 60 s. Lesen ist günstig; Funkzeit verbrauchen vor allem Schreibzugriffe. |

**Neue Adresse für den Cube?** Die Integration sucht ihn über seine Seriennummer und speichert die neue Adresse
selbst. Klappt das nicht, nutze **⋮ → Neu konfigurieren** am Integrationseintrag und gib die neue IP ein; Geräte,
Namen und Verlauf bleiben erhalten.

---

## 🖥️ Unterstützte Geräte

| Gerät | Unterstützt |
| :--- | :--- |
| MAX! Cube LAN-Gateway | ja (Hub-Gerät, Firmware, Funkauslastung, freie Speicherplätze) |
| Heizkörperthermostat / Thermostat+ | ja (Klima, Temperatur, Ventilstellung, Batterie, Wochenprogramm lesen und schreiben) |
| Wandthermostat | ja (Klima, Temperatur, Batterie; das Programm wird angezeigt, nicht geschrieben) |
| Fenster-/Türkontakt | ja (offen/geschlossen, Batterie) |
| Eco-Taster | noch nicht |

## 🔧 Unterstützte Funktionen

Lesen: Soll- und Isttemperatur, Modus, Voreinstellungen, Ventilstellung, Fensterzustand, Batterie, Wochenprogramm,
Funkauslastung, freie Speicherplätze. Schreiben: Solltemperatur, HVAC-Modus, Voreinstellung, Wochenprogramm
(Heizkörperthermostate). Nicht unterstützt: Geräte koppeln, Komfort-/Eco-/Fenster-Temperaturen ändern, Urlaubsmodus.

## 🔄 Datenaktualisierung

Die Integration fragt den Cube (lokal, ohne Cloud) standardmäßig alle 60 s ab. Jede Abfrage öffnet kurz eine
Verbindung und schließt sie wieder, damit andere Programme den Cube dazwischen nutzen können. Änderungen aus
Home Assistant werden sofort gesendet und bei der nächsten Abfrage zurückgelesen.

## 💡 Anwendungsbeispiele

- **Kinderzimmer an Schultagen früher heizen:** `maxcube_local.set_schedule` (siehe oben) aus einer Automation
  oder einem Skript aufrufen.
- **Vor einem kalten Raum warnen:** Automation auf `climate.<raum>` mit Template-Bedingung, die
  `current_temperature` mit `temperature` vergleicht.
- **Beim Verlassen sparen:** Voreinstellung *Abwesend* mit `climate.set_preset_mode` setzen.

## 🩺 Fehlerbehebung

| Problem | Was prüfen |
| :--- | :--- |
| *Verbindung fehlgeschlagen* bei der Einrichtung | MAX!-App schließen und alten `maxcube:`-YAML-Block entfernen: Der Cube erlaubt nur einen Client. IP und Port prüfen. |
| Entitäten werden „nicht verfügbar“ | Der Cube ist nicht erreichbar. Sensor **Konnektivität** ansehen; dem Cube eine feste Adresse geben oder die automatische Suche nutzen. |
| Ein Thermostat zeigt keine Temperatur | Heizkörperthermostate melden die Isttemperatur nur im Auto-/Manuell-Modus und erst nach dem ersten Funkkontakt. |
| Programmänderung nicht sichtbar | Der Cube zeigt sie nach etwa zwei Minuten; Attribut `schedule` später erneut ansehen. |
| Schreiben abgelehnt (Funkauslastung) | Der Cube hat 90 % seiner Funkzeit genutzt. Warten; bei 100 % sendet er etwa eine Stunde nichts. |

### Cube liefert keine Geräteliste

Manche Cubes senden ihre Raum- und Geräteliste leer. Die Integration nutzt dann die zuletzt gespeicherte Liste; sie wird mit dem Eintrag gespeichert und mit ihm gelöscht. Raum- und Gerätenamen sowie seitdem neu gekoppelte Geräte werden übernommen, sobald der Cube wieder eine gültige Liste sendet. Bleibt der Reparaturhinweis *MAX! Cube liefert keine Geräteliste*, den Cube neu starten (Netzteil 10 Sekunden lang trennen) oder den Cube in der MAX!-Software prüfen.

## 🗑️ Entfernen

**Einstellungen → Geräte & Dienste → eQ-3 MAX! Cube → ⋮ → Löschen.** Der Cube und seine Geräte verschwinden aus Home
Assistant; am Cube selbst ändert sich nichts. Danach bei Bedarf die Integration in HACS entfernen.

## ⚠️ Bekannte Einschränkungen

- Der Cube erlaubt nur einen Client gleichzeitig.
- Wandthermostate lassen sich hier nicht programmieren; Koppeln oder Löschen von Geräten braucht die MAX!-Software.
- Home Assistant speichert das Programm eines Thermostats nicht, es wird vom Cube gelesen.
- Ein neu gekoppeltes Gerät erscheint bei der nächsten Abfrage. Ein aus dem Cube entferntes Gerät verschwindet nach dem nächsten Neuladen oder Neustart aus Home Assistant.

---

## 🙏 Credits

Diese Integration basiert auf der Bibliothek
[`maxcube-api`](https://github.com/uebelack/python-maxcube-api).

Ihre Climate-Plattform ist **von der Home-Assistant-Core-`maxcube`-Integration
abgeleitet**, die unter der Apache-Lizenz 2.0 steht. Der erforderliche
Urheberhinweis und eine Kopie dieser Lizenz liegen in der Datei
[`NOTICE`](NOTICE).

Das Community-Projekt
[MassiPi/maxcube](https://github.com/MassiPi/maxcube) wurde **nur als Referenz**
herangezogen — es hat keine Lizenz, und es ist kein Code daraus enthalten.

---

## 🗺️ Roadmap & Ideen

Geplant und in Prüfung — **gib dem ein 👍, was dir wichtig ist**, und bring eigene Ideen ein:

- ✅ Wochenprogramm: Heizplan anzeigen (1.2.0) und setzen (1.3.0)
- 💡 Reparatur-Hinweis, wenn der Cube nicht erreichbar ist
- 💡 Diagnose-Sensoren (Komfort-/Eco-/Min-/Max-Sollwerte)

➡️ Alle Ideen & Abstimmung: **[Discussions → Ideas](https://github.com/Ebenhoeh80/ha-maxcube/discussions/categories/ideas)**

---

## ❤️ Projekt unterstützen

<div align="center">

**Ich entwickle und pflege diese Integration in meiner Freizeit und trage die laufenden Kosten – meine Zeit, Strom sowie die Entwicklungswerkzeuge und IT-Ausstattung, die ich dafür nutze – aus eigener Tasche.**

Wenn sie dir Zeit oder Ärger erspart, hilft eine kleine freiwillige Spende, das Projekt am Laufen zu halten. Jeder Beitrag, egal wie klein, freut mich riesig. Vielen Dank! 🙏

<a href="https://www.paypal.com/pool/9p84qTHCFr?sr=wccr">
  <img src="https://img.shields.io/badge/Spendier%20mir%20einen%20Kaffee-PayPal-00457C?style=for-the-badge&logo=paypal&logoColor=white" alt="Spenden via PayPal" height="42">
</a>
<a href="https://buymeacoffee.com/daneben">
  <img src="https://img.shields.io/badge/%E2%98%95%20Spendier%20mir%20einen%20Kaffee-FFDD00?style=for-the-badge&logo=buymeacoffee&logoColor=black" alt="Buy Me a Coffee" height="42">
</a>

</div>

---

## 📄 Lizenz

MIT © 2026 Daniel Ebenhöh — siehe [LICENSE](LICENSE).

Teile der Climate-Plattform sind von der Apache-2.0-lizenzierten
Home-Assistant-Core-`maxcube`-Integration abgeleitet; siehe [`NOTICE`](NOTICE)
für den Urheberhinweis und den Text der Apache-Lizenz 2.0.
