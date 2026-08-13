# Offene Aufgaben bis zur Veröffentlichung

Sechs Einträge, fertig zum Anlegen als GitHub-Issues, sobald das öffentliche Repository steht.
Anlegen jeweils mit:

```
gh issue create --title "<Titel>" --label "<Labels>" --body "<Text>"
```

Bewusst in einer Datei statt in sechs: Solange es kein Remote gibt, wäre ein Verzeichnis mit
Einzeldateien nur Verwaltung ohne Nutzen. Beim ersten Anlegen wandern sie nach GitHub und diese
Datei wird gelöscht.

---

## 1. Dokumentation und Code ins Englische übersetzen

**Labels:** `documentation`, `blocker`

Rund 2000 Zeilen. Bezeichner sind bereits englisch, betroffen sind Docstrings und Kommentare.

Sinngemäß übersetzen, nicht wörtlich. Der Wert dieses Codes steckt in den Begründungen — warum
über Geometrien gemittelt wird und nicht über Vorverarbeitungen, warum eine Auslassung halb so
teuer ist wie ein Fehler, warum „gültig" nicht „richtig" heißt. Eine maschinelle Übersetzung
zerstört genau diesen Teil.

Muss vor der ersten Veröffentlichung fertig sein — danach ist es ein Bruch für alle, die schon
geforkt haben.

**Fertig, wenn:** kein deutscher Text mehr in `src/`, `tests/`, `scripts/`; `CLAUDE.md` und die
Skills unter `.claude/` bleiben deutsch, die sind projektintern.

---

## 2. Lizenz, README und Beitragsleitfaden

**Labels:** `documentation`, `blocker`

- `LICENSE`: Apache-2.0. Kompatibel mit zxing-cpp (Apache-2.0), OpenCV (Apache-2.0), NumPy (BSD),
  Pillow (MIT-CMU). Die Patentklausel ist im Barcode-Umfeld die vorsichtigere Wahl.
- `README.md`: Problem, Beispielbild, Installation, CLI-Nutzung, Messergebnisse.
- `CONTRIBUTING.md`: Entwicklungsaufbau, Testlauf, Hinweis auf das synthetische Korpus.

**Wichtig für das README:** Verwandte Werkzeuge offen nennen und abgrenzen, nicht verschweigen.
[QRazyBox](https://github.com/Merricx/qrazybox) (Open Source, manuelle Matrixeingabe),
[QR Photo Restore](https://www.hashitosystem.com/en/tools/qr-restore/) (automatisch, aber ohne
Quellcode und Lizenz), [EAN Check](https://eancheck.com/qr-code-recovery) (kommerziell).
Alleinstellung ist nicht die Kategorie, sondern: gewölbte Flächen, reproduzierbarer Benchmark,
offene und skriptbare Pipeline.

---

## 3. CI: ruff und pytest auf Linux, macOS, Windows

**Labels:** `infrastructure`

GitHub Actions, Matrix über die drei Systeme und Python 3.11 bis 3.13.

- `ruff check` und `ruff format --check`
- `pytest -m "not regression"` überall
- `pytest -m regression` mindestens auf Linux

Das Regressionskorpus ist synthetisch und liegt im Repository, läuft also ohne weitere
Vorbereitung. Laufzeit im Auge behalten: die Suite braucht derzeit rund 30 Sekunden.

---

## 4. Exportformate

**Labels:** `feature`

Der entscheidende Punkt kommt aus der eigenen Messung: Bei QR-Codes entscheidet die *physische*
Modulgröße über die Lesbarkeit, nicht die Bildauflösung. Rasterformate allein reichen deshalb nicht.

- **SVG** — vektoriell, zum Weitergeben
- **PDF mit Millimeterangabe** — `--size 40mm` muss 40 mm ergeben. Der einzige Weg, die
  Modulgröße verlässlich zu treffen
- **PNG** mit wählbarer Auflösung
- **JSON** — Nutzlast, Version, Fehlerkorrekturstufe, Maske, falsch abgetastete Zellen, Zahl der
  Reparaturen. Also auch, wie sicher das Ergebnis ist
- **HTML-Prüfbericht** — Foto, erkanntes Gitter, Kennzahlen, Ergebnis. Wer lange gesucht hat,
  will einen Nachweis, nicht nur eine Zeichenkette
- **Zigbee-Felder als JSON**, ausdrücklich opt-in: EUI-64, Install-Code, CRC-Prüfung. Schreibt
  ein Kopplungsgeheimnis in eine Datei, darf also nie Voreinstellung sein

---

## 5. Grafische Oberfläche

**Labels:** `feature`

Eine einzelne HTML-Datei mit Canvas, ausgeliefert von einem lokalen Python-Server. Kein npm,
kein Build-Schritt.

Der ursprüngliche Zweck — Zellen von Hand nachzeichnen — hat sich durch die Messungen erledigt,
das erledigt der Solver. Der verbliebene Zweck ist **Erreichbarkeit**: Foto hineinziehen,
Ergebnis bekommen, ohne ein Venv aufzusetzen.

- Drag-and-drop, Ergebnis mit Kennzahlen
- Manuelle Gitterkorrektur als Notausgang, wenn die Findersuche versagt (drei Finderzentren
  plus vierter Punkt anklicken)
- Downloads der Exporte aus Nr. 4

---

## 6. Streuung innerhalb der Zelle als zweite Unsicherheitsquelle nutzen

**Labels:** `bug`, `research`

Beobachtet an einem synthetischen Fall (`QRSALVAGE-SELFTEST-0815`, Kontrast 0.20, Wölbung 0.30,
Startwert 1): Gitter perfekt, **null** falsche bekannte Zellen, Timing 100 %, **null** unsichere
Zellen — und der Code decodiert trotzdem nicht. Reed-Solomon findet mit 7 Auslassungen nur
gültige, aber unlesbare Lösungen.

Ursache: Die bekannten Zellen liegen an den Rändern und Ecken. Sind ausgerechnet die sauber,
schätzt `estimate_levels` die Streuung zu klein, und die Datenzellen in der Mitte bekommen eine
Sicherheit, die sie nicht verdienen. Der Solver hat dann nichts zum Antasten.

Ansatz: `sample_cells` berechnet bereits die Streuung *innerhalb* jeder Zelle und wirft sie weg.
Sie ist von der Anpassung an die bekannten Zellen unabhängig und würde genau dort Unsicherheit
melden, wo das aktuelle Modell blind ist.

**Fertig, wenn:** die Erfolgsquote in `scripts/schwierigkeit.py` messbar steigt — nicht, wenn der
Einzelfall durchgeht.
