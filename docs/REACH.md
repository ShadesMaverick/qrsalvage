# Reichweite: gefunden werden, wenn es brennt

Wie aus dem Werkzeug eines wird, an das die Leute denken. `VISION.md` sagt, *was* gebaut wird
und warum in dieser Reihenfolge; hier steht, *wie es zu den Menschen kommt*, die es brauchen —
und was das realistisch einbringt. Wie alles unter `docs/` deutsch und an uns gerichtet.

## Der eine Satz, aus dem alles Weitere folgt

**Niemand sucht qrsalvage. Alle suchen ihr Problem.**

Kein Mensch abonniert ein QR-Rettungswerkzeug, folgt seinem Account oder erinnert sich in
sechs Monaten an seinen Namen. Es gibt genau einen Moment, in dem jemand uns will: Ein Code auf
einer Verpackung, einem Ticket, Dokument, Schild, Produktetikett oder Gerät ist unlesbar,
mehrere Reader haben versagt, und die Person tippt entnervt eine Suchanfrage. Dieser Moment ist
der ganze Markt.

Daraus folgt die Strategie vollständig: **Wir werben nicht, wir liegen bereit.** Jede Maßnahme
in diesem Dokument beantwortet die Frage „Sind wir in diesem Moment auffindbar und sofort
benutzbar?" Alles, was diese Frage nicht beantwortet, ist Zeitverschwendung — egal wie sehr es
nach Marketing aussieht.

Das Ziel „die Leute denken QR → mein Tool" ist deshalb nicht über Bekanntheit zu erreichen,
sondern über **Auffindbarkeit plus einen Empfehlungsreflex bei den wenigen, die oft gefragt
werden**: Hilfsbereite in Reparatur-, Technik-, Archiv-, Inventar- und Smart-Home-Communities.
Nicht tausend Nutzer müssen uns kennen, sondern die Menschen, die in solchen Fällen Antworten
geben.

## Die ehrliche Zahl

Damit später niemand enttäuscht ist — inklusive uns:

- FOSS-Spendenquoten liegen typischerweise **deutlich unter 1 %** der Nutzer.
- Unser Fall ist seltener als andere (niemand braucht uns regelmäßig), aber unser
  **Spendenmoment ist außergewöhnlich gut**: akute Not, sichtbare Rettung, dreißig Sekunden
  später der Ask. Das ist Trinkgeld nach der Rettung, nicht „unterstütze eine Bibliothek".
  Realistisch sind **2–5 % der erfolgreichen Rettungen**, nicht 0,1 %.
- Erwartbare Größenordnung im eingeschwungenen Zustand: **5–30 € im Monat, grob 100–300 € im
  Jahr**, dazu ein einmaliger Ausschlag von vielleicht 50–150 € nach einem gelungenen
  Launch-Post.
- Von 5 € via PayPal bleiben nach Gebühren ~4,40 € (der Festbetrag trifft Kleinbeträge hart).
  Ko-fi und LiberaPay sind günstiger, PayPal bleibt trotzdem an erster Stelle, weil es die
  niedrigste Hürde hat. Beides anbieten, PayPal zuerst.

**Das deckt die Domain und gelegentlich eine Pizza. Es wird kein Nebeneinkommen.** Wer bei
einem Nischenwerkzeug ohne Wiederkehr etwas anderes verspricht, verkauft einen Kurs. Die
Spende ist Bestätigung, nicht Finanzierung — und als Bestätigung ist sie viel wert.

## Die Rangfolge der Maßnahmen

Streng in dieser Reihenfolge. Jede Stufe ist wertlos, solange die vorige fehlt.

### 0. Voraussetzung: die statische Browser-Version *(= Fahrplan 4/5)*

**Vor der Browser-Version lohnt keine einzige Marketing-Maßnahme.** „Installiere Python 3.11,
lege ein Venv an" verliert 95 % der Hilfesuchenden im ersten Satz — und die verlorenen kommen
nie wieder, auch nicht, wenn es später einfacher wird. Ein Link, der sofort funktioniert, ist
die Bedingung für alles Folgende.

Der Nebeneffekt ist unser bestes Argument: „Läuft komplett in deinem Browser, deine Fotos
verlassen dein Gerät nie" ist bei Geräte-Pairing-Codes kein Feature, sondern eine
Vertrauensfrage — und wir können sie wörtlich wahr beantworten, weil es keinen Server gibt.

### 1. Die Startseite trifft die Suchintention in der ersten Zeile

Nicht „qrsalvage — recover QR codes from what's left of them" als Erstes, sondern das Problem
der suchenden Person, in ihren Worten. Erst danach der Name.

- Erste Zeile sinngemäß: **„Beschädigter QR-Code auf Verpackung, Ticket, Dokument, Schild oder
  Produkt? Foto auswählen — alles bleibt auf deinem Gerät."**
- Direkt darunter der Knopf, keine Erklärstrecke davor. Wer hier landet, ist genervt.
- Die Erklärung (Methodenseite, Live-Ansicht) ist der Glaubwürdigkeitsbeweis *danach*, nicht
  die Begrüßung.
- Zweisprachig: Deutsch und Englisch. Der Gründungsfall ist deutsch, der Markt englisch.

### 2. Auf die echten Suchanfragen optimieren

Das sind keine Marketingbegriffe, sondern was Verzweifelte tippen. Diese Formulierungen
gehören wörtlich auf die Seite (in Überschriften, FAQ-Abschnitten, `<title>`, Meta-Description):

- „QR code won't scan" / „QR-Code lässt sich nicht scannen"
- „QR code damaged / scratched / faded / blurry"
- „QR code on packaging / ticket / document / product label"
- „QR code on curved surface" — unser Gründungsfall, erstaunlich wenig besetzt
- „Zigbee install code unreadable", „Matter pairing code QR damaged"
- „Hue / IKEA / Aqara / Sonoff QR code scan failed"
- „read QR code from photo" (die Leute wissen nicht, dass ihr Fall speziell ist)
- „QR code engraved metal" — Lasergravur, der zweite Kernfall

Eine kurze, ehrliche FAQ, die diese Fragen als Überschriften trägt und knapp beantwortet, ist
zugleich SEO und echter Nutzen. Keine Keyword-Wüste — Google bestraft das, und unsere Leser
merken es sofort.

### 3. In fremder Dokumentation verlinkt sein *(die stärkste Maßnahme)*

Ein Link im Troubleshooting-Abschnitt von Zigbee2MQTT, ZHA, Home Assistant oder einer
Geräte-Doku steht **genau im Problemmoment** und wirkt jahrelang weiter, ohne dass wir etwas
tun. Er ist mehr wert als jeder eigene Beitrag, weil ihn nicht wir schreiben.

Das ist ein Pull Request, keine Werbung: eine Zeile im Sinne von „QR-Code unlesbar? → qrsalvage
(FOSS, läuft lokal im Browser)". Kandidaten in absteigender Wirkung:

- [ ] Zigbee2MQTT-Doku, Abschnitt zum Pairing per Install-Code
- [ ] ZHA / Home-Assistant-Doku, Geräte hinzufügen
- [ ] Matter-Onboarding-Doku der HA-Community
- [ ] Awesome-Listen: awesome-selfhosted, awesome-home-assistant, awesome-privacy
- [ ] Wikipedia-Artikel „QR-Code", Abschnitt Fehlerkorrektur — nur wenn es dort sachlich
      hineingehört, sonst Finger weg (Eigenwerbung wird revertiert und schadet)

### 4. In Hilfe-Threads konkret helfen *(die glaubwürdigste)*

In r/homeassistant, r/zigbee, r/smarthome, dem HA-Forum und dem Zigbee2MQTT-Discord laufen
ständig Threads „kann den Code meiner Lampe nicht scannen". Dort *tatsächlich helfen* — den
Fall lösen, dann das Werkzeug nennen. Zehn solcher Antworten erzeugen Reputation, Backlinks
und genau den Empfehlungsreflex, um den es geht.

**Die Projektregeln gelten auch hier, ohne Ausnahme:** Fremde Fotos bleiben beim Fragenden,
ein wiederhergestellter Code wird **nie öffentlich gepostet** — das ist ein Pairing-Geheimnis,
kein Identifikator. Wer den Code hat und in Funkreichweite ist, kann das Gerät übernehmen. Also
öffentlich die Geräteadresse, das Geheimnis privat. Steht so in `CONTRIBUTING.md` und ist im
Forum genauso bindend wie im Repository.

Nie in einen Thread posten, ohne das eigentliche Problem zu lösen. Das ist der Unterschied
zwischen einer Empfehlung und Spam, und die Foren erkennen ihn zuverlässig.

### 5. Ein Launch-Post pro Plattform, erst wenn alles steht

Nicht mehrere, nicht wiederholt, nicht vorher. Der Aufhänger ist immer die **echte
Gründungsgeschichte**, nicht die Featureliste: Soziologe, gewölbte Zigbee-Lampe, kein Reader
kam damit klar, also selbst gebaut — mit Reed-Solomon-Erasures, weil eine ehrliche
Unsicherheit doppelt so viel wert ist wie ein geratener Wert.

- [ ] **Show HN** — dort zählt die Methode. Die berechneten Abbildungen der Methodenseite und
      die gemessenen Zahlen (36–81 % einzeln → 93–100 % fusioniert) sind genau die Währung
      dieses Publikums. Ehrliche negative Befunde (`ensemble.py`) sind dort ein Plus, kein Makel.
- [ ] **r/homeassistant** — die größte Konzentration echter Betroffener mit belegter
      Spendenkultur.
- [ ] **r/selfhosted, r/privacy** — Aufhänger: kein Server, keine Uploads, nachprüfbar.
- [ ] **Mastodon / Fediverse (FOSS-Szene)** — kleine Reichweite, überdurchschnittliche
      Spendenbereitschaft.
- [ ] **Lobsters, Hackaday-Tip** — je nach Resonanz.

**Das tragende Material ist ein 20–30-Sekunden-GIF der Live-Ansicht**: wie das Gitter einrastet,
wie die Unsicherheit schrumpft, wie der Klartext herausfällt. Es zeigt in einem Blick, was
sonst drei Absätze braucht. Ohne dieses GIF keinen Post.

## Der Spendenmoment im Detail

Die Mechanik steht (Karte auf der Erfolgsseite, unter dem Klartext). Was sie besser macht:

- **Konkreter Betrag statt offenem Feld.** „QR-Code gerettet? 5 € helfen, die Recovery-Engine
  zu pflegen und das private Browserwerkzeug verfügbar zu halten." Ein Vorschlag verankert;
  ein leeres Feld erzeugt Entscheidungslast und damit Abbruch.
- **Zweckbindung nennen.** „Deckt Domain und Weiterentwicklung." Kleinspenden steigen messbar,
  wenn der Zweck konkret ist.
- **Die Privacy-Aussage steht direkt daneben**, weil sie im selben Moment ihre Wirkung
  entfaltet: „Lief komplett auf deinem Gerät. Nichts wurde hochgeladen."
- **Niemals auf der Startseite**, niemals vor dem Ergebnis, niemals als Overlay. Ein Ask vor
  der Leistung verbrennt genau das Reziprozitätsgefühl, von dem er lebt.
- **Kein Tracking, kein Analytics** — auch nicht „nur zum Messen". Es widerspräche der
  Kernaussage, und die Kernaussage ist mehr wert als jede Statistik. Der einzige ehrliche
  Erfolgsindikator ist die Zahl der Spenden selbst.

## Was wir bewusst *nicht* tun

- **Keine Social-Media-Präsenz mit regelmäßigen Posts.** Es gibt nichts Wiederkehrendes zu
  erzählen, und ein verwaister Account sieht toter aus als gar keiner.
- **Keine Newsletter, kein „Sign up".** Niemand will eine Beziehung zu einem Werkzeug, das er
  einmal im Jahr braucht.
- **Keine Feature-Verbreiterung als Wachstumsstrategie.** Data Matrix und Co. verwässern den
  Fokus, ohne die Nische zu vertiefen (siehe Grundsätze in `VISION.md`).
- **Keine wiederholten Posts in denselben Foren.** Einmal vorstellen, danach nur noch in
  konkreten Hilfefällen auftauchen.
- **Keine Erfolgsbehauptungen ohne Messung** — auch nicht im Marketing. Die Zahlen, die wir
  nennen, stammen aus `scripts/`, mit Konfidenzintervallen. Das ist auf Show HN ein Vorteil
  und in den Foren der Grund, warum man uns weiterempfiehlt.

## Wenn es doch mehr werden soll: die andere Zielgruppe

Privatnutzer haben das Problem einmal. Geld liegt bei denen, die es **in Serie** haben:

Refurbisher und Gebrauchtgeräte-Händler, Repair-Cafés, E-Waste-Verwerter, Inventarisierung mit
gravierten Anlagen-Codes, Archive. Für die ist nicht die Einzelrettung wertvoll, sondern
**Stapelverarbeitung und der A4-Katalog-Export** — der bereits gebaut ist und für Privatnutzer
fast überdimensioniert wirkt.

Dort wären Support-Verträge, eine Batch-Oberfläche oder eine gehostete Variante denkbar, ohne
die FOSS-Basis anzutasten (Apache-2.0 erlaubt das ausdrücklich). Das ist aber ein **eigenes
Projektziel mit eigenem Aufwand und eigener Zielgruppenansprache** — kein Nebenprodukt des
jetzigen Plans. Hier festgehalten, damit die Option nicht vergessen wird, nicht als Aufgabe.

## Reihenfolge in einem Absatz

Browser-Version fertigstellen, Startseite auf die Suchintention drehen, FAQ mit den echten
Suchbegriffen, das GIF aufnehmen, dann die Doku-Pull-Requests, dann zehn echte Hilfe-Antworten,
dann die Launch-Posts. Danach nichts mehr aktiv tun außer helfen, wenn jemand fragt — und die
Rettungsquote weiter messen, denn sie ist der einzige Faktor, den wir selbst in der Hand haben.
