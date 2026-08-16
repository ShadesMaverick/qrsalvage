# Offene Aufgaben bis zur Veröffentlichung

Einträge, fertig zum Anlegen als GitHub-Issues, sobald das öffentliche Repository steht.
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

## 3. CI: ruff und pytest auf Linux, macOS, Windows — ERLEDIGT

**Labels:** `infrastructure`

`.github/workflows/ci.yml`: Lint über den ganzen Baum, schnelle Suite auf Linux 3.11–3.13 plus
macOS und Windows, Bildkorpus auf Linux, dazu ein Job, der ein Wheel baut und **außerhalb des
Quellverzeichnisses** installiert. Der letzte hat beim Schreiben gleich einen echten Fehler
aufgedeckt: Die Oberfläche wurde relativ zum Repo-Wurzelverzeichnis gesucht und war gar nicht
als Paketdaten deklariert — ein Wheel hätte keine Seite enthalten.

**Noch offen:** `<owner>` im CI-Badge des README ersetzen, sobald das Repository existiert.

---

## 4. Exportformate — ERLEDIGT

Gebaut in `src/qrsalvage/export.py`, Aufruf `--export svg pdf json html --size-mm 40`.
SVG und PDF tragen eine echte Millimeterangabe, das PDF ist von Hand geschrieben statt mit
einer Bibliothek — ein QR-Code ist eine Seite schwarzer Rechtecke. Zigbee-Felder nur mit
`--zigbee`.

<details><summary>ursprüngliche Beschreibung</summary>

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

</details>

---

## 5. Grafische Oberfläche — ERLEDIGT

**Labels:** `feature`

Gebaut: `src/qrsalvage/server.py` und `src/qrsalvage/web/index.html`, Aufruf `qrsalvage serve`. Nur auf
127.0.0.1, eine statische Datei, kein Build-Schritt. Drag-and-drop, Kennzahlen, Downloads,
und der Notausgang mit drei Klicks — der verträgt 45 px Ungenauigkeit, weil der Klick nur
den Kandidaten auswählt und die Position aus dem Bild kommt.

**Noch offen:** die Exporte aus Nr. 4 in der Oberfläche anbieten. Dort gibt es derzeit nur
PNG-Downloads, während die Kommandozeile SVG, PDF, JSON und HTML kann.

<details><summary>ursprüngliche Beschreibung</summary>

Eine einzelne HTML-Datei mit Canvas, ausgeliefert von einem lokalen Python-Server. Kein npm,
kein Build-Schritt.

Der ursprüngliche Zweck — Zellen von Hand nachzeichnen — hat sich durch die Messungen erledigt,
das erledigt der Solver. Der verbliebene Zweck ist **Erreichbarkeit**: Foto hineinziehen,
Ergebnis bekommen, ohne ein Venv aufzusetzen.

- Drag-and-drop, Ergebnis mit Kennzahlen
- Manuelle Gitterkorrektur als Notausgang, wenn die Findersuche versagt (drei Finderzentren
  plus vierter Punkt anklicken)
- Downloads der Exporte aus Nr. 4

</details>

---

## 6. Streuung innerhalb der Zelle als zweite Unsicherheitsquelle — ERLEDIGT

**Labels:** `bug`, `research`

Gebaut in `estimate_levels`: `sigma` ist jetzt ein Feld statt einer Zahl. Zwei Beiträge — die
Streuung der bekannten Zellen um ihr angepasstes Niveau, plus die interne Streuung jeder Zelle,
wobei nur der Überschuss über die Grundstreuung zählt (die das Punktraster ohnehin jeder Zelle
gibt).

Der auslösende Fall löst jetzt: aus 0 unsicheren Zellen und keinem Ergebnis wurden 1 unsichere
Zelle und ein Treffer, die Quote auf der Stufe stieg von 19/20 auf 20/20.

<details><summary>ursprüngliche Beschreibung</summary>

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

**Fertig, wenn:** die Erfolgsquote in `scripts/difficulty.py` messbar steigt — nicht, wenn der
Einzelfall durchgeht.

</details>

---

## 7. Neu aufgekommen

**Labels:** `enhancement`

- **Härtung und Performance — DURCHGANG ERLEDIGT (August 2026).** Server: Host-Header-Prüfung
  gegen DNS-Rebinding (403 für fremde Hosts, getestet), CSP mit Skript-Hashes statt
  `unsafe-inline` (Stolperfalle dokumentiert: der Browser hasht nach CR→LF-Normalisierung des
  HTML-Parsers, eine CRLF-Datei hasht auf Platte anders als im Browser), `nosniff`,
  `Referrer-Policy: no-referrer`, `frame-ancestors 'none'`; API-Antworten und Downloads mit
  `default-src 'none'`. Seite: systematisches Escaping aller Diagnosewerte; XSS-Beweis mit
  einem QR-Code, dessen Payload ein Injektionsversuch ist — erscheint wörtlich als Text.
  Performance (gemessen, `out/bench.py`-Methodik): render über repeat statt kron,
  `structure_mask`/Layout-Tabellen/Designmatrix/Pseudoinverse per lru_cache (eingefrorene
  Arrays, damit ein schreibender Aufrufer laut scheitert statt den Cache zu vergiften) —
  saubere Fixture 3,27 s → 2,66 s (−19 %), Probe-lastiges Echtfoto 6,92 s → 5,80 s (−16 %),
  Decode-Rundtrip −27 %. Noch offen fürs Pages-Deployment: CDN-Versionen pinnen bzw.
  selbst hosten (steht in der Browser-Restarbeit).

- **Kalibrierung der Posterior korrigieren.** Das Messwerkzeug gibt es jetzt
  (`scripts/calibration.py`, Rand und Mitte getrennt), und es hat die Frage verschoben. Befund:
  bei mildem und gleichmäßigem Schaden ist die Posterior praktisch perfekt kalibriert; bei
  lokalem Schaden (Fleck) lügt genau die Mitte (98,1 % richtig bei behaupteten ≥0,999, ECE 6,7×
  Rand). Die Fehlkalibrierung ist also räumlich, nicht global — ein Temperaturparameter, am
  ehrlichen Rand gefittet, käme als T ≈ 1 heraus und änderte nichts. Zwei räumliche σ-Terme
  (Beacon aus falsch lesenden bekannten Zellen, geglättete Nachbarschafts-Streuung) sind gebaut,
  gemessen und wirkungslos: Erfolgsraten in keinem Arm bewegt, ECE 0,0238 → 0,0233
  (`scripts/ab_sigma.py`; Gewichte stehen auf 0, Code und Protokoll in `sampling.py`).
  Vermutliche Ursache: der Blur reicht 1–2 Zellen weit, ein Fleck ist viele Zellen groß — das
  Innere bleibt für beide Terme unsichtbar. Nächste Kandidaten: größerer/mehrskaliger Blur oder
  ein echtes MRF über die Zellen. **Fertig, wenn:** die Erfolgsquote in `scripts/difficulty.py`
  oder die Mitte-ECE in `scripts/calibration.py` messbar besser wird.
- **Mehrbild-Fusion in der Oberfläche — ERLEDIGT.** Der Server nimmt `payload["images"]` als
  Liste (das alte `image` bleibt gültig), die Seite hat Mehrfachauswahl, Thumbnails mit
  Entfernen-Knopf und zeigt Übereinstimmung, strittige Zellen und aussortierte Fotos an. Der
  Fehlerfall bietet das Nachlegen weiterer Fotos aktiv an. Dabei zwei echte Fehler gefunden und
  behoben: die Handmarkierung übersprang die Auflösungskorrektur des automatischen Wegs
  (90 Sekunden Rechnen in ein falsches Gitter, jetzt 7 Sekunden ins richtige), und die
  Finder-Koordinaten wurden im Arbeitsbild statt im Originalbild gemeldet — die Ringe auf dem
  Foto saßen daneben, sobald intern skaliert wurde.
- **Kamera-Modus mit Bewegungs-Serie — ERLEDIGT.** „use the camera" in der Ablagezone:
  Live-Vorschau (`getUserMedia`, environment-Kamera, ideal 2560 px), ein Druck nimmt vier
  Frames über ~2 Sekunden, während die Hand driftet — direkt in `solve_many`. Im Katalogmodus
  ein Frame pro Druck. Taschenlampen-Knopf, wo der Browser sie hergibt; Stream wird beim
  Schließen freigegeben; verweigerte Berechtigung fällt freundlich auf den Dateiweg zurück.
  Ende-zu-Ende geprüft über einen gefälschten Kamera-Stream (Canvas mit driftendem Foto).
- **Payload-Intelligenz für die Smart-Home-Nische — ERLEDIGT.** `matter_fields` decodiert den
  Base38-Payload (Bitfelder, Verhoeff-Prüfziffer) und leitet den 11-stelligen manuellen
  Pairing-Code ab — verankert am kanonischen Matter-Testvektor (MT:Y.K9042C00KA0648G00 →
  3497-011-2332, Passcode 20202021, Discriminator 0xF00). `wifi_fields` parst WIFI:-Payloads
  samt Escaping. Die Seite zeigt Hinweis und Felder unter dem Klartext; im JSON-Export opt-in
  über `--split-payload` (`--zigbee` bleibt als Alias). Die echte EUI64 im Zigbee-Test ist
  durch eine erfundene ersetzt.
- **Der Spendenmoment — GEBAUT, wartet auf Konten.** Die Karte sitzt auf der Erfolgskarte
  (und nach dem Katalog-Download), mit Axolotl, Privacy-Satz und Knöpfen — und bleibt
  unsichtbar, solange keine URLs eingetragen sind. **Eintragen in `index.html`, Konstante
  `DONATE` ganz oben im Skript**, sobald die Konten existieren — PayPal.me zuerst (in Deutschland der vertrauteste Knopf; Ko-fi wickelt intern ohnehin über PayPal ab), dazu Ko-fi und LiberaPay. Bewusst nicht auf
  der Startseite: Reziprozität hat einen Moment.
- **Statische Browser-Version (Codeberg Pages + eigene Domain) — SPIKE ERLEDIGT.** Die Naht
  ist gebaut (`core/oracle.py`: zxing-cpp lazy, per `oracle.use()` austauschbar; der Kern
  importiert nachweislich ohne die Bindung — Test in test_solver.py). Der Spike
  (`spike/pyodide/index.html`, Anleitung im Dateikopf) löst die harte Fixture im Browser:
  **12,4 s solve** (nativ ~4 s), ~4 s Ladezeit für CPython+NumPy+OpenCV vom CDN, zxing-cpp-WASM
  0,2 s, Progress-Events laufen unverändert. Sync/Async-Brücke über JSPI (`run_sync`,
  Chrome 137+; Fallback für Browser ohne JSPI: der synchrone Emscripten-Build von zxing-cpp).
  **Worker-Ausbau erledigt** (`spike/pyodide/worker.js`): Module-Worker, Seite bleibt
  reaktiv (Tick-Zähler als Beweis), 12,1 s solve, alle Progress-Events live. **JSPI entfernt**:
  ein Warmup-Aufruf über den Wrapper fängt das voll-defaultete embind-Options-Objekt, danach
  ist jeder Decode ein synchroner `readBarcodesFromPixmap(ptr, w, h, options)`-Aufruf
  (~0,9 ms) — nichts mehr im Pfad, das Safari fehlt (Realtest auf Safari/iOS steht aus).
  **Mobile-Ehrlichkeit auf der Seite:** HEIC wird nicht mehr stumm verschluckt (Meldung; auf
  Safari clientseitige JPEG-Transkodierung), nach einem Erfolg startet ein neuer Drop frisch
  statt sinnlos anzuhängen, der Fehl-Verdict unterscheidet informations- von geometrie-tot
  (Gitter sauber über ≥3 Fotos → ehrlich „Module physisch weg" statt Falsche-Hoffnung-Schleife),
  und hart erkämpfte Erfolge (>100 Versuche) tragen die Aufforderung, den re-encodierten Code
  vor dem Eintippen mit dem eigenen Handy gegenzuscannen. Upload-Deckel auf 64 MB für
  Kamera-Serien. **Restarbeit:** Assets selbst hosten statt CDN (Versionen pinnen),
  Encode-Richtung bridgen (writeBarcode), Pages-Repo mit `.domains`, DNS CNAME auf
  `<user>.codeberg.page`. Lizenzseitig geklärt (`THIRD-PARTY-NOTICES.md`).
- **Mehrere Codes in einem Bild.** Ein Produktfoto mit zwei Etiketten liefert sechs oder mehr
  Finder-Kandidaten; wir suchen daraus genau ein Tripel und ignorieren den Rest.
- **Symbologie-Grenze dokumentieren.** `structure.py`, `layout.py` und `qrspec.py` sind die
  einzigen QR-spezifischen Module. Wenn Data Matrix je dazukommt, ist das die Grenze — sie
  gehört beschrieben, bevor jemand quer durchgreift.
- **Reed-Solomon über Version 10 hinaus.** Die Blocktabellen enden dort; größere Codes werden
  gelesen, aber nicht repariert.




