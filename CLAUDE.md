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
- Zweites Venv (einmalig): dasselbe mit `py -3.12 -m venv .venv312`. Es ist kein Ersatz,
  sondern der Ort, an dem die Versionen liegen, die die CI zieht
- Code lesen: `.venv\Scripts\python.exe -m qrsalvage solve <bild> [--crop X0 Y0 X1 Y1]`
- Mehrere Fotos desselben Codes: `.venv\Scripts\python.exe -m qrsalvage solve <bild1> <bild2> ...`
- Katalog verschiedener Codes als A4-PDF: `.venv\Scripts\python.exe -m qrsalvage catalog <bilder...> [--titles ...]`
- Mehrbild-Gewinn messen: `.venv\Scripts\python.exe scripts\multi_image.py`
- Kalibrierung der Posterior messen: `.venv\Scripts\python.exe scripts\calibration.py`
- A/B einzelner Verfahrensteile: `scripts\ab_ensemble.py`, `scripts\ab_sigma.py`, `scripts\ab_bow.py`
- Testfall erzeugen: `.venv\Scripts\python.exe -m qrsalvage synth "<text>" --contrast 0.14 --curvature 0.4`
- Schwierigkeitskurve messen: `.venv\Scripts\python.exe scripts\difficulty.py`
- Laufzeit messen: `.venv\Scripts\python.exe scripts\runtime.py [--save vorher.json] [--against vorher.json]`
  (nennt die Streuung neben dem Median; eine Änderung innerhalb der Streuung gilt nicht als
  Änderung. Grundlinien sind maschinenspezifisch und werden nicht eingecheckt)
- Test: `.venv\Scripts\python.exe -m pytest`
- Test ohne Bildkorpus (schnell): `.venv\Scripts\python.exe -m pytest -m "not regression"`
- Nur Bildregression: `.venv\Scripts\python.exe -m pytest -m regression`
- Lint: `.venv\Scripts\python.exe -m ruff check .`
- Format: `.venv\Scripts\python.exe -m ruff format .`
- Typen: `.venv\Scripts\python.exe -m mypy` (Konfiguration in `pyproject.toml`; der Kern
  verlangt vollständige Signaturen)
- **Typen wie in der CI: `.venv312\Scripts\python.exe -m mypy`.** Das ist der Lauf, der zählt —
  `.venv` hat numpy 2.4, der `lint`-Job hat 2.5, und die schärferen Stubs finden Dinge, die auf
  3.11 gar nicht auftauchen können. Vor einem Push gehört dieser Aufruf dazu, sonst findet die
  CI den Fehler vierzehn Minuten später
- Statische Seite bauen: `.venv\Scripts\python.exe scripts\build_site.py` (schreibt `site/`,
  ~29 MB, Laufzeit selbst gehostet), testen mit
  `.venv\Scripts\python.exe -m http.server 8833 --directory site --bind 127.0.0.1`

Es gibt keinen Build-Schritt. Die Oberfläche ist eine statische HTML/JS-Datei, kein npm.

## Stack

- Python 3.11 im lokalen `.venv` (nicht 3.14 — dafür fehlen OpenCV-Wheels). 3.13 ist auf diesem
  Rechner eine Karteileiche im py-Launcher, die Installation fehlt; **3.12.10 dagegen ist
  vorhanden** und trägt das zweite Venv.
- Zweites Venv `.venv312` auf Python 3.12, gitignoriert. Grund, gemessen und nicht vermutet:
  numpy 2.5 verlangt Python ≥ 3.12, also ist es in `.venv` nicht installierbar — und der
  `lint`-Job der CI läuft auf 3.12 und bekommt es. Seine schärferen Stubs haben zwei rote Läufe
  erzeugt, die auf 3.11 unsichtbar waren. Was `.venv` nicht sehen kann, sieht dieses hier.
- OpenCV, NumPy, Pillow für Bildverarbeitung; zxing-cpp für Decodier-Versuche auf Bildern
- pytest, ruff, mypy
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
- `src/qrsalvage/api.py` — was eine Schale fragt und was sie zurückbekommt: dict rein, reine
  JSON-Typen raus. Kennt kein HTTP. Server und Browser-Worker rufen dieselben Funktionen auf —
  daran hängt, dass ein Foto sich nicht anders verhält, je nachdem wie die Anfrage gereist ist
- `src/qrsalvage/server.py` + `web/` — lokale Oberfläche, nur auf 127.0.0.1; drei statische
  Dateien ohne Build-Schritt. `web/backend-server.js` und `web/backend-worker.js` sind zwei
  austauschbare Fassungen desselben Vertrags: welche als `backend.js` an ihrem Platz liegt,
  entscheidet, ob die Seite mit dem Server oder mit `web/worker.js` (Pyodide im Browser)
  arbeitet. Die Seite erfährt es nie
- `fixtures/` — synthetisches, öffentliches Korpus (`scripts/make_fixtures.py`)
- `fixtures-local/` — echte Fotos, gitignoriert, verlassen den Rechner nicht
- `tests/`, `scripts/` (Messwerkzeuge, kein Produktionscode)

Wohin das Projekt will und in welcher Reihenfolge: `docs/VISION.md` (Fahrplan mit
Begründungen). Wie es zu seinen Nutzern kommt und was das realistisch einbringt:
`docs/REACH.md` — dort steht auch, welche Maßnahmen bewusst unterbleiben. Technische
Einzelaufgaben: `docs/ISSUES.md`. Die englische Landkarte für
Beitragende — Datenfluss, Lesereihenfolge, Invarianten, Nahtstellen — ist
`docs/ARCHITECTURE.md` und wird bei Architekturänderungen mitgepflegt; die Messinstrumente
sind in `scripts/README.md` indexiert.

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
