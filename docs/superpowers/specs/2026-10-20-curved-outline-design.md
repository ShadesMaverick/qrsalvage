# Gekrümmten QR-Umriss von Hand markieren

## Ziel

Wenn die automatische Geometrie an einer abgerissenen Ecke oder einer stark gewölbten
Oberfläche scheitert, kann ein Mensch den äußeren QR-Umriss vorgeben. Diese Vorgabe steuert
das tatsächlich abgetastete Modulraster; sie ist keine rein grafische Markierung.

## Bedienung

- Nach einem fehlgeschlagenen Einzelbild-Lauf erscheint neben der vorhandenen Finder-Hilfe
  die Aktion **Mark the QR outline**.
- Der Mensch setzt vier Eckpunkte in fester, sichtbarer Reihenfolge: top left, top right,
  bottom right, bottom left. Eine zerstörte Ecke darf auf der vermuteten Position im noch
  sichtbaren Foto liegen.
- Nach dem vierten Punkt erscheinen vier Kanten-Anfasser: top, right, bottom, left. Jede Kante
  beginnt gerade und lässt sich über ihren Mittelpunkt zu einer quadratischen Kurve ziehen.
- Ecken und Kanten-Anfasser bleiben per Maus und Touch verschiebbar. Beim Verschieben einer
  Ecke wandern die beiden angrenzenden Kanten-Anfasser um den halben Versatz mit, damit die
  eingestellte Krümmung erhalten bleibt.
- **Recover with this outline** startet erst dann die Rekonstruktion. **Cancel** verwirft den
  manuellen Umriss.
- Der gezeichnete Umriss und spätere automatische Feinbewegungen bleiben echte Live-Geometrie.
  Erfolg, Fehler und ein neuer Lauf setzen veraltete Markierungen zuverlässig zurück.

## Geometriemodell

Die öffentliche Reihenfolge ist im Uhrzeigersinn:

1. `corners`: top-left, top-right, bottom-right, bottom-left
2. `edge_midpoints`: top, right, bottom, left

Intern verwendet der Kern weiterhin seine bestehende Eckenreihenfolge top-left, top-right,
bottom-left, bottom-right. Die vier Kanten-Anfasser werden in die vorhandenen acht
Bow-Parameter übersetzt: je ein `(x, y)`-Versatz für top, bottom, left und right. Der Anfasser
ist der tatsächliche Kurvenpunkt bei `t = 0.5`; die Kurve verwendet weiterhin den gemessenen
Term `4t(1-t)` und den vorhandenen Coons-artigen Übergang ins Innere.

Für jede mögliche QR-Version wird der vom Menschen gesetzte Umriss gegen die festgelegten
QR-Zellen bewertet. Die beste Version gewinnt. Nur dieser Gewinner erhält wie bisher die
teure automatische Bow-Feinabstimmung, diesmal ausgehend von den gesetzten Kurven statt von
vier geraden Kanten. Eine manuelle Vorgabe umgeht den externen Direktdecoder und darf nicht
gleichzeitig mit Finder-Punkten oder mehreren Fotos verwendet werden.

## API-Vertrag

`solve_payload` akzeptiert optional:

```json
{
  "outline": {
    "corners": [
      {"x": 10, "y": 20},
      {"x": 210, "y": 18},
      {"x": 218, "y": 222},
      {"x": 7, "y": 225}
    ],
    "edge_midpoints": [
      {"x": 110, "y": 12},
      {"x": 224, "y": 120},
      {"x": 112, "y": 232},
      {"x": 1, "y": 122}
    ]
  }
}
```

Beide Listen haben exakt vier endliche numerische Punkte. Ungültige, kombinierte oder für
mehrere Bilder eingereichte Vorgaben liefern ein englisches API-Fehlerobjekt und erreichen
den Kern nicht. Browser-Worker und lokaler Server verwenden unverändert denselben Vertrag.

Fortschrittsereignisse vom Typ `grid` tragen neben `corners` auch `edge_midpoints`. Dadurch
zeichnet die Oberfläche sowohl den manuellen Start als auch die echte automatische
Feinabstimmung.

## Grenzen

- Keine frei gezeichneten Splines und kein Kontrollgitter: genau ein Mittelpunkt je Kante
  entspricht dem bereits gemessenen Modell und begrenzt Überanpassung.
- Keine manuelle Mehrbild-Geometrie: verschiedene Fotos haben verschiedene Projektionen.
- Keine neue Abhängigkeit und kein Netzwerkzugriff zur Laufzeit.
- Die vorhandene Drei-Finder-Hilfe bleibt unverändert als einfacherer Weg erhalten.
- Alle neuen Code-Bezeichner, UI-Texte, Fehlertexte, Kommentare und Tests sind Englisch.

## Nachweis

- Rundlauf-Tests belegen die verlustfreie Übersetzung zwischen Kanten-Anfassern und Bow-Vektor.
- Ein synthetischer gekrümmter Fall belegt, dass ein manueller Umriss tatsächlich die
  abgetastete Posterior-Matrix verändert und die erwartete Nutzlast rekonstruiert.
- API-Tests belegen Validierung, Ausschlussregeln und identisches Verhalten des Worker-Vertrags.
- Webtests belegen die vier Eckpunkte, vier Kanten-Anfasser, Pointer-Bedienung, Kurvenzeichnung
  und den versendeten `outline`-Vertrag.
- Die vollständige Test-, Lint-, Typ- und statische Build-Suite bleibt grün.
