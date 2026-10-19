# Veröffentlichung eines Releases

Diese Checkliste beschreibt die externen Schritte einer Veröffentlichung. Sie führt keinen davon
automatisch aus.

## Voraussetzungen

- Der Release-Branch ist sauber und enthält ausschließlich die beabsichtigten Änderungen.
- Die vollständige Verifikation einschließlich Tests, Lint und Typprüfung ist erfolgreich.
- Für Änderungen am Wiederherstellungspfad liegt nachvollziehbare Benchmark-Evidenz vor.
- GitHub ordnet die Commits der vorgesehenen Identität zu und erkennt ihre Signaturen an. Ein
  `[verified]` im Commit-Betreff ist nur Text und keine Signatur.

## Reihenfolge

1. Die nächste Version festlegen und in `pyproject.toml` eintragen.
2. Die vollständige Verifikation erneut ausführen.
3. Einen signierten Tag im Format `vX.Y.Z` erstellen.
4. Branch und Tag zu GitHub pushen.
5. Einen GitHub Release erstellen und Wheel sowie Source Distribution anhängen.
6. Exakt dieselben Artefakte auf PyPI veröffentlichen.
7. Die Installation in einer frischen Umgebung prüfen.
8. Erst nach erfolgreicher Installation die README auf `pip install qrsalvage` umstellen.

## GitHub-Einstellungen

- `main` durch Pull Requests und erforderliche erfolgreiche CI-Prüfungen schützen.
- Force-Pushes und das Löschen von `main` verbieten.
- `harden-declared-invariants` erst löschen, nachdem bestätigt wurde, dass der Branch keine
  eindeutigen Commits enthält.

## Abbruch

Wenn ein Artefakt-Digest abweicht, eine frische Installation fehlschlägt, eine Signatur nicht
anerkannt wird oder eine CI-Prüfung fehlschlägt, wird der nächste Veröffentlichungskanal nicht
bedient. PyPI wird bis zur vollständigen Klärung nicht beworben.
