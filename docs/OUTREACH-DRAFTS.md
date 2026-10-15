# Externe Texte vor Veröffentlichung

Keiner dieser Texte wird ungeprüft veröffentlicht. Vor jedem Versand werden Zielseite, aktueller
Wortlaut und der konkrete Nutzen noch einmal geprüft. Keine fremden Fotos oder wiederhergestellten
Pairing-Geheimnisse gehören in einen öffentlichen Beitrag.

## Zigbee2MQTT-Dokumentation: knapper Linkvorschlag

Titelvorschlag: `Document local recovery option for unreadable install-code QR labels`

Text:

> Some devices require the complete value encoded in the QR label rather than the shorter text
> printed beside it. If the label is faded, engraved, curved or damaged, qrsalvage can attempt to
> recover it locally in the browser. It is free software, uploads neither the photograph nor the
> recovered install code, and reports when the remaining image is insufficient. A closer photo
> from several angles gives it the best chance.

Linkziel: die veröffentlichte qrsalvage-Seite. Erst nach öffentlichem Deployment einsetzen.

Warum dieser Text vertretbar ist: Er ergänzt nur Geräteseiten, auf denen Zigbee2MQTT bereits das
Scannen des langen QR-Inhalts verlangt. Er behauptet keine allgemeine Erfolgsquote.

## Antwort in einem konkreten Hilfethread

> The short code printed next to the symbol may not be the full install-code value expected by
> Zigbee2MQTT. First take a close, sharp photo with the whole QR code and its border visible. If a
> normal scanner still cannot read it, qrsalvage is an open-source recovery tool that runs
> entirely in the browser; the photo and recovered code are not uploaded. Try several photos from
> different angles. Please do not paste the recovered install code into this public thread: it is
> a device pairing secret.

Nur posten, wenn der Thread tatsächlich ein unlesbares oder beschädigtes Etikett beschreibt. Bei
Netzwerk-, Firmware- oder Commissioning-Fehlern wäre der Link unpassend.

## Show HN

Titel:

> Show HN: qrsalvage – recover QR codes from curved, faded and damaged labels

Text:

> I built qrsalvage after a Zigbee bulb's pairing code defeated every scanner I tried. The code
> was laser-engraved on a curved dome, low-contrast, stained and only a few pixels per module.
>
> The tool treats the cells fixed by the QR standard as a calibration target. It searches the
> grid and version against those cells, keeps a probability for every data module, and hands
> uncertain codewords to Reed-Solomon as erasures rather than confident mistakes. Several photos
> from different angles can be fused because their geometry errors land on different cells.
>
> It runs locally in the browser. There is no upload endpoint; the CSP limits connections to the
> site's own static files. The repository contains synthetic benchmarks, confidence intervals,
> calibration checks and the negative experiments too. The headline recovery rates are benchmark
> results, not a promise about arbitrary real labels.
>
> I would especially value hard cases whose owners can describe the damage without publishing
> the image or payload. Pairing codes are secrets, so real photos stay local.

## r/homeassistant

Titel:

> I made a local browser tool for damaged Zigbee and Matter QR labels

Text:

> A curved QR engraving on a Zigbee bulb started this project. Normal phone scanners and online
> decoders could not read it, so I built a recovery path that fits the grid against the QR
> standard's known cells, preserves uncertain cells as erasures and can combine several photos
> taken from different angles.
>
> qrsalvage now runs entirely in the browser. Photos and recovered pairing codes are not uploaded.
> It also recognises Zigbee, Matter and Wi-Fi payloads and can derive the Matter manual pairing
> code after a successful recovery.
>
> It is free software. The repository includes reproducible synthetic benchmarks and the limits:
> very low resolution and physically missing modules remain unrecoverable. If you try it, a close
> photo plus two or three genuinely different angles helps much more than a burst from one spot.
>
> Please do not post recovered install codes or Matter passcodes in the comments.

## Problem-Interview mit Refurbisher oder Werkstatt

Kein Verkaufsgespräch. Zehn Minuten, fünf Fragen:

1. Wie oft pro Monat scheitert eine Geräteannahme an einem unlesbaren QR-, Data-Matrix- oder
   Serienetikett?
2. Was tun Mitarbeitende heute, wie lange dauert es, und wann wird das Gerät abgeschrieben?
3. Welche Codes enthalten Geheimnisse oder Kundendaten und dürfen keine Cloud verlassen?
4. Wäre ein lokaler Batch-Lauf mit Bericht und druckbarem Ersatzcode nützlich? Für welche Menge?
5. Würden Sie 39 € für einen einmaligen Pilot mit bis zu 25 Bildern bezahlen? Falls nein: Liegt es
   am Preis, am seltenen Problem oder am fehlenden Funktionsumfang?

Dokumentiert werden nur Häufigkeit, heutiger Aufwand, gewünschter Ablauf und Zahlungsentscheidung.
Keine Bilder, Gerätecodes oder Kundennamen.
