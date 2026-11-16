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

- **Einrichtung per UI (Config-Flow)** — einfach die IP-Adresse des Cubes eingeben,
  kein YAML.
- **Climate**-Entitäten für Heizkörper- und Wandthermostate:
  - Zieltemperatur (0,5-°C-Schritte),
  - HVAC-Modi Auto / Heizen / Aus,
  - Presets Boost, Komfort, Eco, Abwesend,
  - Heizaktion aus der Ventilstellung abgeleitet,
  - Komfort-/Eco-Sollwerte und Ventilstellung als Zusatz-Attribute.
- **Sensoren**: gemessene Temperatur je Thermostat und Ventilöffnung (%) je
  Heizkörperthermostat.
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

1. HACS → Drei-Punkte-Menü → **Benutzerdefinierte Repositories**.
2. `https://github.com/Ebenhoeh80/ha-maxcube` hinzufügen, Kategorie **Integration**.
3. **eQ-3 MAX! Cube** installieren, dann Home Assistant neu starten.
4. **Einstellungen → Geräte & Dienste → Integration hinzufügen → eQ-3 MAX! Cube**,
   IP-Adresse des Cubes eingeben.

(Alternativ `custom_components/maxcube` in den Ordner `config/custom_components`
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
- **Drop-in-Ersatz.** Diese Integration nutzt dieselbe Domain `maxcube` wie die
  Core-Integration und überschattet sie. Entferne zuvor jeden `maxcube:`-Block aus
  der `configuration.yaml`.
- Die MAX!-Cloud wurde 2023 von eQ-3 abgeschaltet; diese Integration nutzt sie nicht.

---

## 🙏 Credits

Basiert auf dem reverse-engineerten MAX!-Protokoll und der Bibliothek
[`maxcube-api`](https://github.com/uebelack/python-maxcube-api) sowie auf der
Core-`maxcube`-Integration und der Community-Fork
[MassiPi/maxcube](https://github.com/MassiPi/maxcube).

---

## ❤️ Projekt unterstützen

<div align="center">

**Ich entwickle und pflege diese Integration in meiner Freizeit – und trage die laufenden Kosten aus eigener Tasche.**

Wenn sie dir Zeit oder Ärger erspart, hält eine kleine freiwillige Spende das Projekt am Leben und motiviert zu neuen Funktionen.
Jeder Beitrag, egal wie klein, freut mich riesig. Vielen Dank! 🙏

<a href="https://www.paypal.com/pool/9p84qTHCFr?sr=wccr">
  <img src="https://img.shields.io/badge/Spendier%20mir%20einen%20Kaffee-PayPal-00457C?style=for-the-badge&logo=paypal&logoColor=white" alt="Spenden via PayPal" height="42">
</a>

</div>

---

## 📄 Lizenz

MIT © 2026 Daniel Ebenhöh — siehe [LICENSE](LICENSE).
