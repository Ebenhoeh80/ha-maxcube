# Release eQ-3 MAX! Cube

[English](RELEASING.md) | [Deutsch](RELEASING.de.md)

So wird ein Release Schritt für Schritt erstellt, ohne dass es auf jemandes Erinnerung ankommt.
Versionen folgen [Semantic Versioning](https://semver.org/): ein Breaking Change erhöht die
Major-Version, ein neues Feature die Minor-Version, ein Fix die Patch-Version.

## 1. Vorbereiten

1. Sicherstellen, dass alles, was ins Release gehört, auf `main` gemergt ist und CI grün ist.
2. In `CHANGELOG.md` **und** `CHANGELOG.en.md` `[Unreleased]` in `[x.y.z] - JJJJ-MM-TT`
   umbenennen und darüber ein neues leeres `[Unreleased]` anlegen. Beide Abschnitte werden zu den
   zweisprachigen Release Notes; ein Release ohne eine der beiden Sprachen ist ein Mangel.
3. Die neue Version in `custom_components/maxcube_local/manifest.json` setzen.

## 2. Lokal prüfen

CI führt bereits Ruff, MyPy, Xenon, die reinen Unit-Tests, die Tests in einem echten
Home-Assistant-Core, Hassfest und die HACS-Validierung aus. Bei Codeänderungen dieselben Befehle
lokal ausführen und die Änderung auf einer Home-Assistant-Instanz mit echtem Cube prüfen: das
Single-Client-Protokoll des Cube lässt sich nicht vollständig simulieren.

## 3. Pull Request

Einen Pull Request mit Changelog- und Versionsänderung öffnen, **alle** Checks abwarten (Tests auf
aktueller und Mindest-HA-Version, Lint, Typen, Komplexität, Hassfest und HACS `validate`) und per
Squash mergen. Ein Release wird nicht bei einem roten oder übersprungenen Check vorbereitet; es
gibt keine dokumentierten Ausnahmen.

## 4. Tag

Den Tag auf dem Merge-Commit von `main` erstellen und pushen:

```bash
git checkout main && git pull
git tag vX.Y.Z
git push origin vX.Y.Z
```

Der Tag **muss** `v` plus die Version aus `manifest.json` sein. Ein Suffix wie `-rc.1` macht es
zu einem Pre-Release (denselben Suffix in die Manifest-Version schreiben).

## 5. Was der Workflow macht

Der Tag startet `.github/workflows/release-zip.yml`, das den gemeinsamen Workflow in
[`Ebenhoeh80/.github`](https://github.com/Ebenhoeh80/.github) aufruft. Er prüft, dass der Tag zur
Manifest-Version passt, baut `maxcube_local.zip` (Integrationsdateien im Zip-Wurzelverzeichnis, wie
HACS es bei `zip_release` erwartet) und erstellt oder aktualisiert das GitHub-Release mit dem
passenden Changelog-Abschnitt und dem Zip als Asset. Weichen Tag und Version ab, bricht der
Workflow ab und nichts wird veröffentlicht.
Ein zweiter Job führt anschließend `scripts/release_notes.py` aus und ersetzt den Release-Text
durch die deutschen **und** englischen Changelog-Abschnitte (der gemeinsame Workflow veröffentlicht
nur Deutsch). Fehlt der englische Abschnitt, schlägt der Job fehl, statt eine unvollständige
Übersetzung zu veröffentlichen.

## 6. Release prüfen

- Die Release-Seite zeigt den Changelog-Text in Deutsch und Englisch sowie das Asset
  `maxcube_local.zip`.
- HACS bietet die neue Version an (falls es langsam ist, *Update information* im Repository nutzen).

## 7. Live-System aktualisieren und prüfen

Zuerst ein Home-Assistant-Backup erstellen. Dann über HACS aktualisieren, Home Assistant neu
starten und prüfen, dass die Thermostate Ist- und Solltemperatur anzeigen, nichts `unavailable`
ist und im Log keine neuen Warnungen für `maxcube_local` auftauchen.

## 8. Nach dem Release

- Falls das Repository im HACS-Standardkatalog ist und eine Prüfung eine Änderung verlangt hat,
  in dortigen Pull Request antworten.
- Prüfen, ob README, Übersetzungen und Roadmap-Abschnitt noch passen.
