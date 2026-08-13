# Eine unsichere Zelle beurteilen

Gilt für Menschen wie für Agenten. Die Kachel zeigt die fragliche Zelle mit ihrer Umgebung; die
Frage ist immer nur: schwarz, weiß, oder unbekannt.

## Die Referenz ist immer lokal

Finder- und Timing-Pattern definieren, wie "schwarz" und "weiß" **in dieser Bildregion** aussehen.
Über ein Foto mit Glanzverlauf hinweg kann ein weißes Modul oben dunkler sein als ein schwarzes
unten. Vergleiche nie gegen einen globalen Mittelwert, sondern gegen die nächstgelegenen sicheren
Module.

## Was ein schwarzes Modul ausmacht

Bei Lasergravur ist ein schwarzes Modul kein Fleck, sondern ein Punktraster. Entscheidend ist die
**Punktdichte**, nicht die mittlere Helligkeit — ein grob gerastertes schwarzes Modul kann heller
messen als ein verschmutztes weißes. Und ein echtes Modul hat Kanten, die auf den Gitterlinien
liegen. Was über die Gitterlinie hinausläuft oder mitten in der Zelle ausfranst, ist kein Modul.

## Die vier häufigen Täuschungen

- **Glanzlicht** hebt eine ganze Region an. Wenn die Nachbarzellen ebenfalls untypisch hell sind,
  ist die Region verdächtig, nicht die Zelle. Dann gegen die lokalen Nachbarn schwellen, nicht
  gegen die Referenz von weiter weg.
- **Verschmutzung** senkt die Helligkeit flächig und sieht damit aus wie schwarz. Unterscheidbar
  über die Farbsättigung: die Gravur ist entsättigtes Grau, Schmutz und Vergilbung haben einen
  Farbton. Ein Fleck respektiert außerdem keine Gitterlinien.
- **Wölbung** staucht die Module zum Rand hin. Wenn die Kachel systematisch neben dem Gitter
  liegt statt zufällig, ist nicht die Zelle das Problem, sondern die Entzerrung — zurück auf
  Stufe 1, nicht weiter raten.
- **Nachbarschaft.** Durch die Maskierung enthält ein QR-Code kaum große einfarbige Flächen. Ein
  3×3-Block gleicher Farbe ist ein Warnsignal für einen Gitterversatz oder eine Fehlserie.

## Wann `unbekannt` die richtige Antwort ist

Immer dann, wenn die Begründung mit "vermutlich" oder "eher" beginnt. Reed-Solomon korrigiert
doppelt so viele Erasures wie Fehler: eine ehrliche Enthaltung kostet halb so viel wie ein
falscher Tipp. Der Solver probiert die offenen Zellen ohnehin durch — er braucht nur wenige davon,
und zwar die ehrlichen.

## Zwei Verbote

- **Nicht mehrere Zellen mit derselben Begründung auf einmal entscheiden.** Wenn eine Begründung
  für fünf Zellen taugt, beschreibt sie ein Bildproblem, keine fünf Modulwerte.
- **Kein Rückschluss aus dem erwarteten Inhalt.** Weder "das müsste eine URL sein" noch "der Code
  fängt sicher mit dem Herstellerpräfix an" darf einen Modulwert setzen. Genau dieser Kurzschluss
  erzeugt Ergebnisse, die decodieren und trotzdem falsch sind.
