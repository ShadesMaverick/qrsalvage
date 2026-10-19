# Vision und Fahrplan

Dieses Dokument hält fest, wohin qrsalvage will und in welcher Reihenfolge. Die technischen
Einzelheiten der Aufgaben stehen in `ISSUES.md`; hier steht, *warum* sie in dieser Reihenfolge
drankommen. Wie alles unter `docs/` richtet es sich an uns, nicht an Beitragende — deshalb
deutsch.

## Warum es dieses Werkzeug gibt

Etliche QR-Reader scheiterten am Pairing-Code einer Zigbee-LED-Lampe, weil der Code auf der
Wölbung sitzt. Diese eine Lampe ist der Gründungsfall, nicht die Marktgrenze. Die Zielgruppe sind
Menschen mit beschädigten QR-Codes auf Verpackungen, Tickets, Dokumenten, Schildern,
Inventaretiketten, Produkten und Geräten. Wer hier landet, hat ein akutes Problem und meist schon
mehrere Scanner erfolglos probiert. Smart-Home-Codes bleiben ein besonders sensibler Spezialfall.

## Wohin es soll

- **FOSS, öffentlich auf GitHub.** Apache-2.0; `LICENSE` und `THIRD-PARTY-NOTICES.md`
  liegen im Repo. Alle Abhängigkeiten sind permissiv — nichts steht einer Veröffentlichung
  oder Spendenfinanzierung im Weg. Warum nicht Codeberg: siehe unten.
- **Statische Browser-Version auf GitHub Pages, kein Anwendungsserver.** Die aktuelle Version
  läuft unter https://shadesmaverick.github.io/qrsalvage/; eine eigene Domain ist eine
  optionale spätere Maßnahme. Die Rechnerei läuft per Pyodide + zxing-cpp-WASM im Browser des
  Besuchers. Der Anwendungscode hat keinen Uploadpfad, der Build auditiert ausgelieferte
  Textressourcen auf unerklärte absolute URLs, und die CSP beschränkt programmgesteuerte
  Verbindungen auf denselben Ursprung. Gemeinsam tragen diese drei Ebenen die Privacy-Aussage.
  Ehrliche Kosten (~40–60 MB Erstladung, 2–5× langsamer) stehen in `ISSUES.md`.
- **Finanziert über Spenden, nicht über Daten.** Zielgröße ist der einmalige Fünfer im
  Rettungsmoment. Ko-fi/LiberaPay für Einmalspenden; Patreon höchstens zusätzlich — Abo-Logik
  passt nicht zu einem Werkzeug, das man einmal im Jahr braucht.
- **Edutainment als Haltung.** Die Live-Ansicht zeigt echte Zwischenstände des Verfahrens,
  die Methodenseite erklärt sie, beide verweisen aufeinander. Wer wartet, lernt nebenbei,
  warum es funktioniert. Nichts wird animiert, was nicht wirklich passiert.

### Warum nicht Codeberg (Entscheidung September 2026)

Codeberg war bis hierhin das Ziel, und der Wechsel ist keine Geschmacksfrage. Die
Mitgliederversammlung 2026 hat mit 358 zu 144 Stimmen eine Ergänzung der Nutzungsbedingungen
beschlossen (§ 2 (1) 7, seit Juli 2026 in Kraft): Projekte, die überwiegend aus Code
generativer KI-Werkzeuge bestehen, dürfen dort nicht geteilt werden — Claude ist im Text
namentlich als Beispiel genannt. Begründet wird es mit ungeklärtem Urheberrechtsstatus und
fehlenden Sicherungen gegen Schadcode; der begleitende Blogbeitrag nennt zusätzlich den
Ressourcenverbrauch von Projekten, die mehr Rechenzeit und Speicher verbrauchen, als die
beteiligten Menschen von Hand hätten erzeugen können.

qrsalvage fällt darunter. Die Historie trägt in jedem Commit `Co-Authored-By: Claude`, es gibt
keine Vor-LLM-Historie und keine Community — die beiden Ausnahmen, die Codeberg ausdrücklich
nennt, greifen beide nicht. Dass der Gründungsfall echt ist, die Fotos echt sind und jede
Erfolgsquote gemessen statt behauptet wurde, ändert daran nichts: Die Regel fragt nicht nach
der Sorgfalt, sondern nach der Entstehung.

Die Trailer aus der Historie zu entfernen, um die Regel zu unterlaufen, kam nicht in Frage.
Ein Projekt, dessen einziges Kapital die Nachprüfbarkeit seiner Aussagen ist, kann nicht mit
einer Fälschung anfangen. Also GitHub — dort gibt es keine solche Regel, die CI liegt ohnehin
schon als `.github/workflows/ci.yml` im Baum, und Pages kann die 29 MB der Browser-Version
ausliefern.

Was das kostet, gehört mitgeschrieben: GitHub gehört Microsoft, ist nicht quelloffen, und die
Datenschutzaussage der Seite muss ehrlich sagen, dass die Auslieferung dort stattfindet. Die
Kernaussage bleibt davon unberührt: Die Rechnerei läuft im Browser des Besuchers. Der
Anwendungscode enthält keinen Uploadpfad, der Build auditiert ausgelieferte Textressourcen auf
unerklärte absolute URLs, und die CSP beschränkt programmgesteuerte Verbindungen auf denselben
Ursprung. Keine dieser Ebenen beweist die Aussage allein; gemeinsam tragen sie, dass das Foto
nicht hochgeladen wird.

**Für den Launch-Post daraus die Konsequenz:** Die Entstehung wird offen genannt, nicht
verschwiegen. Offen vorgetragen und mit `scripts/` nachprüfbar ist sie haltbar; unerwähnt und
später entdeckt kostet sie genau die Glaubwürdigkeit, auf der `REACH.md` aufbaut.

## Die Spenden-Mechanik

Spenden sind keine Kaufentscheidung, sondern Reziprozität: Man gibt in den ersten dreißig
Sekunden nach einer Rettung. Der Hebel ist deshalb

**Rettungsquote × Reichweite × richtig platzierter Moment**

und nicht die Breite der Featureliste. Jede der folgenden Aufgaben zahlt auf genau einen
dieser drei Faktoren ein. Der Faktor Reichweite ist in `REACH.md` ausgearbeitet — samt der
Zahl, die realistisch dabei herauskommt.

## Fahrplan

In dieser Reihenfolge, jede Stufe für sich nutzbar:

- [x] **1. Kamera-Modus mit Bewegungs-Serie** *(Rettungsquote)* — „Halte die Kamera auf den
  Code und beweg sie langsam": Live-Vorschau per `getUserMedia`, automatisch 3–5 Frames
  greifen, direkt in `solve_many`. Die Fusion ist der stärkste gemessene Hebel
  (36–81 % einzeln → 93–100 % fusioniert), aber niemand macht von Hand drei Fotos — aus dem
  erklärungsbedürftigen Feature wird eine Geste. Läuft lokal auf 127.0.0.1 und öffentlich
  über HTTPS auf GitHub Pages.
- [x] **2. Konservative Payload-Intelligenz** *(Rettungsquote/Erlebnis)* — URL, Kontaktkarte,
  E-Mail, Telefon, SMS, Geo-URI, WLAN, Zigbee und Matter nur anhand ihrer eigenen Syntax
  erkennen. Alles andere bleibt Klartext; Produkt und Zweck werden nie geraten. Aufschlüsselung
  bleibt opt-in und lokal.
- [x] **3. Die Spendenkarte** *(Moment; URLs nachtragen, siehe ISSUES)* — der Ask auf der
  Erfolgskarte, klein, unter dem Klartext, zusammen mit der Privacy-Aussage: „Lief komplett auf
  deinem Gerät. QR-Code gerettet? 5 € halten das Werkzeug am Leben." Nicht auf der Startseite.
- [x] **4. Statische Seite — LIVE und im Browser verifiziert.** GitHub Pages liefert sie unter
  https://shadesmaverick.github.io/qrsalvage/ aus. `scripts/build_site.py` schreibt `site/`
  (29 MB, alle Assets selbst gehostet: Pyodide 0.28.0, NumPy 2.2.5, OpenCV 4.11,
  zxing-wasm 2.2.4, das eigene Wheel). Gemessen: Kaltstart unter 9 s über localhost, das
  schwere Fixture in **10,7 s** gelöst, 225 Live-Ereignisse, Exporte und Katalog-PDF entstehen
  im Browser. Jede einzelne Anfrage ging an den eigenen Host — im Server-Log samt der
  Worker-Ressourcen nachgewiesen. Anwendungscode ohne Uploadpfad, URL-Audit im Build und
  `connect-src 'self'` tragen die Privacy-Aussage gemeinsam. Der Weg dahin: `api.py` als
  transportneutrale Schicht, die Server und Worker gemeinsam aufrufen, plus die fertige
  Encode-Richtung des Orakels — gegen den nativen Encoder matrixgleich geprüft
  (`tests/test_oracle_bridge.py`). Vendoring, Encode-Bridge und Pages-Deployment sind damit
  abgeschlossen. Offen bleibt nur der echte Safari/iOS-Test; eine eigene Domain ist optional.
  Die Vorgeschichte: **Spike gelungen**
  (`spike/pyodide/index.html`): der unveränderte Kern löst die harte Fixture im Browser in
  **12,4 s** (nativ ~4 s, Faktor ~3 — im prognostizierten Band), Ladezeit CPython+NumPy+OpenCV
  ~4 s vom CDN, alle 225 Progress-Events flossen durch. Die Orakel-Naht (`core/oracle.py`)
  macht zxing-cpp austauschbar; die Sync/Async-Brücke läuft über JSPI (`run_sync`,
  Chrome 137+). **Worker-Ausbau erledigt**: die Rechnerei
  läuft im Module-Worker (Seite bleibt beweisbar reaktiv), und das Orakel wird über den
  synchronen embind-Aufruf von zxing-wasm gerufen — **JSPI ist raus aus dem Pfad**, die
  Safari-Blockade damit architektonisch beseitigt (Realtest auf Safari steht aus). Die damals
  offene Selbsthostung der Assets, Encode-Richtung und Pages-Veröffentlichung sind erledigt.
- [x] **5. Veröffentlichung auf GitHub** — erledigt: Übersetzung (kein Deutsch mehr in
  `src/`, `tests/`, `scripts/`), `CONTRIBUTING`, erfundene EUI64 im Test, und
  `web/legal.html` mit Impressum und Datenschutzerklärung, verlinkt aus der Fußzeile beider
  Seiten. Repository und Browser-App sind öffentlich; Rechtstext, Ko-fi-Link, README-Verweise
  und GitHub Pages sind eingerichtet. Ein echter Safari/iOS-Test bleibt offen.
- [ ] **6. Reichweite für konkrete Schadensfälle** — der ausgearbeitete Plan steht in
  `REACH.md`: Startseite auf allgemeine Suchintentionen drehen, sachliche Links in passender
  Troubleshooting-Dokumentation, echte Hilfe in Foren-Threads und anschließend je ein
  Launch-Post. Kernsatz: niemand sucht qrsalvage, alle suchen ihr Problem — wir werben nicht,
  wir liegen bereit.

Danach, bewusst nachrangig (verbreitert statt vertieft):

- [ ] RS-Blocktabellen über Version 10 hinaus — billig, eine Fleißstunde
- [ ] Mehrere Codes in einem Bild
- [ ] Data Matrix — die Symbologie-Grenze ist dokumentiert, der Aufwand groß

## Was bereits steht

Fusion mehrerer Fotos (`solve_many`, gemessen), gebogenes Gitter, Streumengen-Erasures,
A4-Katalog mit Titeln, Live-Ansicht mit Ereignis-Streaming, Methodenseite mit berechneten
Abbildungen, Lizenzfundament. Die Ereignisse sind transportneutral gebaut — die
Browser-Version konsumiert sie unverändert.

## Grundsätze, an denen jedes neue Feature gemessen wird

1. Hilft es im Rettungsmoment, oder verbreitert es nur die Liste?
2. Läuft es ohne Anwendungsserver — lokal auf 127.0.0.1 und statisch auf GitHub Pages?
3. Vertieft es die Rettung beschädigter QR-Codes, ohne unbelegte Universalversprechen?
4. Ist sein Nutzen messbar, bevor er behauptet wird?
