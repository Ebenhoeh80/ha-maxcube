# eQ-3 MAX! Cube — Home-Assistant-Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/default)
[![GitHub Release](https://img.shields.io/github/v/release/Ebenhoeh80/ha-maxcube)](https://github.com/Ebenhoeh80/ha-maxcube/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.11+-41BDF5.svg?logo=home-assistant&logoColor=white)](https://www.home-assistant.io)
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
  - HVAC-Modi Auto / Heizen / Aus,
  - Presets Boost, Komfort, Eco, Abwesend,
  - Heizaktion aus der Ventilstellung abgeleitet,
  - Komfort-/Eco-Sollwerte und Ventilstellung als Zusatz-Attribute.
- **Wochen-Heizprogramm** (vorerst nur lesen): Das Programm jedes Thermostats steht im Attribut `schedule`
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

## 📦 Voraussetzungen

- Ein **eQ-3 MAX! Cube LAN-Gateway**, im Netzwerk erreichbar (Standard-Port `62910`).
- Home Assistant **2024.11** oder neuer.

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

- ✅ Wochenprogramm: Heizplan anzeigen (1.2.0)
- 🔜 Wochenprogramm: Heizplan setzen
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
