# Veröffentlichung härten

## Ziel

Die öffentliche Darstellung von qrsalvage soll denselben Belegstandard erfüllen wie der
Recovery-Kern: Nur geprüfter Code wird ausgeliefert, Installations- und Datenschutzangaben sind
wörtlich wahr, und Repository-Automation sowie Dokumentation widersprechen sich nicht.

Diese Arbeit verändert keine Bildverarbeitung und keine Recovery-Entscheidung. Sie fügt keine
Abhängigkeit hinzu und veröffentlicht weder Paket noch Tag noch Commit selbständig.

## Ausgangslage

- `Pages` baut und deployt bei jedem Push auf `main` unabhängig vom Ergebnis von `CI`. Die
  öffentliche Actions-Historie enthält deshalb grüne Deployments zu roten CI-Läufen.
- `main` ist auf GitHub ungeschützt. Das ist eine GitHub-Einstellung, kein Zustand im Git-Baum.
- Die README nennt `pip install qrsalvage`, obwohl unter diesem Namen kein PyPI-Projekt besteht.
- Es gibt weder Tag noch GitHub Release; `pyproject.toml` nennt bereits Version `0.1.0`.
- Die Meta-CSP enthält `frame-ancestors`, obwohl Browser diese Direktive aus einer Meta-CSP
  ignorieren. Einige Texte schreiben der CSP außerdem einen stärkeren Beweis zu, als sie liefert.
- CI und Actions verwenden bewegliche Versionsbereiche beziehungsweise Major-Tags, während
  Kommentare teilweise Reproduzierbarkeit behaupten.
- Interne Veröffentlichungsnotizen beschreiben Pages und das öffentliche Repository noch als
  unerledigt. GitHub fehlen außerdem einfache Issue- und PR-Vorlagen.
- Bestehende Commits sind nicht kryptografisch signiert und wegen der Codeberg-Noreply-Adresse
  keinem GitHub-Konto zugeordnet. Eine nachträgliche Änderung verlangte einen History-Rewrite.

## Leitentscheidungen

### 1. Repository zuerst, externe Zustände getrennt

Alle im Git-Baum lösbaren Punkte werden auf einem isolierten Branch umgesetzt. Nicht Teil dieser
Änderung sind:

- Push oder Merge auf einen gemeinsam genutzten Branch,
- Branch-Protection beziehungsweise Rulesets auf GitHub,
- Löschen des öffentlichen Branches `harden-declared-invariants`,
- Erstellen eines Tags oder GitHub Releases,
- Registrierung oder Veröffentlichung auf PyPI,
- Umschreiben bestehender Commits oder Ändern der globalen Git-Identität.

Für diese Punkte entsteht eine kurze, ausführbare Checkliste. Ihre Durchführung braucht einen
separaten, ausdrücklich freigegebenen Schritt mit den erforderlichen Kontorechten.

### 2. Ein Deployment gehört genau zu einem grünen CI-Commit

Der bestehende `Pages`-Workflow bleibt als eigene Zuständigkeit erhalten, wird aber ausschließlich
durch den erfolgreichen Abschluss des Workflows `CI` auf `main` ausgelöst. Er prüft:

- Ereignis ist `workflow_run` für `CI`,
- Ergebnis ist `success`,
- Branch ist `main`,
- Checkout und Build verwenden exakt `github.event.workflow_run.head_sha`.

Ein manueller Pages-Dispatch entfällt, weil er den Nachweis umgehen würde. Die vorhandenen
Pages-Buildprüfungen, Hashprüfungen und der URL-Audit bleiben unverändert. Ein Repository-Test
liest den Workflow als Text und hält Trigger, Gate und SHA-Bindung fest. YAML wird nicht mit einer
neuen Bibliothek geparst.

Branch-Protection ergänzt diesen Mechanismus später auf GitHub: Pull Request erforderlich,
aktuelle CI-Checks erforderlich, kein Force-Push und kein Löschen von `main`.

### 3. Nur heute funktionierende Installation versprechen

Bis ein echtes PyPI-Release existiert, nennt die README zwei unterstützte Wege:

1. direkte Installation aus dem öffentlichen GitHub-Repository;
2. Clone plus editable install für Entwicklung.

`pip install qrsalvage` wird nicht beworben. `pyproject.toml` erhält die öffentlichen Projekt-URLs,
die auch bei einem späteren Paket-Release benötigt werden. Eine deutsche Release-Checkliste legt
fest, dass Tag, GitHub Release, Artefakte, PyPI und README-Angabe als eine atomare öffentliche
Umstellung behandelt werden. Sie führt keine dieser Aktionen selbst aus.

Die statische Version `0.1.0` bleibt bestehen. Ohne veröffentlichten Tag wird keine neue
Versionsnummer erfunden.

### 4. Datenschutzbehauptungen auf das tatsächlich Erzwungene begrenzen

Die Meta-CSP behält die wirksamen Direktiven, insbesondere `connect-src 'self'`, enthält aber kein
wirkungsloses `frame-ancestors`. GitHub Pages erlaubt für dieses Projekt keine frei gesetzten
Response-Header; Clickjacking-Schutz wird deshalb nicht behauptet.

Die Texte unterscheiden drei Aussagen:

- Der ausgelieferte Anwendungscode hat keinen Uploadpfad für Foto oder Payload.
- Der Build auditiert ausgelieferte Textressourcen auf unerklärte absolute URLs.
- Die CSP beschränkt programmgesteuerte Verbindungen auf denselben Ursprung, ist aber allein kein
  mathematischer Beweis, dass Daten das Gerät nie verlassen könnten.

Die Nutzeraussage „Nothing is uploaded“ bleibt bestehen, weil Codepfad, Build-Audit und statischer
Host sie gemeinsam tragen. Begründungstexte behaupten nicht mehr, allein die CSP mache einen
Upload unmöglich. Tests decken die Meta-CSP und die Netzwerkaudit-Regeln ab.

### 5. Reproduzierbarkeit ohne Verlust des Kompatibilitätssignals

Die Paketmetadaten behalten Mindestversionen: Sie beschreiben, womit qrsalvage kompatibel sein
soll. Die Entwicklungs-/CI-Installation wird dagegen in `requirements.txt` auf die in den beiden
vorhandenen Umgebungen bereits verwendeten Versionen festgelegt: NumPy 2.4.6 für Python 3.11,
NumPy 2.5.4 ab Python 3.12, OpenCV 5.0.0.93, Pillow 12.3.0, zxing-cpp 3.1.1, pytest 9.1.1,
Ruff 0.17.1 und mypy 2.4.0. Python-Marker bilden den NumPy-Unterschied ab. Es werden keine neuen
Pakete aufgenommen.

GitHub Actions werden auf vollständige Commit-SHAs festgelegt; der lesbare Major-Tag bleibt als
Kommentar daneben. Die Workflow-Kommentare sagen anschließend, dass die CI die festgelegte
Entwicklungsumgebung auf der unterstützten Betriebssystem-/Python-Matrix prüft. Kompatibilität mit
neueren Abhängigkeiten wird erst nach einer ausdrücklichen Aktualisierung dieser Pins geprüft; es
gibt keinen still driftenden „latest“-Job.

Diese Aufgabe ändert keine lokale Venv und führt kein `pip install` aus.

### 6. Veröffentlichungszustand und Beitragswege aufräumen

`VISION.md` und `ISSUES.md` werden auf den aktuellen Stand gebracht:

- GitHub Pages ist aktiv und die Standardadresse ist die gegenwärtige Produktionsadresse.
- Eine eigene Domain ist eine optionale spätere Maßnahme, kein erfüllter Ist-Zustand.
- Safari/iOS bleibt offen, solange kein realer Test belegt ist.
- Bereits erledigte Browser-Vendoring- und Encode-Aufgaben werden nicht weiter als Restarbeit
  geführt.

GitHub erhält schlanke strukturierte Vorlagen für Fehler und Verbesserungen sowie eine
Pull-Request-Vorlage. Sie wiederholen die Projektinvarianten nicht vollständig, sondern verlinken
auf `CONTRIBUTING.md` und fragen bei Recovery-Änderungen nach Vorher-/Nachhermessung. Reale Fotos
und entschlüsselte Payloads dürfen ausdrücklich nicht in Issues gelangen.

Es wird kein Verhaltenskodex mit erfundener privater Kontaktstelle angelegt. Der fehlende
Code-of-Conduct ist weniger schädlich als ein Meldeweg, den niemand vertraulich bedienen kann.

### 7. Commit-Identität ohne Geschichtsfälschung

Bestehende Commits bleiben unverändert. Die Release-Checkliste erklärt:

- `[verified]` im Betreff ist kein GitHub-Signaturstatus und wird künftig nicht als Ersatz dafür
  verwendet;
- Release-Tags sollen mit einer auf GitHub verifizierbaren Identität signiert werden;
- Kontozuordnung und Signatur werden vor einem öffentlichen Release auf GitHub kontrolliert.

Welche E-Mail-Adresse und welcher Schlüssel dafür verwendet werden, bleibt eine lokale
Kontoeinstellung und wird nicht im Repository erfunden.

## Arbeitspakete und Reihenfolge

1. **Deployment-Gate:** Workflow-Vertragstest, fehlschlagenden Test beobachten, Pages-Trigger und
   SHA-Bindung ändern, gezielte Tests und Workflow-Diff prüfen.
2. **Installation und Release-Wahrheit:** README-Test beziehungsweise Metadatenprüfung zuerst,
   Installationsanweisung und Projekt-URLs ändern, Release-Checkliste ergänzen.
3. **Browser-Sicherheit und Aussagen:** Tests für CSP und relevante Texte zuerst, unwirksame
   Direktive entfernen, VISION/Rechtstext/Build-Kommentare präzisieren.
4. **CI-Lieferkette:** bestehende Versionen ermitteln, Vertragsprüfung schreiben, Abhängigkeiten
   und Actions soweit ohne neue Infrastruktur möglich fixieren, Kommentare korrigieren.
5. **Repository-Hygiene:** veraltete Roadmapstellen und GitHub-Vorlagen aktualisieren; danach
   Dokumentations- und Vorlagentests.

Jedes Paket wird seriell von einem frischen Implementierungs-Subagenten bearbeitet. Ein separater
Review-Subagent prüft anschließend Spezifikationstreue und Qualität. Kritische oder wichtige
Befunde gehen vor dem nächsten Paket an denselben Implementierer zurück. Nach allen Paketen folgt
ein unabhängiger Gesamt-Review.

## Verifikation

Gezielte Tests werden in jedem Paket testgetrieben ausgeführt. Vor Abschluss laufen frisch und
vollständig:

```powershell
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m ruff format --check .
.venv312\Scripts\python.exe -m mypy
```

Im isolierten Worktree werden die vorhandenen Interpreter aus dem Hauptcheckout verwendet und
der Worktree-Quellpfad nur für den jeweiligen Prozess gesetzt. Kein Venv wird aktiviert oder
verändert.

## Erfolgskriterien

- Kein Pages-Deployment kann aus einem roten oder anderen als dem gebauten CI-Commit entstehen.
- Jede Installationsanweisung funktioniert ohne ein nicht existentes PyPI-Projekt.
- Keine Dokumentation schreibt einer Meta-CSP unwirksame oder überstarke Garantien zu.
- Versions- und Action-Politik entsprechen den Kommentaren im Workflow.
- Öffentliche Roadmap, Issue-Texte und GitHub-Vorlagen beschreiben den tatsächlichen Zustand.
- Alle vier Abschlussprüfungen sind grün.
- Externe Restschritte sind explizit aufgelistet und wurden nicht stillschweigend ausgeführt.
