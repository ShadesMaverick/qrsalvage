---
description: Nimmt ein geloestes Foto in die Regressionssuite auf - Bild nach fixtures/, Erwartungsdatei schreiben, Suite pruefen. Verwenden, wenn ein QR-Code entschluesselt wurde und das Bild als Testfall erhalten bleiben soll.
argument-hint: <pfad-zum-foto> <id>
---

Nimmt das Foto `$0` unter der Kennung `$1` ins Korpus auf. Ohne Argumente: nach beidem fragen.
Die Kennung ist kurz, kleingeschrieben, mit Bindestrichen, und beschreibt die Quelle statt
durchzuzählen — `zigbee-bulb-e27`, nicht `foto3`.

## Reihenfolge

**1. Klartext reproduzieren, nicht erinnern.** Den Code aus dem Foto neu lösen und das Ergebnis
mit dem aus der Sitzung vergleichen. Ein Fixture, dessen Erwartung aus dem Gedächtnis stammt,
zementiert im Zweifel einen Fehler.

**2. Kollision prüfen.** Existiert `fixtures/$1.png` oder `fixtures/$1.json` bereits, hier
abbrechen und eine andere Kennung erfragen. Fixtures werden ergänzt, nie überschrieben — auch
nicht, wenn das Bild "eigentlich dasselbe" zeigt.

**3. Das Original kopieren**, nicht die vorverarbeitete Fassung. Der Testfall ist die schlechte
Aufnahme; ein bereits entzerrtes und geschwelltes Bild testet nichts.

**4. Erwartungsdatei `fixtures/$1.json` schreiben:**

```json
{
  "source": "Zigbee-Lampe E27, Lasergravur auf gewoelbter Kuppel",
  "expected_sha256": "<sha256 des Klartexts, hex>",
  "expected_prefix": "",
  "qr_version": 5,
  "ecc_level": "M",
  "solved_at_stage": 2,
  "solved_by": "agent",
  "difficulties": ["woelbung", "punktraster", "verschmutzung"],
  "added": "<YYYY-MM-DD>"
}
```

Der Klartext steht **als Hash** in der Datei, nicht im Klartext. Die Regression braucht nur den
Vergleich, und die Codes enthalten Geraete-Install-Codes. `expected_prefix` bleibt leer, solange
der Inhalt schuetzenswert ist; bei harmlosen Inhalten wie einer oeffentlichen URL darf dort ein
kurzer Anfang stehen, der die Fehlersuche erleichtert.

`solved_at_stage` ist die Stufe, die es tatsaechlich geloest hat — die wichtigste Zahl im Korpus.
Steigt sie ueber die Zeit, wird das Werkzeug schlechter.

**5. Suite laufen lassen:** `.venv\Scripts\python.exe -m pytest -m regression`

Das neue Fixture muss gruen sein, und die bestehenden muessen es bleiben. Faellt ein altes
Fixture dabei um, ist das ein Befund und kein Anlass, es anzupassen.

**6. Commit vorschlagen.** Nicht selbst committen. Der Klartext gehoert weder in die
Commit-Nachricht noch in eine Beschreibung.
