# qrsalvage

*recover QR codes from what's left of them*

Werkzeug zur Rekonstruktion schwer lesbarer QR-Codes — gewölbte Flächen, Lasergravur,
Verschmutzung, schlechter Kontrast. Drei Wege zum selben Ziel: vollautomatisch, durch einen
AI-Agenten über ein Textinterface, oder durch einen Menschen über eine Canvas-Oberfläche.

Das Verzeichnis heißt noch `whichqrcode` — das ist der lokale Arbeitsordner, nicht der
Projektname. Beim Anlegen des öffentlichen Repositories wird daraus `qrsalvage`.

## Commands

Alle Befehle in PowerShell aus dem Projekt-Root. Das Venv wird nie aktiviert, sondern direkt
adressiert — so ist immer eindeutig, welcher Interpreter läuft.

- Setup (einmalig): `py -3.11 -m venv .venv`, dann `.venv\Scripts\python.exe -m pip install -r requirements.txt`, dann `.venv\Scripts\python.exe -m pip install -e .`
- Code lesen: `.venv\Scripts\python.exe -m qrsalvage solve <bild> [--crop X0 Y0 X1 Y1]`
- Mehrere Fotos desselben Codes: `.venv\Scripts\python.exe -m qrsalvage solve <bild1> <bild2> ...`
- Katalog verschiedener Codes als A4-PDF: `.venv\Scripts\python.exe -m qrsalvage catalog <bilder...> [--titles ...]`
- Mehrbild-Gewinn messen: `.venv\Scripts\python.exe scripts\multi_image.py`
- Kalibrierung der Posterior messen: `.venv\Scripts\python.exe scripts\calibration.py`
- A/B einzelner Verfahrensteile: `scripts\ab_ensemble.py`, `scripts\ab_sigma.py`, `scripts\ab_bow.py`
- Testfall erzeugen: `.venv\Scripts\python.exe -m qrsalvage synth "<text>" --contrast 0.14 --curvature 0.4`
- Schwierigkeitskurve messen: `.venv\Scripts\python.exe scripts\difficulty.py`
- Test: `.venv\Scripts\python.exe -m pytest`
- Test ohne Bildkorpus (schnell): `.venv\Scripts\python.exe -m pytest -m "not regression"`
- Nur Bildregression: `.venv\Scripts\python.exe -m pytest -m regression`
- Lint: `.venv\Scripts\python.exe -m ruff check .`
- Format: `.venv\Scripts\python.exe -m ruff format .`

Es gibt keinen Build-Schritt. Die Oberfläche ist eine statische HTML/JS-Datei, kein npm.

## Stack

- Python 3.11 im lokalen `.venv` (nicht 3.14 — dafür fehlen OpenCV-Wheels; 3.12 und 3.13 sind
  auf diesem Rechner nur Karteileichen im py-Launcher, die Installationen fehlen)
- OpenCV, NumPy, Pillow für Bildverarbeitung; zxing-cpp für Decodier-Versuche auf Bildern
- pytest, ruff
- Oberfläche: eine HTML-Datei mit Canvas, ausgeliefert von einem lokalen Python-Server

## Architektur

- `src/qrsalvage/core/` — der bibliotheksreine Kern:
  - `preprocess.py` Beleuchtungskorrektur und Rasterfusion
  - `structure.py` die Zellen, die der Standard festlegt — das Eichmaß des Verfahrens
  - `geometry.py` Findersuche, Gitteraufbau, Nachjustieren der Eckpunkte
  - `sampling.py` Zellabtastung, Helligkeitsmodell, Wahrscheinlichkeit je Modul
  - `matrix.py` Modulraster mit drei Zuständen
  - `galois.py` GF(256) und Reed-Solomon mit Erasure-Unterstützung
  - `qrspec.py` Blocktabellen, Maskenmuster, Formatinformation
  - `layout.py` Modulplatzierung, Verschachtelung, Format lesen und schreiben
  - `repair.py` macht unsichere Zellen zu Auslassungen; steigert deren Zahl nur so weit,
    wie eine äußere Prüfung das Ergebnis akzeptiert
  - `decoding.py` Zeichnen, Decodieren, geordnetes Nachtasten, Neukodieren
  - `ensemble.py` Mehrfachmessung. Die zwei Varianten *innerhalb* eines Bildes sind
    standardmäßig aus — beide teilen sich den Gitterfehler und lösen messbar keinen Fall mehr.
    Die Fusion mehrerer Fotos desselben Codes ist die einzige mit positivem Messergebnis; sie
    läuft automatisch, sobald `solve` mehrere Bilder bekommt. Alle Messwerte im Docstring
  - `pipeline.py` fügt zusammen, entscheidet nichts selbst
- `src/qrsalvage/synth.py` — künstlich verdorbene Fälle mit bekannter Antwort
- `src/qrsalvage/cli.py` — Textinterface, zugleich der Agentenweg. Alles Ausgeben und Schreiben
  passiert hier, nie im Kern.
- `src/qrsalvage/server.py` + `web/index.html` — lokale Oberfläche, nur auf 127.0.0.1,
  eine statische Datei ohne Build-Schritt
- `fixtures/` — synthetisches, öffentliches Korpus (`scripts/make_fixtures.py`)
- `fixtures-local/` — echte Fotos, gitignoriert, verlassen den Rechner nicht
- `tests/`, `scripts/` (Messwerkzeuge, kein Produktionscode)

Wohin das Projekt will und in welcher Reihenfolge: `docs/VISION.md` (Fahrplan mit
Begründungen). Technische Einzelaufgaben: `docs/ISSUES.md`.

## Rules

- **Der Kern ist bibliotheksrein.** Nichts unter `src/qrsalvage/core/` importiert CLI-, Server- oder
  UI-Code oder gibt etwas auf stdout aus. CLI und Canvas sind zwei dünne Schalen über demselben
  Kern — sobald einer der beiden Wege eigene Logik bekommt, driften Agenten- und Menschenweg
  auseinander und liefern verschiedene Ergebnisse.
- **Eine Zelle hat drei Zustände: schwarz, weiß, unbekannt.** Nie auf zwei reduzieren, auch nicht
  "zur Vereinfachung" in einer Zwischenschicht. Reed-Solomon korrigiert doppelt so viele Erasures
  wie Fehler — Unsicherheit zu verwerfen wirft den halben Hebel des Projekts weg.
- **Kein Netzwerkzugriff zur Laufzeit.** Weder im Kern noch in der Oberfläche.
- **Bilder und entschlüsselter Klartext verlassen das Projekt nie.** Keine Online-Decoder, keine
  Uploads, kein Einfügen von Klartext in Commit-Nachrichten oder Issues. Die Fotos zeigen Hände und
  Wohnräume, die Codes enthalten Geräte-Install-Codes.
- **`fixtures/` ist unantastbar.** Bilder und Erwartungsdateien dort werden nie überschrieben oder
  gelöscht, nur ergänzt. Ein Fixture, das nicht mehr passt, ist ein Befund, kein Aufräumfall.
- **Keine Abhängigkeit ohne Rückfrage.** `pip install` und Venv-Änderungen immer vorher ansprechen,
  auch für scheinbar harmlose Hilfspakete.
- **Erfolgsquoten werden gemessen, nicht geschätzt.** Aussagen wie "das sollte jetzt besser
  funktionieren" gehören durch einen Lauf der Regressionssuite belegt.

## Konventionen

- **Alles im Code auf Englisch** — Bezeichner, Dateinamen, Docstrings, Kommentare, Testnamen
  und Programmausgaben. Das Projekt wird veröffentlicht, und die Begründungen in den Docstrings
  sind sein wertvollster Teil; auf Deutsch wären sie für die meisten Leser wertlos.
- Diese Datei, `docs/` und die Skills unter `.claude/` bleiben deutsch — sie richten sich an
  dich, nicht an Beitragende.
- Antworten an den Nutzer auf Deutsch.
- Modulkoordinaten heißen durchgehend `(row, col)` mit Ursprung oben links, Pixelkoordinaten
  `(x, y)`. Verwechslung der beiden ist in diesem Projekt die wahrscheinlichste Fehlerquelle.
