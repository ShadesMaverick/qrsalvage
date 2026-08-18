---
description: Liest einen schwer lesbaren QR-Code aus einem Foto aus - verwaschen, graviert, auf gewoelbter Flaeche, verschmutzt, zu wenig Kontrast. Verwenden, wenn ein Foto entschluesselt, geknackt, rekonstruiert oder nachgezeichnet werden soll.
argument-hint: <pfad-zum-foto>
---

Ziel: aus dem Foto `$ARGUMENTS` den Klartext gewinnen.

Das ist eine Eskalationsleiter. Eine Stufe wird erst betreten, wenn die vorige **nachweislich**
gescheitert ist — nicht, weil sie mühsam aussieht. Höhere Stufen kosten Zeit oder Aufmerksamkeit
des Nutzers, niedrigere kosten Rechenzeit.

## Grundsätze auf allen Stufen

- **Nie raten und weitergehen.** Eine Zelle, die du nicht sicher beurteilen kannst, ist `unbekannt`.
  Ein falsch geratener Wert verbraucht doppelt so viel Korrekturbudget wie ein Erasure.
- **Zwischenergebnisse nach `out/`** (gitignoriert). `fixtures/` wird nicht angefasst.
- **Das Bild verlässt das Projekt nicht.** Keine Online-Decoder, auch nicht "nur zum Vergleich".
- **Am Ende jeder Stufe berichten**, was versucht wurde und wie weit es kam: Finder gefunden?
  Timing-Pattern lesbar? Version bestimmt? Wie viele Zellen unsicher? Ein blankes "hat nicht
  geklappt" macht die nächste Stufe blind.

## Stufe 0 — das Werkzeug laufen lassen

```
.venv\Scripts\python.exe -m qrsalvage solve <bild> [--crop X0 Y0 X1 Y1]
```

Das ist der ganze erste Schritt. Findet das Werkzeug weniger als drei Finder, hilft ein enger
gesetzter `--crop` — die Findersuche verträgt Hintergrund schlecht.

**Nicht mit einem Vorverarbeitungs-Sweep anfangen.** Beim ersten gelösten Bild sind 5376
Kombinationen aus Kanal, CLAHE, Glättung, Schwelle und Morphologie ergebnislos durchgelaufen,
während der erste ernsthafte Geometrieversuch nahe an der Lösung war. Schlechte Codes scheitern
an der Geometrie, nicht am Kontrast. Ein Sweep lohnt erst, wenn die Findersuche selbst versagt —
dann geht es um die Frage, welcher Farbkanal das Muster überhaupt zeigt.

**Farbige Überlagerungen** (Filzstift, Hilfslinien, Stempel): gesättigte Pixel vorab per Skript
auf Mittelgrau setzen (nach `out/`, Original nie anfassen) — Mittelgrau, nicht Weiß, damit die
Zellen darunter unsicher statt hell werden. Es gibt dafür einen Schalter im Kern
(`preprocess.NEUTRAL_SATURATION_CAP`), aber er ships aus; die Messung, warum, steht in seinem
Docstring und `scripts/ab_marker.py`.

## Stufe 1 — die Zahlen lesen, die das Werkzeug ausgibt

Die Ausgabe ist eine Diagnose, kein Protokoll. In dieser Reihenfolge prüfen:

- **Versionstabelle.** Die gewählte Größe muss sich klar abheben. Liegen zwei Kandidaten dicht
  beieinander, sitzt das Gitter nicht — dann ist alles Weitere wertlos.
- **Bekannte Zellen falsch.** Unter 1 % ist gesund, über 5 % zeigt ein Geometrieproblem an.
  Diese Zahl ist die einzige, an der sich eine Verbesserung ehrlich messen lässt.
- **Timing-Güte.** Alles unter 100 % bedeutet Gitterversatz, auch wenn das Bild plausibel aussieht.
- **Unsichere Zellen** und **Decodier-Versuche.** Viele Versuche heißen: der Solver hat sich
  durchgetastet und es hat gereicht. Budget erschöpft heißt: zu viele echte Fehler.

Sitzt die Geometrie nicht, hier ansetzen und nicht an den Zellwerten. Ein um eine halbe
Modulbreite verschobenes Gitter erzeugt hunderte falsche Zellen und sieht dabei plausibel aus.

Neu in der Ausgabe: eine `featureless:`-Zeile heißt, das Werkzeug hat leere Flächen erkannt
(übermalt, abgerieben, Druck endet) und behandelt sie bereits als Erasures — das ist kein
Fehler, sondern Diagnose. Viele featureless-Zellen bei gleichzeitig erschöpftem Budget: prüfen,
ob die Fläche mehr Codewörter frisst, als das Korrekturniveau trägt (dann ist das Foto die
Grenze, nicht das Werkzeug).

## Stufe 1b — Finderzentren von Hand

Wenn die Versionstabelle durchweg schlecht fittet (alles über 5 %) oder die Findersuche ein
Artefakt gegriffen hat (drei „Finder" mit stark ungleichen Breiten in der Diagnose):

```
.venv\Scripts\python.exe -m qrsalvage solve <bild> --finders X1 Y1 X2 Y2 [X3 Y3]
```

Zwei Zentren genügen, wenn der dritte Finder zerstört oder außerhalb des Fotos ist — alle
geometrischen Lesarten des Paares werden dann gefittet und die bekannten Zellen entscheiden.
Grob geklickt reicht; die Zentren rasten auf das nächste echte Muster ein. Bei zerstörter
*Unterkante* (Finderpaar oben intakt, unten nichts): den dritten Punkt konstruieren und dabei
mehrere Abstände probieren (senkrecht unter dem ersten Punkt, Distanz mal 0,95 bis 1,06) —
die Bodenkante ist dann durch keine Strukturzelle festgelegt, und nur der Decode entscheidet
(siehe docs/ISSUES.md Nr. 9).

## Stufe 2 — unsichere Zellen beurteilen

Erst hier, wenn das Budget erschöpft ist. Der Solver tastet die unsichersten Zellen bereits von
allein ab, billigste Zweifel zuerst — bis dahin ist menschliches oder agentisches Urteil
verschwendete Mühe.

`out/grid.txt` enthält das Raster als `#`, `.` und `?`. Die Fragezeichen in Konfidenzreihenfolge
durchgehen, jede Zelle einzeln beurteilen. Die Entscheidungsregeln stehen in
`zellbeurteilung.md` — vor der ersten Zelle lesen.

Nach jeweils etwa zehn Entscheidungen neu decodieren lassen. Bei vielen offenen Zellen an den
`grid-reader`-Subagenten delegieren, sobald es ihn gibt — Dutzende Bildausschnitte im
Hauptkontext verdrängen alles andere.

## Stufe 3 — Mensch an die Oberfläche

Erst wenn Stufe 2 ausgereizt ist: den lokalen Server starten und den Nutzer bitten, die verbliebenen
Zellen in der Canvas-Oberfläche zu entscheiden. Ihm dabei sagen, wie viele Zellen offen sind und
wie viele davon die Lösung vermutlich braucht — nicht wortlos eine Oberfläche aufmachen.

## Abschluss

Bei Erfolg: den Klartext nennen, auf `out/sauber.png` hinweisen (der neu kodierte, normgerechte
Code — nicht die Rekonstruktion) und den Skill `add-fixture` vorschlagen.

Bei Misserfolg: festhalten, welche Stufe woran gescheitert ist. Ein Foto, das keine Stufe löst, ist
ein Befund über das Werkzeug — und der wertvollste Kandidat fürs Korpus.

Wenn ein Schadensbild neu ist, mit `qrsalvage synth` nachbauen und in
`scripts/difficulty.py` aufnehmen. Dann lässt sich die nächste Verbesserung beziffern, statt
auf das nächste Foto zu warten.
