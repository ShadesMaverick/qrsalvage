# Vision und Fahrplan

Dieses Dokument hält fest, wohin qrsalvage will und in welcher Reihenfolge. Die technischen
Einzelheiten der Aufgaben stehen in `ISSUES.md`; hier steht, *warum* sie in dieser Reihenfolge
drankommen. Wie alles unter `docs/` richtet es sich an uns, nicht an Beitragende — deshalb
deutsch.

## Warum es dieses Werkzeug gibt

Etliche QR-Reader scheiterten am Pairing-Code einer Zigbee-LED-Lampe, weil der Code auf der
Wölbung sitzt. Diese eine Lampe ist der Gründungsfall — und zugleich die Marktdefinition: Die
Zielgruppe sind Smart-Home-Nutzer mit Zigbee- und Matter-Geräten, gewölbten Lampen, winzigen
gravierten Etiketten, toten Hubs und gebraucht gekauften Geräten. Wer hier landet, hat ein
akutes Problem und meist schon drei Apps erfolglos probiert.

## Wohin es soll

- **FOSS, öffentlich auf Codeberg.** Apache-2.0; `LICENSE` und `THIRD-PARTY-NOTICES.md`
  liegen im Repo. Alle Abhängigkeiten sind permissiv — nichts steht einer Veröffentlichung
  oder Spendenfinanzierung im Weg.
- **Statische Browser-Version, eigene Domain, kein Server.** Codeberg Pages liefert Dateien,
  die Rechnerei läuft per Pyodide + zxing-cpp-WASM im Browser des Besuchers. Das macht die
  Privacy-Aussage wörtlich wahr: Es gibt keinen Server, der Fotos oder Klartexte sehen könnte.
  Plan und ehrliche Kosten (~40–60 MB Erstladung, 2–5× langsamer) in `ISSUES.md`.
- **Finanziert über Spenden, nicht über Daten.** Zielgröße ist der einmalige Fünfer im
  Rettungsmoment. Ko-fi/LiberaPay für Einmalspenden; Patreon höchstens zusätzlich — Abo-Logik
  passt nicht zu einem Werkzeug, das man einmal im Jahr braucht.
- **Edutainment als Haltung.** Die Live-Ansicht zeigt echte Zwischenstände des Verfahrens,
  die Methodenseite erklärt sie, beide verweisen aufeinander. Wer wartet, lernt nebenbei,
  warum es funktioniert. Nichts wird animiert, was nicht wirklich passiert.

## Die Spenden-Mechanik

Spenden sind keine Kaufentscheidung, sondern Reziprozität: Man gibt in den ersten dreißig
Sekunden nach einer Rettung. Der Hebel ist deshalb

**Rettungsquote × Reichweite × richtig platzierter Moment**

und nicht die Breite der Featureliste. Jede der folgenden Aufgaben zahlt auf genau einen
dieser drei Faktoren ein.

## Fahrplan

In dieser Reihenfolge, jede Stufe für sich nutzbar:

- [x] **1. Kamera-Modus mit Bewegungs-Serie** *(Rettungsquote)* — „Halte die Kamera auf die
  Lampe und beweg sie langsam": Live-Vorschau per `getUserMedia`, automatisch 3–5 Frames
  greifen, direkt in `solve_many`. Die Fusion ist der stärkste gemessene Hebel
  (36–81 % einzeln → 93–100 % fusioniert), aber niemand macht von Hand drei Fotos — aus dem
  erklärungsbedürftigen Feature wird eine Geste. Läuft auf 127.0.0.1 und später auf HTTPS.
- [x] **2. Payload-Intelligenz für die Nische** *(Rettungsquote/Erlebnis)* — Matter (`MT:…`)
  und WLAN (`WIFI:…`) zerlegen wie heute Zigbee, und nach der Rettung die Folgefrage
  beantworten: was ist das, und wo gebe ich es ein. Aufschlüsselung opt-in, Klartext bleibt
  lokal.
- [x] **3. Die Spendenkarte** *(Moment; URLs nachtragen, siehe ISSUES)* — der Ask auf der Erfolgskarte, klein, unter dem
  Klartext, zusammen mit der Privacy-Aussage: „Lief komplett auf deinem Gerät. Lampe
  gerettet? 5 € halten das Werkzeug am Leben." Nicht auf der Startseite.
- [ ] **4. Pyodide-Spike, dann statische Seite** *(Reichweite)* — erst die eine Unbekannte
  klären: pures Wheel + Minimalseite, eine Fixture im Browser lösen, Zeit messen. Dann
  Worker, Pages-Repo, `.domains`, DNS. Details in `ISSUES.md`.
- [ ] **5. Veröffentlichung auf Codeberg** — Übersetzung der Docstrings (ISSUES 1), README
  final, `CONTRIBUTING`, die echte EUI64 in `tests/test_export.py` durch eine erfundene
  ersetzen, Impressum + Datenschutzerklärung für die öffentliche Seite (trivial: „keine
  Datenerhebung, Verarbeitung im Browser").
- [ ] **6. Reichweite in der Nische** — Home-Assistant-Forum und r/homeassistant mit der
  Gründungsgeschichte („etliche Reader scheiterten an der Wölbung meiner Lampe, also…"),
  Show HN. Die Methodenseite und die Live-Ansicht sind der Glaubwürdigkeitsbeweis; die
  HA-Community hat eine belegte Spendenkultur.

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
2. Läuft es ohne Server — heute auf 127.0.0.1, morgen statisch im Browser?
3. Stärkt es die Smart-Home-Nische, oder verwässert es den Fokus?
4. Ist sein Nutzen messbar, bevor er behauptet wird?
