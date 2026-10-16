# Weg zu mindestens 35 € im Monat

Stand: Oktober 2026. Das ist ein Experimentplan, keine Umsatzprognose. Das Ziel gilt erst als
erreicht, wenn mindestens 35 € netto in drei aufeinanderfolgenden Kalendermonaten eingegangen
sind. Klicks, Sterne und Absichtserklärungen zählen nicht als Umsatz.

Technischer Release-Stand: Das disjunkte synthetische Release-Panel auf Commit `dfaa6a8` lieferte
139 exakte Wiederherstellungen, 5 ehrliche Fehlschläge und keinen gültigen falschen Klartext in
144 Fällen (96,5 % exakt; Wilson-95-%-Intervall 92,1–98,5 %). Das ist Evidenz für genau diesen
Generator und dieses Panel, nicht für beliebige reale Etiketten. Bei null beobachteten Fehltexten
liegt die einseitige exakte 95-%-Obergrenze für ihre Fallrate noch bei 2,1 %; „kein Fehltext
beobachtet" ist daher keine Nullrisiko-Behauptung.
Die 144 Rohzeilen liegen unter `docs/evidence/benchmark-release-dfaa6a8.jsonl`
(SHA-256 `965fd6b4315323ca3f7d5861d50d4986ec364efa509187fa4dd3ff6f872b654e`).

## Was der Markt bereits sagt

Der allgemeine "kaputten QR-Code reparieren"-Markt ist besetzt und preislich schwierig: Semacode,
QR Repair und EAN Check bieten browserbasierte Wiederherstellung kostenlos an.[1][2][3] qrsalvage
sollte deshalb nicht als weiterer universeller QR-Reparierer auftreten. Sein belastbarer Vorsprung
ist enger: gewölbte und gravierte Gerätecodes, Mehrbildfusion, diagnostizierte Unsicherheit,
Smart-Home-Payloads und nachvollziehbare Messungen.

Diese Nische hat einen konkreten Arbeitsablauf. Einige Bosch-Geräte benötigen den langen Inhalt
des QR-Codes als Zigbee-Install-Code; die nebenstehende Kurzfassung reicht ausdrücklich nicht.[4]
Der Nutzer braucht also nicht irgendeinen scannenden Code, sondern den exakten Klartext und die
richtige Anleitung für den nächsten Schritt.

Neben Privatnutzern gibt es zwei plausible Multiplikatoren:

- Repair-Cafés und Reparaturinitiativen. Das deutsche Netzwerk nennt mehr als 1.500 Initiativen;
  sie arbeiten typischerweise kostenlos oder gegen freiwillige Spenden.[9] Das ist ein guter
  Verbreitungskanal, aber kein guter Direktkunde.
- Refurbisher und gewerbliche Geräteaufbereiter. Refurbished-Angebote sind bekannt; in einer
  repräsentativen Fünf-Länder-Studie hatten 25 % der Befragten in Deutschland bereits ein
  refurbished Smartphone gekauft.[5] Das belegt einen professionellen Wiederverwendungsmarkt,
  aber noch nicht dessen Zahlungsbereitschaft für QR-Rettung.

Kommerzielle Barcode-SDKs verkaufen schwierige Erkennung, Offline-Betrieb und Support als
Unternehmensleistung; Dynamsoft lizenziert genau diese Klasse kommerziell und schließt Support
und Wartung ein.[8] Daraus folgt eine klare Trennung: Die freie Browser-App bleibt kostenlos und
privat. Bezahlt werden können Hilfe, Stapelarbeit, Integration und reproduzierbare Dokumentation,
nicht ein künstlich verschlechterter Kern.

## Erlösmodell

### 1. Freiwillige Rettungs-Spende

Nach einem Erfolg bleibt der konkrete 5-€-Hinweis. Ko-fi ist der erste Weg. Auf dem kostenlosen
Tarif können einmalige Trinkgelder ohne Ko-fi-Plattformgebühr laufen; Zahlungsabwicklungsgebühren
bleiben.[6] Liberapay eignet sich später für wiederkehrende FOSS-Unterstützung und nimmt selbst
keinen Anteil, ist aber für den einmaligen Rettungsmoment weniger direkt.[7]

Messziel: 8 Netto-Spenden zu durchschnittlich 4,40 € pro Monat ergeben rund 35 €. Das ist nur bei
hinreichendem qualifizierten Traffic realistisch. Deshalb ist die Spendenrate kein Ersatz für
Reichweite.

### 2. Bezahlte Einzelfallhilfe

Angebot: "QR rescue review" für 15 €: Der Nutzer behält das Foto lokal; er sendet nur freiwillig
eine nicht-sensitive Diagnose oder arbeitet in einer kurzen Bildschirmfreigabe. Ergebnis ist eine
Einschätzung, ein Aufnahmeplan und, wenn möglich, ein lokal erzeugter Export. Keine Erfolgsgarantie,
keine Verwahrung von Pairing-Geheimnissen.

Validierungsschwelle: mindestens 3 bezahlte Fälle in 30 Tagen. Liegt die Abschlussquote unter 10 %
der ernsthaften Anfragen, wird das Angebot eingestellt oder neu zugeschnitten.

### 3. Gewerblicher Pilot

Angebot für Refurbisher, Repair-Cafés mit Geräteannahme und kleine Werkstätten: 39 € für einen
Pilot mit bis zu 25 Bildern, lokalem Batch-Lauf, A4-Katalog und kurzem Fehlerbericht. Keine
Cloud-Plattform, kein Abo und keine Speicherung sensibler Codes.

Validierungsschwelle: 20 gezielte Gespräche, mindestens 5 Problem-Interviews, 2 echte Datensätze
und 1 bezahlter Pilot. Ohne bezahlten Pilot nach 20 qualifizierten Kontakten gibt es keine Evidenz
für B2B-Zahlungsbereitschaft.

## 30/60/90 Tage

### Tage 1–30: Zahlungen technisch möglich und Nachfrage beobachtbar machen

- Ko-fi-Zahlungsweg verbinden und eine echte 1-€-Testzahlung samt Rückerstattung durchführen.
- Öffentliche Seite veröffentlichen; Mobil-, Safari- und Kamera-Pfad real testen.
- Je einen sachlichen Linkvorschlag für passende Zigbee2MQTT-/Home-Assistant-Dokumentation
  vorbereiten. Vor Veröffentlichung wird jeder Text dem Betreiber gezeigt.
- Zehn vorhandene Hilfethreads nur dann beantworten, wenn der konkrete Fall gelöst wird. Nie ein
  Pairing-Geheimnis öffentlich wiedergeben.
- Baseline notieren: erfolgreiche Rettungen, Ko-fi-Klicks laut Ko-fi, Zahlungen, Betrag netto,
  Supportanfragen. Kein Tracking in der App.

Go/No-go nach 30 Tagen: mindestens 10 dokumentierte echte Nutzungsfälle oder 100 qualifizierte
Besuche über verweisende Troubleshooting-Seiten. Sonst zuerst Distribution verbessern, nicht den
Spendenknopf.

### Tage 31–60: Zahlungsbereitschaft testen

- Das 15-€-Hilfsangebot auf Ko-fi als klar begrenzte Leistung einstellen.
- 20 kurze Problem-Interviews mit Refurbishern, Reparaturwerkstätten oder Repair-Cafés anfragen;
  nicht pitchen, sondern Häufigkeit, heutige Umgehung, Zeitverlust und Datenschutzanforderung
  messen.
- Zwei reale, freigegebene Arbeitsabläufe lokal begleiten und nur anonymisierte Kennzahlen
  speichern.
- Einen Launch-Beitrag für Show HN und einen für r/homeassistant vorbereiten; beide vor dem
  Absenden zeigen.

Go/No-go nach 60 Tagen: entweder 8 einmalige 5-€-Spenden in einem Monat oder 3 bezahlte
Hilfsfälle oder 1 bezahlter 39-€-Pilot. Fehlt alles, ist 35 €/Monat mit dem jetzigen Angebot nicht
belegt.

### Tage 61–90: Wiederholbarkeit statt Einmaleffekt

- Nur den Kanal wiederholen, der eine echte Zahlung erzeugt hat.
- Bei B2C: Such- und Doku-Verweise ausbauen, Spendentext anhand tatsächlicher Abbrüche ändern.
- Bei B2B: Pilot als reproduzierbaren lokalen Ablauf dokumentieren; keine Plattform bauen, bevor
  ein zweiter Kunde zahlt.
- Wöchentlich eine einfache Umsatzdatei pflegen: Datum, Kanal, Brutto, Gebühr, Netto,
  Einmal-/wiederkehrend. Keine Kundengeheimnisse.

Erfolg: mindestens 35 € netto in drei aufeinanderfolgenden Monaten. Ein Launch-Ausschlag allein
gilt nicht. Scheitern: nach 90 Tagen trotz mindestens 500 qualifizierten Besuchen oder 20
qualifizierten B2B-Kontakten weniger als 35 € in jedem Monat. Dann wird das Ziel oder das Angebot
geändert, nicht die Messung schön gerechnet.

## Nicht tun

- Keine Paywall vor der Rettung und kein künstliches Limit der freien App.
- Keine Fotos oder Klartexte als Gegenleistung für Hilfe verlangen.
- Kein Analytics-Skript; Referrer aus fremden Seiten und Zahlungsberichte reichen für die erste
  Validierung.
- Kein Abo für Privatnutzer erfinden, deren Problem einmalig ist.
- Keine Umsatzbehauptung aus Marktgröße, Klicks oder Spendenabsichten ableiten.

## Sources

[1] https://mysemacode.com/repair-damaged-qr-code
[2] https://qrrepair.com/qr-code-repair/
[3] https://eancheck.com/qr-code-recovery
[4] https://zigbee2mqtt.io/devices/BMCT-SLZ.html
[5] https://www.vodafone-institut.de/en/publication/refurbished-over-new-a-second-chance-for-smartphones
[6] https://ko-fi.com/pricing
[7] https://liberapay.com/about
[8] https://dynamsoft.com/barcode-reader/pricing
[9] https://dialog.vde.com/en/vde-dialog-editions/2024-2/circular-economy/repaircafes
