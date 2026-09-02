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

**Erledigt:** `.github/workflows/ci.yml` ist die CI, Badge und Clone-URLs zeigen auf das
GitHub-Repository. `.woodpecker.yml` ist entfallen — es fuhr dieselben Prüfungen für Codeberg,
und die Plattform ist seit September 2026 nicht mehr das Ziel (Begründung in `VISION.md`).

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
- **Browser und nativ können an Kippstellen verschieden entscheiden (beobachtet August
  2026).** Vier synthetische Aufnahmen desselben Codes (Kontrast 0,115, Wölbung 0,4, Fleck 0,4,
  Seeds 1/4/5/6): nativ verwirft die Fusion die Mitglieder 1 und 3, fusioniert 2 und **löst**;
  im Browser (Pyodide, WASM) verwirft sie nur ein Mitglied, fusioniert 3 und **scheitert**
  (Übereinstimmung 79 %, 90 strittige Zellen). Dieselben Bytes, derselbe Code, dieselbe
  Version — der Unterschied ist Fließkomma-Arithmetik der Plattform, die an einer knappen
  Verwerfungsschwelle in verschiedene Richtungen kippt. Die Architektur-Invariante „ein Foto
  verhält sich nicht anders, je nachdem wie die Anfrage reist" gilt transportseitig weiterhin
  (identischer Code in api.py), aber nicht bis in die letzte Nachkommastelle der Plattform.
  Einordnung: betrifft nur Fälle, die haarscharf an einer Schwelle liegen; klare Fälle
  entscheiden beide gleich. Denkbare Abmilderung: Schwellen mit Hysterese versehen oder die
  Verwerfung auf ganzzahlige Vergleichsgrößen stützen. **Fertig, wenn:** ein Regressionsfall
  existiert, der auf beiden Plattformen gleich entscheidet, oder der Unterschied als bekannt
  dokumentiert bleibt und die Fehlermeldung der Seite („mehr Fotos helfen") ihn ehrlich
  abdeckt — was sie heute schon tut.

- **Safari/iOS — statisch geprüft, UNGETESTET auf einem Gerät.** Ein Durchgang durch den
  Browser-Code gegen Safari-Verfügbarkeiten ergab genau einen echten Stolperstein, und der ist
  beseitigt: `worker.js` benutzte `OffscreenCanvas` (Safari 16.4) und `createImageBitmap`
  ausschließlich, um einen Aufwärm-Aufruf des Orakels zu ermöglichen — dessen Ergebnis nie
  jemanden interessiert hat. Jetzt tut es ein leeres `ImageData`; damit verlangt der Worker
  nichts Neueres als den Module-Worker selbst (Safari 15). In Chrome nachgeprüft: Orakel
  scharf, hartes Fixture in 11,7 s gelöst. Was der statische Blick *nicht* beantworten kann und
  nur ein Gerät klärt: ob iOS die Speichergrenze eines Tabs bei ~30 MB WASM plus NumPy/OpenCV
  hält. Der Kamera-Modus braucht einen sicheren Kontext, ist über eine LAN-Adresse per `http://`
  also nicht prüfbar — er wird erst mit dem HTTPS-Deployment testbar. **Stand August 2026: kein
  iOS-Gerät verfügbar, der Test ist nicht gelaufen.** Das ist die einzige Aussage über das
  Produkt, die derzeit unbelegt ist; sie gehört entsprechend zurückhaltend formuliert, solange
  das so bleibt. Wege, das zu schließen: ein fremdes Gerät, ein Gerätetest-Dienst im Browser,
  oder ein früher Nutzer, der berichtet. Der Taschenlampen-Knopf
  existiert auf iOS ohnehin nicht und blendet sich dort korrekt aus.

- **Statische Browser-Version — GEBAUT (August 2026).** `scripts/build_site.py` schreibt eine
  in sich geschlossene `site/` (29 MB): Pyodide 0.28.0 (Kern-Tarball, Teilmenge über
  `pyodide-lock.json` aufgelöst statt geraten), NumPy 2.2.5, OpenCV 4.11.0.86, zxing-wasm 2.2.4
  aus dem npm-Tarball, das eigene Wheel. Ein einziger Fremd-URL musste weichen: zxing-wasm holt
  seine `.wasm` per Default von jsDelivr — der Build patcht `locateFile` auf `import.meta.url`
  und bricht ab, falls das Muster beim nächsten Pin nicht mehr passt. Gemessen im Browser:
  Kaltstart unter 9 s über localhost, `engraved-curved-hard.png` in 10,7 s gelöst (nativ ~4 s),
  225 Live-Ereignisse, SVG/PDF/Katalog-PDF im Browser erzeugt. Alle 46 Anfragen same-origin,
  im Server-Log inklusive der Worker-Ressourcen gegengeprüft. CSP liegt als `<meta>` in der
  Seite, weil ein statischer Host keine Header setzt; `connect-src 'self'` macht die
  Privacy-Aussage erzwungen statt versprochen, `wasm-unsafe-eval` ist ihr Preis. Zwei
  Architekturstücke haben das getragen: `api.py` (transportneutral, Server und Worker rufen
  dieselben Funktionen) und die synchrone Encode-Richtung des Orakels — ohne die wäre die
  Browser-Version ein reiner Leser gewesen, weil jeder Erfolg re-encodiert und der ganze
  Katalog aus Re-Encodierungen besteht. **Offen:** GitHub Pages einschalten (Source: GitHub
  Actions, `.github/workflows/pages.yml`), echter Safari/iOS-Test.

  **Nachtrag September 2026, eine alte Behauptung hier war falsch:** An dieser Stelle stand,
  die Seite setze wurzelrelative Pfade und damit einen Domain-Root voraus. Nachgesehen: Die
  Seiten adressieren durchweg relativ (`style.css`, `method.html`, `legal.html`, `backend.js`)
  — die einzigen absoluten Verweise waren sieben `/method#…`-Links der Live-Ansicht in
  `app.js`, jetzt auf `method.html#…` umgestellt. Damit läuft die Seite unter
  `<user>.github.io/qrsalvage/` genauso wie unter einer eigenen Domain oder direkt vom
  Dateisystem. Der `fetch("/api/solve")` in `backend-server.js` bleibt absolut und muss es
  sein: den fährt nur der lokale Server, und der wohnt auf seinem eigenen Root.

- **Statische Browser-Version (GitHub Pages + eigene Domain) — SPIKE ERLEDIGT.** Die Naht
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
  Encode-Richtung bridgen (writeBarcode), GitHub Pages einschalten (Source: GitHub Actions,
  `.github/workflows/pages.yml`). Lizenzseitig geklärt
  (`THIRD-PARTY-NOTICES.md`).
- **Das Korpus löst unter OpenCV 5 — unbeabsichtigt gemessen (September 2026).** Der erste
  CI-Lauf auf GitHub hat wegen der `>=`-Untergrenzen in `requirements.txt` numpy 2.5.2,
  **opencv-python 5.0.0.93** und zxing-cpp 3.1.1 installiert, bei OpenCV also einen
  Hauptversionssprung von 4.11. Der `regression`-Job ist damit grün durchgelaufen: Das
  Bildkorpus löst unverändert. Das ist kein Freibrief — geprüft ist Linux/3.12 mit genau diesen
  Versionen, nicht die Kombinationsfläche —, aber es ist mehr, als das Projekt vorher über
  seine Robustheit gegen die Bildbibliothek wusste. Nebenbefund derselben Untergrenzen:
  numpy 2.5.2 hat den `lint`-Job zerlegt, weil sein Stub PEP-695-Syntax verwendet, die mypy
  gegen ein 3.11-Ziel nicht parsen kann; Ausweg und Preis stehen im Kommentar bei
  `python_version` in `pyproject.toml`.
- **Mehrere Codes in einem Bild.** Ein Produktfoto mit zwei Etiketten liefert sechs oder mehr
  Finder-Kandidaten; wir suchen daraus genau ein Tripel und ignorieren den Rest.
- **Symbologie-Grenze dokumentieren.** `structure.py`, `layout.py` und `qrspec.py` sind die
  einzigen QR-spezifischen Module. Wenn Data Matrix je dazukommt, ist das die Grenze — sie
  gehört beschrieben, bevor jemand quer durchgreift.
- **Reed-Solomon über Version 10 hinaus.** Die Blocktabellen enden dort; größere Codes werden
  gelesen, aber nicht repariert.

---

## 8. Abrisskante: ein Foto, drei Schwächen

**Labels:** `bug`, `research`

Ein Foto eines abgerissenen Ausdrucks (lokal: `fixtures-local/sample-torn-edge.jpg`; Klartext
bekannt, steht absichtlich nicht hier) scheitert auf Stufe 0 und hat beim Sezieren drei
getrennte Schwächen freigelegt. Das Schadensbild: Die Abrisskante verläuft direkt an der
linken Codespalte, ihr gewölbter Rand wirft einen weichen grauen Schattenstreifen in die
Ruhezone, und die Wölbung verschiebt die Module nahe der Kante — am stärksten unten links.
Als Synth-Achse nachgebaut (`tear` in `synth.py`, Achse in `scripts/difficulty.py`).

**Was die Synth-Achse leistet und was nicht — gemessen, nicht angenommen.** Sie reproduziert
das *Aussehen* des Schadens (Schattenstreifen an der linken Flanke, Wölbungsversatz zur Kante
hin), aber nicht den Fehlermechanismus des Fotos. Sie ist bimodal: bis `tear` 0,6 bleibt der
Fall harmlos (0 falsche bekannte Zellen), ab 0,8 zerstört der Streifen bei manchen Startwerten
die *Findererkennung* — statt drei Findern wird einer gefunden, die Zwei-Finder-Rekonstruktion
übernimmt, und die Versionswahl kippt von 29 auf 21. Das schmale Fenster, in dem das echte
Foto lebt — Finder intakt, Gitter um eine halbe Modulbreite verschoben — überspringt sie.
Folge: Die `tear`-Achse ist ein Instrument für Finder-Robustheit, **nicht** für (a) oder (b).
Wer (b) beziffern will, braucht den Wölbungsversatz ohne den Streifen als eigenen Parameter;
heute sind beide Hälften an `tear` gekoppelt.

**(a) Sigma-Explosion im Helligkeitsmodell — ERLEDIGT.** Das Gitter hing über die Papierkante,
eine Spalte „bekannt dunkler" Zellen maß helles Papier. Diese Ausreißer hebelten die zwei
quadratischen Niveaufelder, bis sie sich kreuzten; die Kontrastklemme lief auf ihr absolutes
Minimum (1e-6), die kontrastnormierten Residuen explodierten, `base_sigma` stand bei
2,9 Millionen — und die Posterior von 555 der 841 Zellen wurde zum Münzwurf, auf einem Bild
mit tadellosem Kontrast (Dunkel-Median 102, Hell-Median 197). Eine gesättigte
22-Erasure-Reparatur lieferte dann margenlos „gültige" unlesbare Ergebnisse. Gebaut in
`estimate_levels` (`ROBUST_LEVELS` in `sampling.py`): Ausreißer-Known-Cells fliegen iterativ
aus der Feldanpassung, der Kontrastboden ist ein Anteil des Median-Kontrasts statt eines
absoluten Epsilons, die Streuung kommt per MAD statt Standardabweichung.

**Die Messung, ehrlich gelesen** (`scripts/ab_robust.py`, 16 Bilder je Stufe und Arm): Auf
den synthetischen Achsen bringt die Änderung **nichts** — Kontrast (Kontrolle) 16/16, 16/16,
15/16 in beiden Armen; Fleck 14/14, 11→12, 8→9, also ein Bild von sechzehn auf zwei Stufen und
damit im Rauschen; `tear` 14/14, 14/14, 6/6, identisch. Wer diese Änderung als
Erfolgsquotensteigerung verkaufen wollte, hätte keine Belege.

Was sie tatsächlich bringt, ist die **Ehrlichkeit der Zahlen, die die Eskalationsleiter liest**:
auf dem Foto 555 → 37 unsichere Zellen, bei nie strittigem Kontrast (gelöst wird es dadurch
trotzdem nicht — siehe b und c). Eine auf 0,5 plattgedrückte Posterior zerstört zusätzlich die
Flip-Cost-Ordnung, das heißt der Solver vertastet sein gesamtes Budget in zufälliger
Reihenfolge. Die konstruierte Ausreißer-Matrix in
`test_lying_known_cells_cannot_flatten_the_posterior` geht von 775/841 unsicher auf 0. Und eine
konkrete Rettung: Der harte Fusion-Fall (Fleck 0,50, Gruppe 7) hatte vorher alle drei Fotos
einzeln scheiternd und löst jetzt aus einem Einzelbild — weshalb `test_fusion.py` einen
härteren Fall braucht (0,55, Gruppe 2).

**Der Preis, ebenfalls gemessen:** 2,4× so viele Niveau-Anpassungen auf einem sauberen Bild,
2,9× auf einem verfleckten, macht 40–50 % mehr Laufzeit. Grund: Der Ausreißer-Loop läuft
*innerhalb* der Gittersuche, wo die meisten Kandidatenplatzierungen zu Recht falsch sind und
darum voller „Ausreißer" aussehen. Die naheliegende Reparatur — robust erst verwerfen, wenn
das Gitter steht — verlangt, Suchpfad und finale Abtastung zu trennen; heute laufen beide
durch `geometry._score`. **Offen, lohnt sich besonders für die Browser-Version**, wo ein
Solve ohnehin bei ~10 s liegt.

**(b) Der Ecken-Descent rastet auf dem Schatten ein — ERLEDIGT.** Der Schattenstreifen liegt
genau dort, wo die linke dunkle Spalte der beiden linken Finder erwartet wird, und ist etwa
modultief; die Eckenjustierung findet mit ihrem feinen Startschritt (3 px) aus diesem lokalen
Optimum nicht heraus und lässt das Gitter eine halbe Modulbreite zu weit links sitzen — 19
von 244 bekannten Zellen falsch, gebündelt in Spalte 0 und der Alignment-Zone, Timing
trotzdem 100 % (es verläuft quer zum Versatz und merkt nichts).

Gebaut als `geometry.restart_coarse`, ausgelöst in `pipeline.solve`, sobald der Gewinner über
5 % falsche bekannte Zellen liegt (die Schwelle, die der Skill selbst als „Geometrieproblem"
liest). Übernommen wird das Ergebnis nur, wenn dieselbe Qualitätsfunktion, die der Descent
ohnehin optimiert, eine Verbesserung sieht — dieselbe Sicherheitsgarantie wie bei
`refine_bow`, festgenagelt in `test_the_coarse_restart_never_returns_a_worse_grid`.

**Die Ablation hat den ursprünglich geplanten Fix widerlegt** und ist der eigentliche Ertrag
dieser Aufgabe. Geplant war „grober Startschritt *und* die lügende Randspalte aus dem Zielmaß
nehmen". Gemessen am Foto, alle Arme an *allen* bekannten Zellen bewertet:

| Arm | falsche Zellen | löst |
|---|---|---|
| unverändert (Schritt 3, volles Zielmaß) | 19/244 | nein |
| Schritt 12 ab den **Startecken**, volles Zielmaß | 50/244 | nein |
| Schritt 3 ab den Startecken, Spalte 0 maskiert | 16/244 | ja |
| Schritt 12 ab den Startecken, Spalte 0 maskiert | 15/244 | ja |

Und dann, ab den **bereits justierten** Ecken statt ab den Startecken: Bei Schritt 3, 6 und 9
bleibt der Descent hängen, egal welche Randlinie maskiert wird; ab Schritt 12 retten **alle
vier** Randlinien das Bild gleich gut — auch die drei, die gar nicht beschädigt sind. Damit
war klar, dass die Maskierung nichts trägt. Der Test ohne jede Maskierung bestätigt es:
Schritt 12 ab den justierten Ecken, volles Zielmaß, ergibt 9 falsche Zellen, null unsichere,
Decodierung im ersten Versuch. Was zählt, ist die Kombination — erst behalten, was der feine
Descent gefunden hat, dann einen groben davon weglaufen lassen.

**Der Schritt ist in Modulen parametrisiert, nicht in Pixeln** (2 Modulbreiten). 3 px sind auf
einem Foto eine halbe Modulbreite und auf dem nächsten ein Fünftel; die Falle hat aber eine
Größe in Modulen, nicht in Pixeln. Auf diesem Foto misst ein Modul 6,2 px, die 12 px sind also
knapp zwei Module — 16 px und 24 px landen an derselben Stelle, es ist eine Schwelle zum
Überspringen, kein Wert zum Tunen.

**Ergebnis am Gründungsfall:** Das Foto besteht jetzt Stufe 0 durch die normale CLI. 19 → 10
falsche bekannte Zellen, 555 → 1 unsichere Zelle, ein einziger Decodier-Versuch statt 4001
vergeblicher. Als Regressionsfall gesichert (`fixtures-local/sample-torn-edge`, gitignoriert).

**Kein Rückschritt auf dem echten Korpus**, ein Zugewinn: Von acht lokalen Fotos lösen
weiterhin dieselben fünf, dazu neu das Abrisskanten-Foto. Die drei, die weiter scheitern,
scheitern an Dingen, die diese Eskalation nicht berührt, und sie feuert dort korrekt gar nicht:
`sample-curved-sheet` findet nur zwei Finder, `sample-engraved-brackets` (2/244 falsch) und
`sample-faint` (0/244 falsch) haben ein perfekt sitzendes Gitter und sind
informationslimitiert.

**Synthetisch bringt es nichts — in jeder einzelnen Stufe null Unterschied** (`scripts/ab_restart.py`,
16 Bilder je Stufe und Arm; die Zeitspalte des Laufs ist unbrauchbar, weil parallel echte Fotos
gelöst wurden):

| Achse | Stufe | ohne | mit | gefeuert |
|---|---|---|---|---|
| Kurvatur | 0,70 | 16/16 | 16/16 | 0 |
| Kurvatur | 0,85 | 0/16 | 0/16 | 16 |
| Kurvatur | 0,95 | 0/16 | 0/16 | 16 |
| Auflösung | 5,0 px | 11/16 | 11/16 | 0 |
| Auflösung | 4,5 px | 0/16 | 0/16 | 2 |
| Auflösung | 4,0 px | 0/16 | 0/16 | 2 |
| Abriss* | 0,80 | 14/16 | 14/16 | 1 |
| Abriss* | 1,00 | 6/16 | 6/16 | 7 |

\* Dieser Lauf ist älter als die Aufspaltung der Abrisskante in eine optische und eine
geometrische Hälfte **und** als die Umformung ihres Schattens vom Balken zur Penumbra. Er
beschreibt die Achse, wie sie damals war, nicht wie sie heute ist — behalten statt
wiederholt, weil der Befund, den er trägt (die Achse bricht über die Findererkennung), genau
der Anlass für beide Änderungen war.

Das ist eine Aussage über das Korpus, nicht über die Eskalation, und sie ist der eigentliche
Befund dieser Messung. Ein hängengebliebener Descent und eine nicht abbildbare Fläche sehen
beide wie ein schlecht sitzendes Gitter aus, aber nur das erste ist ein lokales Optimum. Starke
synthetische Wölbung ist das zweite: Keine Schrittweite erreicht eine Platzierung, die eine
Homographie nicht ausdrücken kann — darum feuert die Eskalation dort auf allen 16 Bildern und
hilft keinem. **Das synthetische Korpus enthält keinen Fall der ersten Art.** Die `tear`-Achse
sollte genau den liefern und verfehlt ihn, weil ihr Schattenstreifen die Findererkennung
zerstört, bevor er etwas einklemmt. Der einzige Beleg für diese Stufe ist damit das Foto, das
sie ausgelöst hat, und der einzige Schutz gegen ihr stilles Veralten ist dieses Foto im privaten
Korpus.

**Versucht, den fehlenden Fall zu bauen — und gescheitert. BLEIBT OFFEN.**

Zwei Änderungen an `synth.py`, beide sinnvoll und beide nicht ausreichend:

*Die Abrisskante ist jetzt zwei Parameter.* `tear` ist die optische Hälfte (der Schatten),
`curl` die geometrische (der Kantenversatz). Zusammen ergeben sie das Foto, einzeln lässt sich
messen, was jede Hälfte tut — was vorher unmöglich war und genau deshalb eine Fehlmessung
erzeugt hatte. Ein Test hält sie auseinander
(`test_the_two_halves_of_a_torn_edge_are_independent`), formuliert über eine formunabhängige
Invariante: Ein subtrahierter Verlauf kann ein Pixel nur dunkler machen, ein Versatz verschiebt
Kanten und hellt daher genauso viel auf, wie er abdunkelt.

*Der Schatten ist jetzt eine Penumbra.* Vorher ein dreieckiger Balken (Halbbreite 1,6 Module,
Zentrum 0,8 Module außerhalb der Kante) — sein Träger lief direkt über den äußeren Finderring
und zerstörte die Erkennung, bevor er irgendeine Geometrie täuschen konnte. Jetzt eine
Gaußsche Penumbra (σ 1,5 Module, Zentrum 1,5 Module außerhalb): Maximum außerhalb des Codes,
in die Finder reicht nur der Ausläufer. Gaußsch statt dreieckig, weil eine harte Kante selbst
ein Merkmal ist, an dem die Binarisierung sich festhält.

**Das hat die Findererkennung deutlich verbessert** — bei `tear` 1,0 überleben jetzt 6 von 6
Tripeln, wo der alte Balken bei manchen Startwerten einen statt drei Findern übrig ließ.
**Das Fenster trifft es trotzdem nicht** (6 Bilder je Zelle, Budget 2000):

| tear | curl | Finder | falsch (Median) | Zellen >5 % | ohne | mit Neustart |
|---|---|---|---|---|---|---|
| 0,8 | 1,5 | 5/6 | 2,5 % | 0 | 5/6 | 5/6 |
| 0,8 | 2,5 | 4/6 | 4,5 % | 0 | 6/6 | 6/6 |
| 0,8 | 3,5 | 0/6 | 5,3 % | 3 | 5/6 | 5/6 |
| 1,2 | 1,5 | 4/6 | 4,5 % | 1 | 6/6 | 6/6 |
| 1,2 | 2,5 | 1/6 | 5,3 % | 5 | 6/6 | 6/6 |
| 1,2 | 3,5 | 0/6 | 25,8 % | 4 | 2/6 | 2/6 |
| 1,6 | 1,5 | 0/6 | 8,2 % | 6 | 3/6 | 3/6 |
| 1,6 | 2,5 | 1/6 | 9,0 % | 3 | 3/6 | **2/6** |
| 1,6 | 3,5 | 0/6 | 25,0 % | 2 | 1/6 | 1/6 |

In **keiner** Zelle treffen „Finder intakt" und „Gitter über 5 % falsch" zusammen: Wo die
Fehlerrate die Schwelle überschreitet, ist die Findererkennung bereits auf 0–1 von 6 gefallen.
Der Neustart gewinnt nirgends — und verliert in einer Zelle ein Bild von sechs (fett). Das ist
bei n=6 im Rauschen und betrifft eine Zelle, in der die Finder ohnehin tot sind und die
Versionswahl damit haltlos, aber es ist genau der Fall, den `ab_restart.py` im Kopf hat: Die
Garantie gilt für das *Gitter* unter der Qualitätsfunktion, nicht für das *Ergebnis*, und hier
hat die Qualität einmal in die falsche Richtung gezeigt.

**Warum es strukturell schwer ist.** Eine Falle im Sinne eines lokalen Optimums braucht ein
Merkmal, das die quadratischen Niveaufelder *nicht* absorbieren können — also etwa modulbreit
und lokal. Genau so ein Merkmal überlappt zwangsläufig den Finderring. Umgekehrt ist ein
breiter weicher Verlauf, der die Finder schont, exakt das, was adaptive Schwelle und
quadratische Anpassung wegrechnen. Das echte Foto trifft das Fenster, weil sein Schatten beides
ist: weich genug für die Finder, lokal genug an der Codekante. Über die Schattenform allein ist
das synthetisch nicht erreichbar.

**Dritter Versuch: der Reststreifen — ebenfalls gescheitert, und zwar wie vorhergesagt.**

Die Idee war, den Attraktor nicht weiter zu formen, sondern woanders herzuholen: `remnant`
druckt einen stehengebliebenen Streifen des Nachbaretiketts in die Ruhezone — gleiche Presse,
gleiche Modulteilung, zwei Module breit, durch genau ein freies Modul vom Code getrennt. Der
Gedanke: Er berührt die Finder nicht und legt trotzdem Modulstruktur dorthin, wo die äußerste
Spalte eines verschobenen Gitters sonst weißes Papier findet.

Die Vorhersage wurde **vor** dem Lauf notiert und hat gehalten: Der Lichtspalt, der die Finder
rettet, nimmt dem Attraktor zugleich die Wirkung. Gemessen (6 Bilder je Zelle):

| remnant | curl | Finder | falsch (Median) | Zellen >5 % | ohne | mit Neustart |
|---|---|---|---|---|---|---|
| 0,0 | 0,0 | 6/6 | 0,0 % | 0 | 6/6 | 6/6 |
| 0,0 | 2,0 | 6/6 | 1,2 % | 0 | 6/6 | 6/6 |
| 0,0 | 3,0 | 6/6 | 4,5 % | 0 | 6/6 | 6/6 |
| 0,6 | 0,0 | 6/6 | 0,0 % | 0 | 6/6 | 6/6 |
| 0,6 | 2,0 | 6/6 | 1,6 % | 0 | 6/6 | 6/6 |
| 0,6 | 3,0 | 6/6 | 2,9 % | 0 | 6/6 | 6/6 |
| 1,0 | 0,0 | 6/6 | 0,0 % | 0 | 6/6 | 6/6 |
| 1,0 | 2,0 | 6/6 | 1,6 % | 0 | 6/6 | 6/6 |
| 1,0 | 3,0 | 6/6 | 2,9 % | 0 | 6/6 | 6/6 |

Keine Zelle überschreitet die Schwelle, keine löst schlechter, alle Arme identisch. Der
Streifen ist für die Pipeline schlicht nicht vorhanden.

**Warum diese Linie erschöpft ist.** Drei Versuche, drei Mal derselbe Wall: Die
Qualitätsfunktion sieht den linken Rand ausschließlich über die Finder — in den mittleren
Zeilen ist Spalte 0 Datenfeld und damit unbekannt, ein Attraktor dort bewegt nichts. Wirken
kann er nur neben einem Finder; steht er dort dicht genug, um zu wirken, verschmilzt er in der
Binarisierung mit dessen äußerem Ring und zerstört die Erkennung (Schattenbalken); hält man ihn
mit einem Spalt fern, bleibt er wirkungslos (Reststreifen); und ein Verlauf, der beides
umgehen soll, wird von adaptiver Schwelle und quadratischen Niveaufeldern weggerechnet
(Penumbra). **Ohne Änderung an der Zielfunktion selbst — etwa dass sie auch unbekannte Zellen
auf Modulraster-Kohärenz prüft — ist die Falle synthetisch nicht erreichbar.** Wer es erneut
versucht, sollte dort ansetzen und nicht am Schadensbild.

**Nebenbefund, unbeabsichtigt und positiv:** Die Pipeline ist von Modulraster-Störstruktur
direkt neben dem Code vollkommen unbeeindruckt — bei voller Streifenschwärze und einem Modul
Abstand bleiben Findererkennung, Versionswahl und Gitteranpassung unverändert. Das ist eine
Robustheitseigenschaft, die vorher niemand geprüft hatte, und `remnant` ist ab jetzt das
Instrument, das sie festhält.

Bis auf Weiteres gilt: Der grobe Neustart hat genau einen Beleg, und der ist ein Foto.

**(c) Der Bogen-Term kann Randversatz prinzipiell nicht ausdrücken — DOKUMENTIERT.** Seine
Beulen `4t(1-t)` verschwinden an den Rändern; das ist Absicht (Schutz gegen das Verbiegen der
unbeobachteten Mitte, siehe Docstring von `refine_bow`) und genau deshalb liegt der Versatz
einer gewölbten Abrisskante außerhalb seines Ausdrucksraums. Die Vermutung war, dass die Ecken
den Randversatz tragen können, wenn der Descent sie nur lässt — **durch (b) bestätigt**: Der
grobe Neustart bringt die Ecken dorthin, und der Bogen muss den Randversatz gar nicht
ausdrücken können. Kein Fix nötig. Sollte doch einmal ein Fall auftauchen, den die Ecken nicht
tragen, ist der nächste Kandidat das Alignment-Muster als vierter Anker, nicht eine weitere
Parametrisierung des Warps.





---

## 9. Unterkante ohne Anker: Becken aufzählen statt Zeugen suchen — ERLEDIGT

**Labels:** `enhancement`, `geometry`

Befund vom Foto einer abgeriebenen Gebrauchsanleitung (untere ~5 Modulreihen samt BL-Finder
weg, v4/33): Zwei Gitter treffen **beide 220 von 220 sichtbaren Strukturzellen fehlerfrei**
und lesen trotzdem 197 Datenzellen verschieden — nur eines decodiert. Die Lage der Bodenkante
ist bei zerstörter Unterkante durch keine einzige Strukturzelle festgelegt; der Kohärenzterm
allein trennt die Skalenhypothesen nicht (gemessen: Handkonstruktion mit Faktor 1,06 löst,
die senkrechte Konstruktion mit 1,00 nicht, beide sehen im Objective gleich gut aus).

Der aussichtsreichste Anker: **das Alignment-Muster.** Ab Version 2 sitzt es bei
(n-7, n-7) — beim genannten Foto Reihe 26 von 33, also *oberhalb* des zerstörten Streifens.
Ein 5x5-Muster mit festem Zentrum legt die Skala der Bodenkante fest, wo Finder fehlen.
Heutiger Ausweg auf der Eskalationsleiter: `--finders` mit drei Punkten, den dritten
konstruiert (so wurde das Foto gelöst). Zweiter Kandidat, falls das Alignment auch zerstört
ist: Skalenhypothesen (0,94–1,06) je durch die volle Decode-Kette schicken und den Decoder
entscheiden lassen — teuer, aber nur als Eskalation nach Fehlschlag.

**Nachtrag nach Vertiefung — die Alignment-Hälfte war falsch herum gedacht.** Beide Gitter
lesen das Alignment bereits fehlerfrei (es steckt längst in den bekannten Zellen und pinnt
beide bis Reihe 28); die Divergenz sitzt in der BR-Ecke (24 px in x), von Perspektive und
Kantenbogen an allen Zeugen vorbei gebogen. Ein zusätzlicher Alignment-Zwang hätte nichts
getrennt. Gebaut wurde deshalb der zweite Kandidat: der **Anchor-Sweep** in `pipeline.solve`
(`ANCHOR_SWEEP`), der nach Fehlschlag die Descent-Becken der konstruierten Drittfinder-Skalen
aufzählt und die billige Decode-Kette richten lässt — mit gedeckelter Erasure-Leiter
(`ANCHOR_ERASURE_CAP`), weil ein Richter über mehrere Geometrien sonst die mit der größten
Reed-Solomon-Freiheit gewinnen lässt statt die mit der Antwort (zwei so entstandene Fehltexte
in der ersten Messung, beide mit der Signatur „alle Prüfsymbole als Erasures verbraucht").
Messung in `scripts/ab_anchor.py`.

**Das Foto selbst bleibt offen und ist doppelt blockiert:** (a) sein richtiges Becken wird
nur von der 1,06-Konstruktion ab den *Handklick*-Zentren erreicht — ab den Detektorzentren
(TR 10 px daneben) erreicht es keine der Skalen, auch nicht mit grobem Neustart; (b) selbst
im richtigen Becken decodiert erst die handgesetzte Reihenmaske, weil der strukturierte
Abrieb (Nr. 10) konfident-falsche Zellen liefert. Es ist damit der Prüfstein für Nr. 10,
nicht mehr für diese Nummer.

**Fertig, wenn:** die worn-Achse bei 0,09+ messbar über die 9/16 des einzelnen Beckens
steigt, ohne dass der Sweep-Arm falsche Texte produziert (`scripts/ab_anchor.py`).

**Gemessen und erfüllt** (16 Bilder je Level und Arm, Budget 4000, vier Messrunden — die
ersten drei haben je einen Richterfehler aufgedeckt, Protokoll im Docstring von
`ANCHOR_WITNESS_CONFIDENCE`): worn 0,09: 9→11; 0,12: 9→11; 0,15: 10→10; 0,18: **4→10**;
Kontrolllevel identisch, **kein falscher Text in keinem Arm**. Der Zeugen-Richter („eine
unbestätigte Reparatur darf Stille füllen, aber keine konfident gelesene Zelle
überstimmen") hat dabei mehr getan als Erfindungen zu blocken: Nach einer Verwerfung sucht
der Sweep weiter, und ein Seed, der zuvor Byte-Müll lieferte, decodiert aus einem späteren
Becken korrekt.

---

## 10. Strukturierter Abrieb ist kein Featureless-Fall

**Labels:** `enhancement`, `sampling`

Dasselbe Foto, zweiter Befund: Der obere Rand des Schadstreifens ist kein leeres Papier,
sondern Restpigment mit Modulresten (Spalten 8–21 über drei Reihen, Konfidenzen 0,2–0,5).
Das Zählargument in `sampling.featureless_depth` kann solche Flächen prinzipiell nicht
markieren — sie *sind* nicht einfarbig. Ihre Zellen erreichen Reed-Solomon als konfidente
Fehler (doppelt so teuer wie Erasures). Ideen, beide ungemessen: lokale Kontrastkarte
(Fensterspannweite der means gegen den Feldkontrast) als zweite, von der Einfarbigkeit
unabhängige Verdachtsquelle; oder die bekannten falschen Strukturzellen als Beacons mit
größerem Radius als die gescheiterten 1,2-Zellen-Blurs (`BEACON_WEIGHT`, dort dokumentiert).

---

## 11. Winzige Codes mit Fremdkante: die 4,5-px-Klasse

**Labels:** `limits`, `documentation`

Produktfoto eines Bosch-Sensors: Code ~100 px im Bild (4,5 px/Modul), lasergraviert,
perspektivisch gekippt, eine Gehäusekante läuft durch die Codefläche. Gemessen: Hochskalieren
(2–6-fach, cubic und lanczos, drei Crops) bringt die Fehlrate nie unter 15,9 %, die
Versionswahl springt zwischen 21 und 37 Modulen. Unterhalb von etwa 5 px/Modul plus
Fremdstruktur ist die Information im Foto erschöpft — das gehört als ehrliche Grenze in die
Dokumentation (REACH/README), nicht in die Pipeline. Der richtige Rat an Nutzer: näher
fotografieren, mehrere Fotos, Fusion.

## 12. Performance-Audit: was die 36 Befunde wirklich wert waren — ERLEDIGT

Ein RepoLens-Lauf über die Domain `performance` hat 36 Befunde geliefert. Jeder wurde gegen
ein Profil geprüft, statt nach Plausibilität sortiert. Das Ergebnis in einem Satz: **kein
einziger Befund zielt auf `refine_corners` oder `estimate_levels`** — also auf die 90 % und
52 % der Laufzeit.

Gemessene Anteile, Korpus (alle sechs Bilder lösen beim ersten Kandidaten):

| Bereich | Anteil | Aufrufe |
|---|---|---|
| `refine_corners` | 90,2 % | 24 |
| `estimate_levels` (darin) | 52,1 % | 6073 |
| Findersuche, `uncertain_cells` | 0,0 % | 4 bzw. 2 |
| `ordered_search`, `repair_progressive`, `ensemble` | 0,0 % | **0** |

Auf schweren synthetischen Fällen (4001 Kandidaten, ungelöst): `refine_corners` 58–73 %,
`ordered_search` 5,7–16,3 %, `repair*` 4,1–6,7 %, `repair_progressive` 0,5–0,7 %.

**Umgesetzt.** Das Basisbild in `ordered_search` wird einmal gerendert und pro Kandidat nur an
den gekippten Modulen gepatcht (`_patch_module`); im selben Profil fiel `render` von 0,34 s auf
0,08 s, `ordered_search` von 1,37 s auf 1,11 s. Der Server deckelt gleichzeitige Recoveries auf
zwei (`WORKERS`). Im Browser gibt `zxDecodeSync` seine embind-Handles frei — bei bis zu 4000
Orakelaufrufen je Solve war das ein Heap, der nur wuchs —, das Wheel wird parallel zur
WASM-Initialisierung geladen, `ImageBitmap`s werden beim Verlassen von `loaded` geschlossen,
und der base64-Pfad läuft ohne Zeichenschleife.

**Abgelehnt, mit Messung.**

- *Serie parallel lösen.* Vier Recoveries in vier Threads brauchten **0,90×** der Zeit von vier
  nacheinander — der Abstieg ist Python-Arbeit unter dem GIL. Dazu ist die Schleife in
  `solve_many` ein Kurzschluss: das erste allein lösende Foto beendet den Aufruf.
- *Importe erst bei Bedarf.* `qrsalvage.cli` kostet 209 ms über 87 ms nacktem Interpreter,
  davon numpy 139 ms und cv2 170 ms inklusive numpy. Jeder Befehl braucht numpy, also spart
  Verzögern nur bei `--help`. Der Preis wäre, `FUSION_RULES` aus `ensemble.py` herauszulösen.
- *Findersuche, `uncertain_cells`, `repair_progressive`, `consensus_posterior`.* Zielen auf
  0,0 % bis 0,7 %. `consensus_posterior` gehört zum bildinternen Ensemble, das laut
  `ensemble.py` standardmäßig aus ist und als nutzlos vermessen wurde — ein Cache für Code, der
  nie läuft.
- *Statische Dateien bei jedem GET von der Platte.* Drei kleine Dateien über Loopback.

**Falsch.** Die Behauptung, nicht-Daemon-Threads hielten den Server nach Ctrl+C am Leben:
`ThreadingHTTPServer.daemon_threads` ist seit Python 3.7 `True`. Und die Meldung, dem CLI fehle
die Bildobergrenze des Web-Pfads, liest das Bedrohungsmodell falsch herum — die Web-Grenze
existiert, weil eine Anfrage von einer fremden Seite kommen kann.

**Was das über das Werkzeug sagt.** Performance-Linsen erkennen Muster — O(n²), fehlende
Caches, wiederholte Arbeit — aber sie wissen nicht, was oft läuft. Hier liegen 90 % der Zeit in
einem Koordinatenabstieg, an dem nichts falsch ist; er ist nur teuer. Der nächste echte Hebel
steht in Abschnitt 13.

## 13. Die Ausreißerschleife: der Deckel stimmt, die Begründung stimmte nicht — ERLEDIGT

`estimate_levels` verwirft Ausreißer und fittet neu, höchstens `ROBUST_ROUNDS` mal. Das Profil
liess es wie eine Performance-Frage aussehen: 85 % der Aufrufe auf einem schweren Foto
schöpfen jede Runde aus, Runden 2 bis 4 sind damit rund drei Viertel der teuersten Funktion.

**Was die Schleife wirklich tut.** Sie kann nicht oszillieren — jede Runde entfernt nur, nimmt
nie zurück. Sie spiralt: Ausreißer verwerfen verkleinert die Streuung, die kleinere Streuung
schiebt weitere Zellen über die Schwelle. Über 400 mitgeschnittene echte Eingaben mit Deckel 12
nachgespielt: 98,2 % kommen zum Stehen, aber der Median braucht 6–7 Runden, und die Stützmenge
fällt dabei von 203 auf rund 120 bekannte Zellen. Der Deckel bei 4 ist also ein Halt mitten in
der Spirale, keine Konvergenz — anders als der alte Docstring behauptete.

**Trotzdem der richtige Halt.** A/B auf der Fleck-Achse (Kontrast 0,13, Wölbung 0,50, 6 px,
`stain` 0,50; 30 Bilder je Zelle), Median der falschen Zellen:

| Runden | 1 | 2 | 3 | 4 | 6 |
|---|---|---|---|---|---|
| falsche Zellen | 16 | 9 | 7 | 7 | 6 |
| Sekunden | 370 | 346 | 380 | 418 | 479 |

Der Nutzen kommt bis Runde 3 und flacht bei 4 ab. Erfolgsquoten lagen in allen Armen in
überlappenden Wilson-Intervallen und tragen nichts bei. Bemerkenswert: **eine Runde ist
langsamer als zwei** — ein schlechterer Level-Fit gibt der Sonde mehr unsichere Zellen zu
durchsuchen. Runden zu streichen spart auf beschädigten Bildern also nicht einmal Zeit; die
Ersparnis zeigt sich nur auf sauberen, wo es nichts zu verwerfen gibt.

**Ergebnis:** `ROBUST_ROUNDS` bleibt 4. Die erhoffte Beschleunigung aus Abschnitt 12 existiert
nicht — der Weg zu weniger Laufzeit führt nicht über weniger Runden. Korrigiert wurde der
Docstring, der „converges in two or three rounds" behauptete. Instrument: `scripts/ab_rounds.py`.

**Zweimal falsch angesetzt, damit es nicht wiederholt wird.** Der erste A/B lief bei Kontrast
0,20 und `stain` 0,35: alles gelöst, falsche Zellen überall 0, kein Arm unterscheidbar. Der
zweite bei Kontrast 0,13 und `stain` 0,50: fast nichts gelöst, aber die Zellzahl trennte sauber.
Bei Änderungen an der Abtastung ist `wrong_known` der Messwert, nicht die Erfolgsquote — steht
so in `scripts/README.md` und hat zwei Anläufe gekostet.
