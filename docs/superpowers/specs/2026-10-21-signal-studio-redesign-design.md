# Signal-Studio-Redesign

**Datum:** 2026-10-21
**Status:** vom Nutzer in der visuellen Begleitung freigegeben

## Ausgangslage

qrsalvage ist technisch ungewöhnlich und leistungsfähig, wirkt in der derzeitigen Oberfläche
aber wie eine Ansammlung nachträglich ergänzter Elemente. Intro, Upload, Fortschritt,
Diagnostik, Export, Katalog und FAQ teilen sich eine lange Seite ohne ausreichend klare
Hierarchie. Die Oberfläche erklärt viel, inszeniert das eigentliche Werkzeug aber zu wenig.

Die neue Gestaltung verbindet zwei Referenzqualitäten, ohne eine davon zu kopieren:

- eine große, fotografische Produktbühne mit charaktervoller Typografie und viel Ruhe;
- eine präzise, modulare Arbeitsfläche, deren Farben echte Zustände und Werkzeuge markieren.

Der Nutzer hat dafür die Richtung **Signal Studio**, eine **adaptive Einzelbühne**, einen
**Easy/Pro-Umschalter**, automatische **DE/EN-Sprachauswahl** und das animierte Axolotl als
Begleiter gewählt. Das bestehende qrsalvage-Farbsystem bleibt erhalten.

## Ziele

1. Die Startseite soll innerhalb weniger Sekunden erklären, was qrsalvage rettet und dass
   Bilder das Gerät nicht verlassen.
2. Vor der Fotoauswahl soll die Marke eine große Bühne erhalten; danach soll sich dieselbe
   Bühne verdichten und dem Werkzeug Platz machen.
3. Gelegenheitsnutzer sollen mit wenigen klaren Entscheidungen zum Ergebnis kommen, während
   Fachnutzer die vorhandene Diagnostik vollständig erreichen können.
4. Alle Seiten sollen wie Teile desselben Produkts wirken.
5. Das Axolotl soll Orientierung geben und auf echte Zustände reagieren, statt nur dekorativ
   über der Oberfläche zu liegen.
6. Barrierefreiheit, Offline-Betrieb und die bestehende Verarbeitungslogik dürfen durch den
   Umbau nicht geschwächt werden.

## Nicht-Ziele

- Der Recovery-Kern, die API-Verträge und die Auswahl der Algorithmen werden nicht verändert.
- Easy und Pro liefern nicht unterschiedliche Ergebnisse.
- Es werden keine erfundenen Erfolgszahlen, Testimonials oder Beispielresultate ergänzt.
- Es entsteht kein Framework-, npm- oder Build-Schritt.
- Zur Laufzeit werden keine Fonts, Bilder, Skripte oder Analysedaten von fremden Hosts geladen.
- Der Ko-fi-Hinweis wird nicht vor einem erfolgreichen Ergebnis gezeigt.

## Visuelles System

### Farben

Die vorhandenen Tokens bleiben die Quelle der Wahrheit:

| Rolle | Token | Wert |
|---|---|---|
| Seitenhintergrund | `--bg` | `#1b252e` |
| angehobener Hintergrund | `--bg-lift` | `#232f3a` |
| Modulfläche | `--panel` | `#26333f` |
| Innenfläche | `--panel-in` | `#1f2a34` |
| Trennlinie | `--line` | `#37485a` |
| Primärtext | `--fg` | `#f2f4f5` |
| Sekundärtext | `--muted` | `#93a3b0` |
| Marke und Interaktion | `--pink` | `#f07ea3` |
| heller Interaktionsakzent | `--pink-soft` | `#f7b3c8` |
| Erfolg | `--ok` | `#8fd3b0` |
| Warnung | `--warn` | `#e0b356` |
| Fehler | `--bad` | `#e0644a` |

Die Bitwig-Anmutung entsteht durch Raster, Dichte, Zustandsleisten und Typografie, nicht durch
eine fremde orange Farbwelt. Farbe bleibt semantisch: Rosa ist keine Warnung, Mint kein bloßer
Schmuck und Fehler werden nie nur farblich mitgeteilt.

### Typografie und Geometrie

- Es werden ausschließlich lokale Systemschriften verwendet.
- Große Überschriften sind kompakt, geometrisch und deutlich skaliert; Fließtext bleibt ruhig
  und auf 65 bis 75 Zeichen begrenzt.
- Monospace bleibt Messwerten, Schritten und technischen Labels vorbehalten.
- Ein 4/8-Pixel-Raster steuert Abstände. Interaktive Ziele sind mindestens 44 mal 44 Pixel groß.
- Module haben wenige, konsistente Radien und eine gemeinsame Linien- und Elevationsskala.
- Sichtbare Fokuszustände bleiben erhalten; Hover ist nie die einzige Erklärung einer Aktion.

## Informationsarchitektur

### Gemeinsame Hülle

Startseite, Methodenseite und Rechtstext verwenden dieselbe kompakte Navigation mit Logo,
Studio, Methode, GitHub, Datenschutz und DE/EN. Easy/Pro erscheint nur dort, wo es die
Werkzeugdichte tatsächlich verändert. Die Navigation bleibt auf Mobilgeräten erreichbar,
ohne die Arbeitsfläche mit einer zweiten Navigationsebene zu überlagern.

### Startseite

Die Reihenfolge lautet:

1. adaptive Produktbühne;
2. Recovery-Studio;
3. drei verständliche Verfahrensschritte;
4. echte schwierige Anwendungsfälle;
5. Datenschutz und Open Source;
6. Footer.

Die derzeit doppelt hintereinander stehenden englischen und deutschen FAQ-Blöcke verschwinden.
Nur die aktive Sprache ist sichtbar und für assistive Technik Teil des Leseflusses.

### Methodenseite

`method.html` wird zum „Signal Manual“: eine kompakte Abschnittsnavigation, große vorhandene
Diagramme, klar getrennte Formeln und Textblöcke sowie dieselben Tokens wie das Studio. Die
fachliche Reihenfolge und die gemessenen Aussagen bleiben unverändert.

### Rechtstext

`legal.html` nutzt dieselbe Hülle, aber eine schmale, ruhige Lesespalte ohne Companion-Motion.
Der deutsche Text bleibt die maßgebliche Fassung. Eine englische Fassung wird ausdrücklich als
Übersetzung gekennzeichnet; Namen, Anschrift, Betreiberangaben und Pflichtlinks stammen aus der
deutschen Quelle und werden nicht abstrahiert oder templatisiert.

## Adaptive Einzelbühne

Die Seite besitzt einen expliziten UI-Zustand, der aus vorhandenen Ereignissen abgeleitet wird:

| Zustand | Bühne | Studio | Axolotl |
|---|---|---|---|
| `welcome` | groß | kompakte Fotoauswahl | ruhige Begrüßung |
| `preparing` | verdichtet | Boot-/Ladezustand | führt zur Statusanzeige |
| `recovering` | verdichtet | Foto und echte Pipeline-Schritte dominieren | wechselt zwischen passenden Ankern |
| `assistance` | verdichtet | Finder-, Ecken- oder Kantenhilfe | zeigt genau einen kontextuellen Hinweis |
| `success` | verdichtet | Payload und Export zuerst | kurze Feier, danach optional Ko-fi |
| `failure` | verdichtet | Ursache und nächster Versuch | verweist auf die konkrete Wiederherstellung |

„Start over“ setzt die Ansicht auf `welcome` zurück. Ein Bild nach einem Erfolg eröffnet wie
bisher eine neue Sitzung. Die Bühne wird nicht entfernt, sondern räumlich verdichtet; dadurch
bleibt die Marke sichtbar, ohne Wiederholungsnutzer auszubremsen.

Ein kleines, separat testbares UI-Modul übersetzt bestehende Backend- und Benutzerereignisse in
diese Zustände. Es enthält keine Recovery-Entscheidungen und verändert keine Requests.

## Easy und Pro

Der Modus ist ausschließlich eine Darstellungspräferenz und wird lokal gespeichert.

### Easy

- eine primäre Aktion je Zustand;
- verständliches Urteil vor Rohmesswerten;
- Diagnostik in einem kompakten Inspector;
- manuelle Finder-, Ecken- und Kantenwerkzeuge erst dann, wenn sie gebraucht werden;
- Exportgrundfunktionen sichtbar, seltene Optionen progressiv aufgeklappt.

### Pro

- dauerhafte Pipeline- und Sitzungsleiste;
- Live-Race, Posterior, unbekannte Module, Erasures und Suchläufe sichtbar;
- manuelle Geometriewerkzeuge direkt erreichbar;
- vollständige Export- und Katalogoptionen ohne zusätzlichen Einführungsdialog.

Der Wechsel ist jederzeit möglich, verliert weder Bild noch Markierungen und startet keine neue
Berechnung. DOM-Zustand und Requests bleiben gleich; CSS und UI-State entscheiden lediglich,
welche Erklär- und Diagnoseebene sichtbar ist.

## Sprache

Beim ersten Besuch gilt `navigator.languages`: Deutsch wird für `de` gewählt, sonst Englisch.
Der sichtbare DE/EN-Schalter überschreibt diese Wahl und speichert sie lokal. Ist Storage nicht
verfügbar, funktioniert die Auswahl für die aktuelle Seite weiter.

Ein gemeinsames statisches Sprachmodul stellt `t(key, values)` sowie die aktuelle Sprache für
alle Seiten bereit. Dynamische Meldungen in `app.js` verwenden Schlüssel statt eingebetteter
englischer Sätze. Längere redaktionelle Texte bleiben semantisches HTML mit klar getrennten
`data-lang`-Blöcken; Formeln, Bilder und Bedienelementstruktur werden nicht dupliziert.

Der Sprachwechsel aktualisiert `document.documentElement.lang`, Seitentitel, Metadaten soweit
im Browser sinnvoll, sichtbare Texte und zugängliche Namen. Er verändert keine Payloads und
sendet nichts nach außen.

## Axolotl-Companion

### Darstellung

Aus der vorhandenen Pixelmarke entsteht ein lokal ausgeliefertes, transparentes Sprite-Sheet
mit wenigen klaren Posen: idle, laufen, zeigen, prüfen und feiern. Es bleibt als qrsalvage-Mark
erkennbar. Das Sprite-Sheet wird eingecheckt und im Browser niemals extern nachgeladen.

Eine einzige Companion-Ebene bewegt das Sprite zwischen ausdrücklich im Markup gesetzten
`data-companion-anchor`-Punkten. Die Bewegung verwendet nur `transform` und `opacity`; die
Sprite-Frames laufen mit `steps()`. Ein `IntersectionObserver` wählt den relevanten Abschnitt,
statt jede Scrollbewegung mit Layoutmessungen zu verfolgen.

Auf Mobilgeräten liegen die Anker innerhalb der jeweiligen Module und die Wege werden kurz.
Der Companion bedeckt keine primäre Aktion, keinen Payloadtext und keine Canvas-Markierung.
Die Figur ist dekorativ und `aria-hidden`; nur ihre seltenen Hinweisblasen besitzen echten Text.

### Verhalten

- Hinweise erscheinen nur kontextuell und beim ersten relevanten Gebrauch.
- Dieselbe Hilfe wird nicht bei jedem Pipeline-Ereignis wiederholt.
- Hinweisblasen sind schließbar und blockieren die Bedienung nicht.
- Erfolg löst erst nach sichtbarer Payload eine kurze Feier aus.
- Danach darf höchstens einmal pro Browsersitzung ein sekundärer Ko-fi-Link erscheinen.
- Ko-fi bleibt ein normaler, bewusst angeklickter Link; es wird nichts von Ko-fi eingebettet.
- Fehler oder Misserfolg zeigen niemals einen Spendenhinweis.

Bei `prefers-reduced-motion: reduce` steht das Sprite am aktuellen Anker, Pfad- und
Frameanimationen entfallen und Erfolg wird statisch bestätigt. Zusätzlich kann die Bewegung
über eine zugängliche Einstellung dauerhaft reduziert werden.

## Komponenten und Dateigrenzen

Der Kern und die API bleiben unberührt. Die Webschale wird wie folgt aufgeteilt:

- `index.html`: semantische Seitenstruktur, Studio-Module und Sprachblöcke;
- `style.css`: gemeinsame Tokens, Shell, responsive Layouts und Motion-Fallbacks;
- `app.js`: bestehende Bild-, Kamera-, Recovery-, Katalog- und Exportorchestrierung;
- `studio-state.js`: reine Ableitung von Phase und Easy/Pro-Sichtbarkeit;
- `locale.js`: Sprachauswahl, Übersetzungen und Persistenz;
- `companion.js`: Companion-Zustandsautomat, Ankerwahl und Hinweisregeln;
- `outline-editor.js`: bleibt die reine Geometriehilfe;
- `method.html` und `legal.html`: Seiteninhalte in der gemeinsamen Hülle;
- `axolotl-companion.png`: lokales Sprite-Sheet.

Die neuen Skripte folgen dem vorhandenen Muster: IIFE plus eine kleine explizite
`window.qr…`-Schnittstelle und CommonJS-Export für reine Funktionen, damit Node-basierte Tests
ohne Browserframework möglich bleiben. Server-Allowlist, Paketdaten und `PAGE_FILES` werden
explizit ergänzt; es gibt weiterhin keinen Glob, Bundler oder npm-Schritt.

## Datenfluss

1. Foto-, Kamera- und Reset-Aktionen bleiben in `app.js`.
2. `app.js` meldet normalisierte UI-Ereignisse an `studio-state.js`.
3. Der abgeleitete Zustand setzt genau eine Phasenklasse und die zugänglichen Zustandsattribute
   auf der Seitenhülle.
4. `companion.js` erhält denselben normalisierten Zustand, wählt Pose, Anker und gegebenenfalls
   einen Hinweis, entscheidet aber nie über Recovery oder Fehlermeldungen.
5. `locale.js` liefert Texte für dynamische Zustände. Technische Payloads werden nicht übersetzt.
6. Easy/Pro wirkt auf Sichtbarkeit und Erklärungstiefe, nicht auf Backend-Anfragen.

Damit existiert weiterhin nur ein fachlicher Weg vom Foto zum Ergebnis.

## Fehler- und Sonderzustände

- Bestehende konkrete Fehlermeldungen bleiben die Quelle der Wahrheit; der Companion darf sie
  kürzen oder überdecken weder visuell noch semantisch.
- Kameraablehnung, nicht lesbare Dateiformate, Worker-Bootfehler, abgebrochene Läufe und
  Exportfehler behalten jeweils eine direkte nächste Aktion.
- Bei Reset oder abgelaufenen asynchronen Operationen darf kein alter Companion- oder
  Studiozustand wieder erscheinen; der bestehende Owner-Mechanismus bleibt maßgeblich.
- Unbekannte Sprachschlüssel fallen auf Englisch zurück und werden im Test als Fehler sichtbar.
- Fehlgeschlagener Storage-Zugriff wird abgefangen; die Bedienung bleibt für die Sitzung aktiv.
- Fehlendes Sprite oder deaktivierte Animation beeinträchtigt keine Funktion und lässt keinen
  unsichtbaren Klickfänger zurück.

## Barrierefreiheit und Responsive Design

- Alle primären Aktionen bleiben echte Buttons oder Links.
- Easy/Pro und DE/EN besitzen sichtbare Labels, `aria-pressed` oder passende Gruppensemantik.
- Die bestehende deduplizierte Live-Region bleibt für bedeutende Pipeline-Zustände zuständig;
  Companion-Bewegungen werden nicht vorgelesen.
- Fokus wird nach bedeutenden Übergängen sinnvoll auf Status, Fehler oder Ergebnis gesetzt,
  ohne während einer laufenden Interaktion zu springen.
- Geprüft werden mindestens 320, 375, 768, 1024 und 1440 Pixel sowie Mobil-Landscape.
- Textvergrößerung, Tastaturbedienung, grobe Zeiger und reduzierte Bewegung sind eigene
  Abnahmekriterien.

## Test- und Abnahmestrategie

### Automatisiert

- Reine Tests für Phasenübergänge, Moduspersistenz, Sprachfallbacks, Companion-Hinweisregeln
  und die einmalige Ko-fi-Regel über die vorhandene Node-Brücke in `pytest`.
- Servertests pinnen Skriptreihenfolge, statische Allowlist, ARIA-Verträge, Fokusziele,
  Reduced-Motion-Regeln und das Fehlen externer Laufzeitressourcen.
- Repository- und Buildtests stellen sicher, dass neue Dateien im Wheel und im statischen Build
  enthalten sind.
- Bestehende API-, Worker-, Geometrie-, Export- und Bildregressionstests bleiben unverändert
  grün.
- `scripts/build_site.py` muss die Selbständigkeitsprüfung ohne unerklärte URL abschließen.

### Visuell und manuell

- Zustände `welcome`, `preparing`, `recovering`, `assistance`, `success` und `failure` werden in
  Easy und Pro auf Desktop und Mobil geprüft.
- DE und EN werden mit langem Text, Browserneustart und fehlendem Storage geprüft.
- Tastatur, Screenreader-Reihenfolge, 200-Prozent-Textzoom und Reduced Motion werden geprüft.
- Ein öffentlicher Fixture-Fall durchläuft Fotoauswahl, Kurveneditor, Erfolg, Export und den
  einmaligen Ko-fi-Hinweis.
- Methodenseite und Rechtstext werden auf Lesbarkeit, Navigation und fehlenden horizontalen
  Überlauf geprüft.

## Veröffentlichung

Nach vollständiger lokaler Prüfung wird die statische Seite gebaut. Erst ein erfolgreicher
`main`-CI-Lauf darf Pages auslösen. Danach werden die Live-Dateien mit Cache-Buster gegen den
lokalen Build verglichen und die veröffentlichte Seite in Desktop- und Mobilbreite geprüft.
