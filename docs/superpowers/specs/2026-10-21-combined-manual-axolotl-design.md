# Gemeinsame manuelle Geometrie und Axolotl-Markenfigur

## Ziel

Schwere QR-Fälle sollen jederzeit manuell vorbereitet werden können. Finderzentren und ein
gekrümmter Umriss dürfen gleichzeitig markiert werden und müssen sich im Rechenkern tatsächlich
ergänzen. Parallel erhält das Axolotl drei klar getrennte Rollen: statisches Logo, einmalige
Regenerationsszene im Hero und optionaler mitlaufender Begleiter.

Die bestehende automatische Rettung bleibt der Standardweg. Die manuelle Oberfläche ist ein
zusätzlicher, jederzeit erreichbarer Weg über denselben API- und Kernpfad; sie bekommt keine
eigene Decodierlogik.

## Verbindliche Randbedingungen

- Kern, CLI, lokaler Server und Browser-Worker verwenden weiterhin dieselben Funktionen.
- Eine QR-Zelle behält die drei Zustände schwarz, weiß und unbekannt.
- Bilder, Markierungen und Klartext verlassen das Gerät nicht.
- Zur Laufzeit gibt es keine neuen Netzwerkzugriffe.
- Es kommt keine neue Abhängigkeit hinzu.
- `fixtures/` wird nicht verändert oder überschrieben.
- Bezeichner, Kommentare, Ausgaben und Tests im Code bleiben Englisch; diese Spezifikation bleibt
  deutsch.
- Pixelkoordinaten heißen `(x, y)`, Modulkoordinaten `(row, col)`.
- Die Oberfläche bleibt vollständig DE/EN-lokalisiert, tastaturbedienbar und bei 320 CSS-Pixeln
  ohne Seitenüberlauf nutzbar.

## Ausgangslage

Die Oberfläche bietet Finder- und Umrisshilfe derzeit erst nach einer gescheiterten automatischen
Rettung an. Der Finderpfad startet nach dem dritten Punkt sofort einen Versuch und löscht damit die
Möglichkeit, anschließend den Umriss im selben Zustand zu ergänzen. Der Umrisspfad setzt seine
eigenen vier Ecken und vier Kantenmittelpunkte und ruft `solve(null, outline)` auf.

Der API-Vertrag verbietet die Kombination gegenwärtig ausdrücklich. Im Kern priorisiert
`_attempt()` den Umriss und verwirft in diesem Zweig die Finderpunkte. Eine rein optische
Zusammenlegung der Werkzeuge würde deshalb kein besseres geometrisches Ergebnis liefern.

Das bestehende Axolotl ist ausschließlich ein Companion-Sprite. Die Navigation zeigt nur den
Textnamen, und im Hero gibt es keine Markenanimation. Der aktuelle Bewegungsumschalter reduziert
Animation, schaltet aber nicht gezielt nur den Begleiter ab.

## Manueller Geometrie-Editor

### Einstieg und Zustände

Sobald genau ein Foto geladen ist, ist ein mindestens 44 × 44 CSS-Pixel großes Steuerelement
`Manual recovery` beziehungsweise `Manuell retten` sichtbar. Der Einstieg hängt nicht vom Ergebnis
eines automatischen Versuchs ab. Im Katalogmodus bleibt er deaktiviert, weil Markierungen immer zu
genau einem Foto gehören.

Der Editor besitzt zwei unabhängige Ebenen auf demselben Canvas:

1. **Finder:** zwei oder drei Mittelpunktmarkierungen in beliebiger Reihenfolge.
2. **Outline:** vier Ecken im Uhrzeigersinn ab oben links; nach der vierten Ecke entstehen vier
   Kantenmittelpunkte für oben, rechts, unten und links, die sich zu gekrümmten Kanten ziehen lassen.

Ein Werkzeugwechsel löscht keine Markierungen. Die aktive Ebene ist über Text, Farbe und
`aria-pressed` erkennbar; Farbe allein trägt keine Bedeutung. Jede Ebene besitzt `Undo` und
`Reset`. Ein gemeinsamer Abbruch verlässt den Editor, ohne automatisch eine Rettung zu starten.

Die Schaltfläche `Recover with hints` ist aktiv, sobald mindestens eine Ebene vollständig nutzbar
ist:

- zwei oder drei Finderpunkte: Finder-only;
- vier Ecken und vier Kantenmittelpunkte: Outline-only;
- beide Bedingungen: Combined.

Unvollständige Ebenen bleiben sichtbar und editierbar, werden aber nicht in die Anfrage
aufgenommen. Die Oberfläche nennt vor dem Start eindeutig, welche Hinweise verwendet werden.

### Eingabe

- Zeiger und Touch setzen Punkte und ziehen vorhandene Griffe.
- Die Tastatur setzt den aktuellen Punkt mit Enter, bewegt ihn mit Pfeiltasten und wechselt mit
  eindeutig beschrifteten Steuerelementen zwischen Werkzeug, Ebene und Griff.
- Finderpunkte und Umrissgriffe besitzen unterschiedliche Formen, Nummern und kontrastreiche
  Halos.
- Der Editor verändert weder Bitmapabmessungen noch Bildkoordinaten. CSS-Mindestgrößen skalieren
  nur die Darstellung; die Rückabbildung auf das Foto bleibt seitenverhältnistreu.
- Ein Sprachwechsel rendert Anleitung und Beschriftungen neu, bewahrt aber Werkzeug, Punkte,
  Griffe, Auswahl und Undo-Verlauf.

### Zustandsgrenze

Die manuelle Zustandslogik wird aus `app.js` in ein kleines browserreines Modul ausgelagert. Es
verwaltet aktive Ebene, Finderpunkte, Ecken, Kantenmittelpunkte, ausgewählten Griff und Undo-Stapel
als expliziten Zustand. Canvas, DOM und Backend bleiben Adapter um diesen Zustand. Dadurch können
Finder-only, Outline-only und Combined ohne Browser-Mocks als reine Zustandsübergänge getestet
werden.

## API-Vertrag

`solve_payload()` akzeptiert bei genau einem Bild künftig gleichzeitig:

```json
{
  "finder_points": [{"x": 10.0, "y": 12.0}, {"x": 90.0, "y": 13.0}],
  "outline": {
    "corners": [{"x": 4.0, "y": 5.0}, {"x": 98.0, "y": 6.0},
                {"x": 96.0, "y": 101.0}, {"x": 3.0, "y": 99.0}],
    "edge_midpoints": [{"x": 51.0, "y": 2.0}, {"x": 101.0, "y": 53.0},
                       {"x": 49.0, "y": 104.0}, {"x": 0.0, "y": 51.0}]
  }
}
```

Die vorhandene Validierung bleibt für beide Teilstrukturen erhalten. Combined ist weiterhin mit
mehreren Fotos und internen Ensemble-Modi unvereinbar. Fehlertexte unterscheiden fehlende,
ungültige und nicht kombinierbare Eingaben. API-Antwort und Fortschrittsereignisse melden, ob der
Gewinner aus `automatic`, `finders`, `outline` oder `combined` hervorging, ohne Klartext zu
protokollieren.

## Gemeinsame Geometrie im Kern

### Gemeinsames Koordinatensystem

Der Umriss bestimmt zunächst wie bisher Ausschnitt, Skalierung und die vorbereitete
`CurvedOutline`. Finderpunkte werden mit derselben Transformation in das Arbeitsbild überführt:

```text
working_x = (original_x - offset_x) * factor
working_y = (original_y - offset_y) * factor
```

Crop-Offsets werden genau einmal angewendet. Fortschrittsereignisse und Ergebnisfinder werden
weiterhin in die Koordinaten des vom Nutzer geladenen Fotos zurücktransformiert.

### Kandidaten

Im Combined-Pfad entstehen Kandidaten in einem gemeinsamen vorbereiteten Graubild:

1. `fit_outline()` liefert Kandidatengrößen und die vom Umriss gesetzte Kantenkrümmung.
2. Zwei Finderpunkte erzeugen wie bisher die diskreten möglichen dritten Finder; drei Punkte
   liefern die beste Orientierung. Kandidaten, deren Finderorientierung nicht innerhalb des
   markierten Umrisses liegt, werden verworfen.
3. Finderbasierte Rasterkandidaten übernehmen die aus den Umrissmittelpunkten berechnete
   anfängliche Kantenkrümmung, bevor die bestehende Bow-Verfeinerung läuft.
4. Der Outline-only-Kandidat bleibt als Fallback im Pool. Dadurch kann ein ungenauer Finderklick
   keinen ansonsten brauchbaren Umriss zerstören.
5. `choose_grid()` entscheidet weiterhin anhand der bekannten QR-Strukturzellen. Manuelle
   Hinweise ersetzen weder Strukturmasken noch das dreistufige Unsicherheitsmodell.

Damit ergänzen sich die Informationen tatsächlich: Der Umriss begrenzt Fläche und Krümmung;
Finder bestimmen Orientierung, Rastermaß und zusätzliche Startgeometrien. Es entsteht kein
zweiter Decoder.

### Widersprüche und Diagnose

Widersprüchliche Hinweise führen nicht zu einem stillen Zwangsfit. Unplausible kombinierte
Kandidaten scheiden aus, während die vollständigen Finder- und Umrisskandidaten im Pool bleiben.
Die Ergebnisdiagnose nennt den gewählten Ursprung und die Zahl verworfener kombinierter
Kandidaten. Ein kontrollierter Fehlschlag bleibt möglich, wenn keine Geometrie die bekannten
Strukturzellen ausreichend erfüllt.

## Axolotl-Markenfigur

### Logo

Die Textmarke erhält ein statisches, scharf gerastertes Axolotl-QR-Signet. Es enthält ein
erkennbares Finder-Motiv, bildet aber absichtlich keinen scannbaren QR-Code. Das Signet wird als
lokales SVG ausgeliefert, besitzt eine Textalternative über den Linknamen und erscheint auch auf
Methoden- und Rechteseite.

### Hero-Regeneration

Im Hero begrüßt das Axolotl Besucher neben einem festen, nicht scannbaren Pixelraster. Die Szene
läuft höchstens einmal pro Browsersitzung:

1. sichtbare Lücken und abgebrochene Rasterkante;
2. Axolotl reagiert mit einer kurzen Schwanz-/Kiemenbewegung;
3. fehlende Module wachsen in drei klaren Wellen nach;
4. das vollständige Markenraster rastet ohne Endlosschleife ein.

Die Szene verwendet ausschließlich lokales SVG, CSS und feste Modulzustände. Sie enthält weder
Nutzdaten noch einen Decoderaufruf. Bei `prefers-reduced-motion: reduce` oder aktivierter
Bewegungsreduktion wird unmittelbar das ruhige Endbild angezeigt.

### Optionales Digital-Pet

Der bestehende Companion wird als freiwilliges Digital-Pet weitergeführt. Ein eigener
`Companion on/off`-Schalter ist von der Bewegungsreduktion getrennt und speichert die Entscheidung
lokal. `Off` entfernt Begleiter, Sprechblasen und Companion-Anker vollständig aus Fokus- und
Zeigerreihenfolge. Logo und Hero bleiben sichtbar.

Bei aktiviertem Begleiter begrüßt das Axolotl einmal pro Sitzung freundlich, begleitet danach nur
relevante Zustände und verdeckt niemals Canvas, primäre Aktion oder Ergebnis. Hinweise bleiben
auch ohne Pet als gewöhnlicher UI-Text verfügbar. Ko-fi erscheint weiterhin ausschließlich nach
einer erfolgreichen Rettung und nie als Teil der Begrüßung.

## Lokalisierung und Barrierefreiheit

- Sämtliche neue Texte und ARIA-Namen existieren symmetrisch in Deutsch und Englisch.
- Alle sichtbaren interaktiven Ziele messen mindestens 44 × 44 CSS-Pixel.
- Der gemeinsame Editor ist vollständig per Tastatur nutzbar und besitzt eine kurze sichtbare
  Tastenhilfe.
- Statusmeldungen nennen aktive Ebene, gesetzte Punkte und nächste mögliche Aktion; eine
  `aria-live`-Region vermeidet redundante Ansagen bei jeder Pixelbewegung.
- Animationen besitzen keine blinkenden schnellen Wechsel, keine Endlosschleife und eine ruhige
  Alternative.
- Pet-Abwahl, Bewegungsreduktion, Sprache und Easy/Pro bleiben voneinander unabhängige
  Einstellungen.

## Fehlerbehandlung

- Manuelle Geometrie ohne Foto startet keinen Versuch.
- Combined mit mehreren Fotos oder Ensemble liefert einen konkreten, lokalisierten API-Fehler.
- NaN, unendliche oder weit außerhalb liegende Koordinaten werden an der API-Grenze abgelehnt.
- Teilweise Markierungen verlassen den Browser nicht.
- Ein Backendfehler bewahrt alle manuellen Markierungen, sodass der Nutzer korrigieren und erneut
  starten kann.
- Reset des Fotos löscht die zugehörige manuelle Geometrie; Sprach-, Pet- und
  Bewegungseinstellungen bleiben erhalten.

## Tests und Messung

### Automatisierte Verträge

- Reine Zustandsmodultests: Werkzeugwechsel, Finder 0–3, Outline 0–4, Midpoints, Undo, Reset,
  Localewechsel und Payload-Erzeugung.
- API-Tests: Finder-only, Outline-only, Combined, Multi-Image-Verbot, Ensemble-Verbot und
  Koordinatengrenzen.
- Kerntests: korrekte Hin- und Rücktransformation, zwei und drei Finder, gekrümmte Kanten,
  widersprüchliche Hinweise, Kandidatenfallback und Fortschrittsursprung.
- Browsertests: Maus, Touch, Tastatur, 320/375/768/1440 CSS-Pixel, Querformat, 200 Prozent Text,
  DE/EN, Easy/Pro, Reduced Motion und persistente Pet-Abwahl.
- Markenprüfungen: keine externen Requests, kein scannbarer Hero-Code, Hero höchstens einmal pro
  Sitzung und Logo/Hero bleiben bei ausgeschaltetem Pet sichtbar.

### A/B/C-Messung

Ein Messskript führt identische Fälle mit Finder-only, Outline-only und Combined aus. Es berichtet
pro Fall Erfolg, Kandidatenzahl und Laufzeit; Klartext wird nicht protokolliert. Combined darf
keinen Fall verlieren, den einer seiner vollständigen Einzelpfade löst, weil beide Einzelkandidaten
im Pool erhalten bleiben. Die Änderung gilt als fachlicher Gewinn, wenn Combined mindestens einen
zusätzlichen Fall löst; bei Gleichstand darf sie nur veröffentlicht werden, wenn die bestehende
Erfolgsquote unverändert bleibt und die zusätzliche Laufzeit ausdrücklich ausgewiesen wird.

Echte private Fotos bleiben unter `fixtures-local/` und werden nie committed. Öffentliche
Regressionserwartungen werden nur ergänzt, niemals überschrieben.

## Veröffentlichung

Die Änderung wird erst nach vollständiger Python-Suite, Ruff, beiden Mypy-Umgebungen, statischem
Site-Build, Browsermatrix, unabhängiger Codeprüfung und erfolgreichem GitHub-CI-/Pages-Lauf nach
`main` veröffentlicht. Danach werden die ausgelieferten Schlüsseldateien mit dem lokalen Build
verglichen und Finder-only, Outline-only sowie Combined auf der Live-Seite gerauchtestet.
