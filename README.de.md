# eQ-3 MAX! Cube — Home-Assistant-Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/default)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

Eine moderne, per UI einrichtbare Home-Assistant-Integration für das
**eQ-3-/ELV-MAX!**-Heizsystem. Sie spricht **lokal** mit dem originalen
**MAX! Cube LAN-Gateway** über TCP — der Cube bleibt im Originalzustand
(kein Flashen, kein CUL/CUN, keine Cloud).

Sie ist ein Config-Flow-Ersatz für die veraltete, nur per YAML konfigurierbare
`maxcube`-Integration aus Home Assistant Core.

**Sprache:** [English](README.md) · Deutsch

## Funktionen

- **Einrichtung per UI (Config-Flow)** — einfach die IP-Adresse des Cubes eingeben,
  kein YAML.
- **Climate**-Entitäten für Heizkörper- und Wandthermostate:
  - Zieltemperatur (0,5-°C-Schritte),
  - HVAC-Modi Auto / Heizen / Aus,
  - Presets Boost, Komfort, Eco, Abwesend,
  - Heizaktion abgeleitet aus der Ventilstellung.
- **Binärsensoren**: Fenster-/Türkontakte und Batterie-schwach-Warnung je Gerät.
- **Sensor**: Ventilöffnung in Prozent je Heizkörperthermostat.
- **Optionen**: einstellbares Abfrageintervall (30–600 s).
- Geräte werden je MAX!-Raum gruppiert (Bereichsvorschlag).

## Voraussetzungen

- Ein **eQ-3 MAX! Cube LAN-Gateway**, im Netzwerk erreichbar (Standard-Port `62910`).
- Home Assistant **2024.11** oder neuer.

## Installation (HACS)

1. HACS → Drei-Punkte-Menü → **Benutzerdefinierte Repositories**.
2. `https://github.com/Ebenhoeh80/ha-maxcube` hinzufügen, Kategorie **Integration**.
3. **eQ-3 MAX! Cube** installieren, dann Home Assistant neu starten.
4. **Einstellungen → Geräte & Dienste → Integration hinzufügen → eQ-3 MAX! Cube**,
   IP-Adresse des Cubes eingeben.

(Alternativ `custom_components/maxcube` in den Ordner `config/custom_components`
kopieren.)

## Wichtige Hinweise

- **Nur eine Verbindung gleichzeitig.** Der Cube akzeptiert nur einen Client.
  Schließe die MAX!-Smartphone-App — und entferne die alte YAML-`maxcube:`-
  Integration — bevor du diese hinzufügst, sonst schlägt die Einrichtung mit
  *Verbindung fehlgeschlagen* fehl.
- **Drop-in-Ersatz.** Diese Integration nutzt dieselbe Domain `maxcube` wie die
  Core-Integration und überschattet sie. Entferne zuvor jeden `maxcube:`-Block aus
  der `configuration.yaml`.
- Die MAX!-Cloud wurde 2023 von eQ-3 abgeschaltet; diese Integration nutzt sie nicht.

## Status

Frühes MVP (v0.1.0): Climate + Fenster-/Batterie-Binärsensoren + Ventil-Sensor,
Einrichtung per Config-Flow. Reauth, Auto-Discovery und eine Testsuite sind geplant.

## Credits

Basiert auf dem reverse-engineerten MAX!-Protokoll und der Bibliothek
[`maxcube-api`](https://github.com/uebelack/python-maxcube-api) sowie auf der
Core-`maxcube`-Integration und der Community-Fork
[MassiPi/maxcube](https://github.com/MassiPi/maxcube).

## Lizenz

MIT © 2026 Daniel Ebenhöh
