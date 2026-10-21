# Combined Manual Recovery and Axolotl Brand Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finderpunkte und gekrümmten Umriss in einem jederzeit erreichbaren manuellen Editor gemeinsam nutzen und das Axolotl als Logo, Hero-Regenerationsfigur und optionales Digital-Pet etablieren.

**Architecture:** Der Kern erzeugt Finder- und Umrisskandidaten in demselben vorbereiteten Koordinatensystem, überträgt die Umrisskrümmung auf finderbasierte Kandidaten und lässt weiterhin die bekannten QR-Strukturzellen entscheiden. Ein browserreines Zustandsmodul hält beide Markierungsebenen unabhängig. Logo und Hero sind lokale SVG/CSS-Komponenten; nur der bestehende Companion ist abschaltbar.

**Tech Stack:** Python 3.11/3.12, NumPy, OpenCV, pytest, statisches HTML/CSS/JavaScript ohne npm, Node für browserreine Vertragstests, Chrome/Edge für reale Layouttests.

**Spec:** `docs/superpowers/specs/2026-10-21-combined-manual-axolotl-design.md`

## Global Constraints

- Kern, CLI, lokaler Server und Browser-Worker verwenden dieselben Kern- und API-Funktionen.
- QR-Zellen behalten die Zustände schwarz, weiß und unbekannt.
- Bilder, Markierungen und Klartext verlassen das Gerät nicht; keine neuen Laufzeit-Netzwerkzugriffe.
- Keine neue Abhängigkeit und keine Änderung oder Überschreibung unter `fixtures/`.
- Code, Tests, Bezeichner, Kommentare und Programmausgaben bleiben Englisch.
- Pixelkoordinaten sind `(x, y)`, Modulkoordinaten `(row, col)`.
- DE und EN bleiben vollständig symmetrisch; alle sichtbaren Ziele sind mindestens 44 × 44 CSS-Pixel.
- Finder-only, Outline-only, automatische Rettung, CLI und Katalog bleiben rückwärtskompatibel.
- Jede Produktionsänderung folgt RED → GREEN → Refactor; ein Test muss vor dem Fix aus dem erwarteten Grund scheitern.

## Dateistruktur

- `src/qrsalvage/core/geometry.py`: gekrümmte finderbasierte Kandidaten, reine Geometriehilfen.
- `src/qrsalvage/core/pipeline.py`: gemeinsames Arbeitskoordinatensystem und Kandidatenpool.
- `src/qrsalvage/api.py`: kombinierter JSON-Vertrag und Ergebnisdiagnose.
- `src/qrsalvage/web/manual-editor.js`: reiner Zustand beider Markierungsebenen.
- `src/qrsalvage/web/outline-editor.js`: bestehende reine Griffgeometrie; bleibt fokussiert.
- `src/qrsalvage/web/hero-regeneration.js`: einmalige Hero-Szenensteuerung ohne Backendwissen.
- `src/qrsalvage/web/brand-mark.svg`: statisches, nicht scannbares Axolotl-QR-Signet.
- `src/qrsalvage/web/app.js`: DOM-/Canvas-Adapter, Payload-Erzeugung, Backendaufruf.
- `src/qrsalvage/web/companion.js`: optionaler Begleiter und Sitzungsbegrüßung.
- `src/qrsalvage/web/{index,method,legal}.html`, `style.css`, `locale.js`: Markup, Darstellung und Sprache.
- `scripts/ab_manual_geometry.py`: Finder-only/Outline-only/Combined-Messung.
- `tests/test_solver.py`, `tests/test_server.py`, `tests/test_contracts.py`, `tests/test_measurements.py`: Kern-, API-, Browser- und Instrumentenverträge.
- `docs/ARCHITECTURE.md`, `scripts/README.md`: Datenfluss und Messinstrument.

---

### Task 1: Gemeinsame Finder-/Umrissgeometrie im Kern

**Files:**
- Modify: `src/qrsalvage/core/geometry.py:665-693`
- Modify: `src/qrsalvage/core/pipeline.py:391-610,853-990`
- Modify: `src/qrsalvage/api.py:86-260`
- Test: `tests/test_solver.py`
- Test: `tests/test_server.py`
- Test: `tests/test_contracts.py`

**Interfaces:**
- Consumes: `CurvedOutline`, `fit_grid()`, `fit_outline()`, `bow_from_midpoints()`, `evaluate_bowed()`, `snap_to_finders()`.
- Produces: `curve_finder_fits(gray, fits, outline) -> list[GridFit]`; `solve(..., finder_points=..., outline=...)` accepts both; JSON result fields `geometry_source` (`automatic`, `finders`, `outline`, `combined`) and `combined_discarded`.

- [ ] **Step 1: Schreibe fehlschlagende API- und Kerntests**

Ersetze den bisherigen Ablehnungstest für beide Hinweise durch einen Forwarding-Vertrag und füge
synthetische Kernfälle hinzu:

```python
def test_api_forwards_finders_and_outline_together(monkeypatch):
    seen = {}

    def fake_solve(_image, **kwargs):
        seen.update(kwargs)
        return SolveResult(text=None, failure="measured failure")

    monkeypatch.setattr(api, "solve", fake_solve)
    answer = api.solve_payload(
        {
            "image": _data_url(FIXTURE),
            "finder_points": [{"x": 30.0, "y": 31.0}, {"x": 220.0, "y": 32.0}],
            "outline": _outline_payload(),
        }
    )
    assert answer["failure"] == "measured failure"
    assert seen["finder_points"] == [(30.0, 31.0), (220.0, 32.0)]
    assert isinstance(seen["outline"], CurvedOutline)


def test_combined_hints_share_the_outline_working_transform(monkeypatch):
    points = [(120.0, 140.0), (760.0, 150.0), (130.0, 780.0)]
    outline = CurvedOutline(
        corners=np.array([[80, 90], [810, 100], [800, 830], [70, 820]], dtype=float),
        edge_midpoints=np.array([[445, 70], [830, 465], [430, 845], [48, 455]], dtype=float),
    )
    events = []
    result = solve(_synthetic_photo(), finder_points=points, outline=outline,
                   progress=lambda event, data: events.append((event, data)))
    assert any(event == "finders" and data["count"] >= 2 for event, data in events)
    assert result.geometry_source == "combined"
```

Füge außerdem Tests hinzu, die beweisen, dass ein unbrauchbarer Combined-Kandidat den
Finder-only- und Outline-only-Fallback nicht entfernt, zwei Finder über die API akzeptiert werden
und Crop-Offsets bei beiden Hinweisarten nur einmal angewendet werden.

- [ ] **Step 2: Führe RED aus**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
.venv\Scripts\python.exe -m pytest tests\test_solver.py tests\test_server.py tests\test_contracts.py -k "combined or outline or hand_marked" -q
```

Expected: FAIL, weil `solve_payload()` beide Hinweise ablehnt, `_attempt()` im Outline-Zweig
leere Finder meldet und `SolveResult` noch kein `geometry_source` besitzt.

- [ ] **Step 3: Extrahiere die gekrümmte Kandidatenhilfe**

Ergänze in `geometry.py` eine einzige Wiederverwendung des vorhandenen Bow-Modells:

```python
def curve_finder_fits(
    gray: np.ndarray,
    fits: Sequence[GridFit],
    outline: CurvedOutline,
) -> list[GridFit]:
    """Apply the manual edge bow to finder-seeded grids without replacing their corners."""
    curved: list[GridFit] = []
    for fit in fits:
        known_dark, known_light = structure_mask(fit.modules)
        bow = bow_from_midpoints(fit.corners, outline.edge_midpoints)
        curved.append(
            evaluate_bowed(
                gray, fit.corners, bow, fit.modules, 12, known_dark, known_light
            )
        )
    return curved
```

Die Funktion übernimmt weder Auswahl noch Decodierung; sie überträgt ausschließlich die bereits
modellierte Kantenkrümmung.

- [ ] **Step 4: Vereine die Vorbereitung und den Kandidatenpool**

Ergänze in `pipeline.py` eine inverse Punkttransformation und extrahiere die bestehende
Finder-Kandidatenlogik aus `_attempt()`:

```python
def _to_working_points(
    points: Sequence[tuple[float, float]],
    transform: tuple[float, float, float],
) -> list[tuple[float, float]]:
    ox, oy, factor = transform
    return [((x - ox) * factor, (y - oy) * factor) for x, y in points]
```

Im Outline-Zweig wird das Bild genau einmal durch `_prepare_with_outline()` vorbereitet. Falls
Finderpunkte vorhanden sind, werden sie über `_to_working_points()` transformiert und mit
`snap_to_finders(binary, working_points)` eingemessen. Erzeuge anschließend:

```python
outline_fits = fit_outline(gray, prepared_outline, sizes, start_delta=12.0, on_step=on_fit)
finder_fits, anchor_pair = _fit_from_finders(gray, finders, sizes, manually_marked=True,
                                             on_step=on_fit)
combined_fits = curve_finder_fits(gray, finder_fits, prepared_outline)
fits = [*outline_fits, *finder_fits, *combined_fits]
fit_sources = (["outline"] * len(outline_fits) + ["finders"] * len(finder_fits)
               + ["combined"] * len(combined_fits))
```

Verwirf finderbasierte Kandidaten, wenn ihre drei erwarteten Finderquadranten nicht innerhalb des
markierten Polygons liegen. Behalte `outline_fits` und die unveränderten `finder_fits` immer im
Pool; nur die daraus abgeleiteten Combined-Kandidaten dürfen als widersprüchlich ausscheiden.
`choose_grid()` und alle ternären Sampling-/Repair-Schritte bleiben unverändert.

- [ ] **Step 5: Öffne den API-Vertrag und diagnostiziere den Gewinner**

Entferne ausschließlich die Ablehnung „use either finder points or a manual outline“ und öffne die
bisherige API-Prüfung von exakt drei auf zwei oder drei Finderpunkte. Multi-Image und Ensemble
bleiben verboten. Erweitere `_Attempt` um die zu jedem Fit parallele Herkunftsliste und die Zahl
verworfener Combined-Kandidaten. Nach `choose_grid()` wird die Herkunft des identischen
Gewinnerobjekts festgehalten; Restart und Anchor-Sweep richten sich danach, ob der Gewinner ein
unveränderter Finderkandidat ist, nicht pauschal danach, ob ein Outline mitgeliefert wurde.

Ergänze `SolveResult.geometry_source: str = "automatic"` und
`SolveResult.combined_discarded: int = 0`; setze den Ursprung auf `finders`, `outline` oder
`combined` und gib beide Felder über `solve_payload()` aus. Das `chosen`-Fortschrittsereignis
erhält dieselben Diagnosen, aber niemals Payloadtext. Das vorhandene Feld `source` behält seine
Bedeutung (`direct`/`recovery`) und wird nicht zweckentfremdet.

- [ ] **Step 6: Führe GREEN und Regression aus**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
.venv\Scripts\python.exe -m pytest tests\test_solver.py tests\test_server.py tests\test_contracts.py -q
.venv\Scripts\python.exe -m ruff check src/qrsalvage/core src/qrsalvage/api.py tests
.venv\Scripts\python.exe -m mypy
.venv312\Scripts\python.exe -m mypy
```

Expected: alle Läufe Exit 0; bestehende Finder- und Umrisstests bleiben unverändert grün.

- [ ] **Step 7: Commit**

```powershell
git add src/qrsalvage/core/geometry.py src/qrsalvage/core/pipeline.py src/qrsalvage/api.py tests/test_solver.py tests/test_server.py tests/test_contracts.py
git commit -m "feat(core): combine manual geometry hints"
```

---

### Task 2: A/B/C-Instrument für manuelle Hinweise

**Files:**
- Create: `scripts/ab_manual_geometry.py`
- Modify: `scripts/README.md`
- Test: `tests/test_measurements.py`

**Interfaces:**
- Consumes: `pipeline.solve()`, synthetische Fotos, Finder-/Grid-Fortschrittsereignisse.
- Produces: Kommando `python scripts/ab_manual_geometry.py --samples N`; Ausgabe pro Schadensstufe für `finders`, `outline`, `combined` mit Erfolg, falschen bekannten Zellen und Laufzeit.

- [ ] **Step 1: Schreibe den fehlschlagenden Instrumentenvertrag**

```python
def test_manual_geometry_ab_reports_all_three_arms():
    script = (ROOT / "scripts" / "ab_manual_geometry.py").read_text(encoding="utf-8")
    assert 'ARMS = ("finders", "outline", "combined")' in script
    assert "wrong_known" in script
    assert "time.perf_counter" in script
```

- [ ] **Step 2: Führe RED aus**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_measurements.py -k manual_geometry -q
```

Expected: FAIL, weil das Instrument noch nicht existiert.

- [ ] **Step 3: Implementiere das Messinstrument**

Das Skript erzeugt für jeden Seed zuerst ein kontrastreiches Referenzfoto mit derselben
geometrischen Verzerrung wie der beschädigte Fall. Es ruft für diese Referenz gezielt die interne
Geometriestufe `_attempt()` auf, damit der vorgeschaltete direkte Decoder die benötigten
Finder-/Grid-Ereignisse nicht überspringen kann. Aus den gesnappten Findern und dem von
`choose_grid()` gewählten Referenzfit entstehen drei Finder und acht Umrissgriffe. Danach wird mit
demselben Seed und derselben Geometrie nur die optische Beschädigung verschärft. Jede Variante
bekommt dasselbe Zielfoto, Budget und dieselben Markierungen:

```python
ARMS = ("finders", "outline", "combined")


def run_arm(photo, finders, outline, arm):
    kwargs = {
        "finders": {"finder_points": finders},
        "outline": {"outline": outline},
        "combined": {"finder_points": finders, "outline": outline},
    }[arm]
    started = time.perf_counter()
    result = pipeline.solve(photo, **kwargs)
    return result, time.perf_counter() - started
```

Die Ausgabe berichtet `wrong_known`, Kandidatenzahl und Laufzeit, zählt gültige falsche Decodes
separat und gibt keinen Payloadtext aus. Falls Combined einen durch einen Einzelarm gelösten Seed
verliert, beendet das Skript den Release-Modus mit Exit 1.

- [ ] **Step 4: Dokumentiere und verifiziere**

Ergänze in `scripts/README.md` eine Tabellenzeile mit der exakten Frage des Instruments. Run:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_measurements.py -q
.venv\Scripts\python.exe scripts\ab_manual_geometry.py --samples 2
```

Expected: Test Exit 0; Skript zeigt alle drei Arme und keine Klartexte.

- [ ] **Step 5: Commit**

```powershell
git add scripts/ab_manual_geometry.py scripts/README.md tests/test_measurements.py
git commit -m "test: measure combined manual geometry"
```

---

### Task 3: Reines Zustandsmodul für den gemeinsamen Editor

**Files:**
- Create: `src/qrsalvage/web/manual-editor.js`
- Modify: `src/qrsalvage/web/index.html`
- Modify: `src/qrsalvage/server.py`
- Modify: `scripts/build_site.py`
- Test: `tests/test_server.py`
- Test: `tests/test_repository.py`

**Interfaces:**
- Consumes: Punktobjekte `{x, y}` und bestehende Griffbewegungen aus `outline-editor.js`.
- Produces: `window.qrManualEditor`/CommonJS mit `createState()`, `setTool()`, `placePoint()`, `setOutline()`, `undo()`, `resetLayer()`, `usableHints()`.

- [ ] **Step 1: Schreibe Node-basierte RED-Tests**

```python
def test_manual_editor_preserves_both_layers_and_builds_combined_hints():
    result = _call_manual_editor_probe()
    assert result["afterToolSwitch"]["finders"] == [{"x": 10, "y": 11}, {"x": 90, "y": 12}]
    assert result["hints"]["kind"] == "combined"
    assert len(result["hints"]["finder_points"]) == 2
    assert len(result["hints"]["outline"]["corners"]) == 4
    assert len(result["hints"]["outline"]["edge_midpoints"]) == 4


def test_manual_editor_omits_incomplete_layers_without_deleting_them():
    result = _call_manual_editor_probe("incomplete")
    assert result["visibleCorners"] == 2
    assert result["hints"]["kind"] == "finders"
    assert "outline" not in result["hints"]
```

Teste zusätzlich Undo pro Ebene, Reset pro Ebene, Abbruch ohne Zustandsverlust und unveränderte
Koordinaten nach Sprach-/Werkzeugwechsel.

- [ ] **Step 2: Führe RED aus**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
.venv\Scripts\python.exe -m pytest tests\test_server.py -k manual_editor_state -q
```

Expected: FAIL, weil `manual-editor.js` fehlt.

- [ ] **Step 3: Implementiere den unveränderlichen Zustandsvertrag**

```javascript
function createState() {
  return {
    active: false,
    tool: "finders",
    finders: [],
    corners: [],
    edgeMidpoints: [],
    selectedHandle: null,
    history: { finders: [], outline: [] },
  };
}

function usableHints(state) {
  const answer = { kind: "none" };
  if (state.finders.length === 2 || state.finders.length === 3) {
    answer.finder_points = state.finders.map((point) => ({ ...point }));
    answer.kind = "finders";
  }
  if (state.corners.length === 4 && state.edgeMidpoints.length === 4) {
    answer.outline = {
      corners: state.corners.map((point) => ({ ...point })),
      edge_midpoints: state.edgeMidpoints.map((point) => ({ ...point })),
    };
    answer.kind = answer.kind === "finders" ? "combined" : "outline";
  }
  return answer;
}
```

Alle Mutationen geben einen neuen Zustand zurück. Begrenze Finder auf drei und Ecken/Mittelpunkte
auf vier; speichere Undo-Snapshots nur für die betroffene Ebene.

- [ ] **Step 4: Binde und inventarisiere das Modul vor `app.js` und führe GREEN aus**

```html
<script src="outline-editor.js"></script>
<script src="manual-editor.js"></script>
<script src="app.js"></script>
```

Nimm `manual-editor.js` zugleich in `Handler.STATIC`, `PAGE_FILES` und den expliziten
Repository-Inventarvertrag auf; der lokale Server und GitHub Pages müssen dieselbe Datei liefern.

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_server.py tests\test_repository.py -k "manual_editor_state or script_order or inventory" -q
node --check src\qrsalvage\web\manual-editor.js
```

Expected: Exit 0.

- [ ] **Step 5: Commit**

```powershell
git add src/qrsalvage/web/manual-editor.js src/qrsalvage/web/index.html src/qrsalvage/server.py scripts/build_site.py tests/test_server.py tests/test_repository.py
git commit -m "feat(web): add combined manual editor state"
```

---

### Task 4: Jederzeit erreichbarer gemeinsamer Canvas-Editor

**Files:**
- Modify: `src/qrsalvage/web/index.html:120-180`
- Modify: `src/qrsalvage/web/app.js:190-1010,1103-1160,1510-1825`
- Modify: `src/qrsalvage/web/style.css:190-290,340-410,620-670`
- Modify: `src/qrsalvage/web/locale.js`
- Test: `tests/test_server.py`
- Test: `tests/test_worker_bridge.py`

**Interfaces:**
- Consumes: `qrManualEditor`, `qrOutlineEditor`, kombinierter API-Vertrag aus Task 1.
- Produces: immer sichtbarer `#manualOpen` bei einem Foto; `solve(points, outlineHint)` sendet beide vollständigen Ebenen; Canvas behält beide Overlays.

- [ ] **Step 1: Schreibe fehlschlagende Runtime- und Browsertests**

Teste den vollständigen Weg: Foto laden, Editor vor jedem Fehlschlag öffnen, zwei Finder setzen,
Umriss ergänzen, Werkzeug mehrfach wechseln, Combined starten und das Backendpayload abfangen:

```python
def test_manual_recovery_is_available_before_failure_and_sends_both_layers():
    result = _call_app_runtime_probe("combined-manual")
    assert result["openBeforeFailure"] is True
    assert result["payload"]["finder_points"] == [
        {"x": 20, "y": 21}, {"x": 180, "y": 22}
    ]
    assert len(result["payload"]["outline"]["corners"]) == 4
    assert len(result["payload"]["outline"]["edge_midpoints"]) == 4
    assert result["backendCalls"] == 1
```

Ergänze reale Browserfälle für 320/375 CSS-Pixel, Touch-/Maus-Griffe, Tastatur, 200 Prozent Text,
DE/EN-Wechsel und alle Ziele ≥44 × 44.

- [ ] **Step 2: Führe RED aus**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
.venv\Scripts\python.exe -m pytest tests\test_server.py tests\test_worker_bridge.py -k "combined_manual or manual_recovery" -q
```

Expected: FAIL, weil der Einstieg erst nach Failure erscheint, der dritte Finder sofort startet
und der Umrissaufruf Finderpunkte verwirft.

- [ ] **Step 3: Ersetze die vier alten Assistance-Aktionen durch einen Editor-Toolbarvertrag**

Das Markup enthält mindestens:

```html
<button id="manualOpen" type="button" data-i18n="manual.open">Manual recovery</button>
<div id="manualTools" hidden data-companion-anchor="manual">
  <div role="group" data-i18n-aria="manual.toolLabel">
    <button id="manualFinders" type="button" aria-pressed="true" data-i18n="manual.finders">Finders</button>
    <button id="manualOutline" type="button" aria-pressed="false" data-i18n="manual.outline">Outline</button>
  </div>
  <button id="manualUndo" type="button" data-i18n="action.undo">Undo</button>
  <button id="manualResetLayer" type="button" data-i18n="manual.resetLayer">Reset layer</button>
  <button id="manualSolve" type="button" disabled data-i18n="manual.recoverHints">Recover with hints</button>
  <button id="manualClose" type="button" data-i18n="action.close">Close</button>
</div>
```

Entferne keine Diagnosehinweise; verweise alte Failure-Aktionen auf denselben `manualOpen`-Weg.

- [ ] **Step 4: Mache `app.js` zum Adapter des Zustandsmoduls**

Der dritte Finder startet nicht mehr automatisch. `renderManualEditor()` zeichnet Finder und
Umriss gleichzeitig, aktualisiert Fortschritt und setzt:

```javascript
const hints = window.qrManualEditor.usableHints(manualState);
manualSolve.disabled = hints.kind === "none";
```

Beim Start:

```javascript
const finderPoints = hints.finder_points || null;
const outlineHint = hints.outline ? {
  corners: hints.outline.corners,
  edgeMidpoints: hints.outline.edge_midpoints,
} : null;
solve(finderPoints, outlineHint);
```

Backendfehler friert den Editor nicht ein und löscht keine Markierungen. Foto-Reset löscht den
Zustand. Sprachwechsel ruft nur `renderManualEditor()` auf.

- [ ] **Step 5: Ergänze vollständige DE/EN-Texte und responsive Darstellung**

Füge symmetrische Keys für Einstieg, Ebenen, Punktfortschritt, kombinierte Zusammenfassung,
Undo/Reset und Tastaturhilfe hinzu. Finder verwenden Ringe mit Nummern, Ecken Quadrate und
Kantenmittelpunkte Rauten. Toolbar und Canvas dürfen bei 320 Pixeln keinen Seitenüberlauf erzeugen.

- [ ] **Step 6: Führe GREEN und komplette Webverträge aus**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
.venv\Scripts\python.exe -m pytest tests\test_server.py tests\test_worker_bridge.py -q
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m ruff format --check .
```

Expected: Exit 0; echte Browserprobe meldet keinen Überlauf, kein Ziel unter 44 Pixel und exakt ein
kombiniertes Backendpayload.

- [ ] **Step 7: Commit**

```powershell
git add src/qrsalvage/web/index.html src/qrsalvage/web/app.js src/qrsalvage/web/style.css src/qrsalvage/web/locale.js tests/test_server.py tests/test_worker_bridge.py
git commit -m "feat(web): combine manual recovery tools"
```

---

### Task 5: Axolotl-Logo und Hero-Regeneration

**Files:**
- Create: `src/qrsalvage/web/brand-mark.svg`
- Create: `src/qrsalvage/web/hero-regeneration.js`
- Modify: `src/qrsalvage/web/index.html:35-75`
- Modify: `src/qrsalvage/web/method.html`
- Modify: `src/qrsalvage/web/legal.html`
- Modify: `src/qrsalvage/web/style.css`
- Modify: `src/qrsalvage/web/locale.js`
- Modify: `src/qrsalvage/server.py`
- Modify: `scripts/build_site.py`
- Test: `tests/test_server.py`
- Test: `tests/test_repository.py`

**Interfaces:**
- Consumes: `sessionStorage`, `matchMedia('(prefers-reduced-motion: reduce)')`, bestehende Farbvariablen.
- Produces: lokales `brand-mark.svg`; `qrHeroRegeneration.create({root, session, media})` mit `start()`, `setMotionReduced()`, `refreshLocale()`, `destroy()`.

- [ ] **Step 1: Schreibe fehlschlagende Marken- und Animationsverträge**

```python
def test_brand_mark_and_hero_are_local_non_scannable_assets():
    mark = (WEB / "brand-mark.svg").read_text(encoding="utf-8")
    page = (WEB / "index.html").read_text(encoding="utf-8")
    assert 'data-brand="axolotl-qr"' in mark
    assert 'id="heroRegeneration"' in page
    assert "https://" not in mark


def test_hero_runs_once_and_reduced_motion_starts_complete():
    result = _call_hero_probe()
    assert result["firstRun"] == ["damaged", "budding", "regrowing", "complete"]
    assert result["secondRun"] == ["complete"]
    assert result["reducedMotion"] == ["complete"]
```

Teste zusätzlich, dass Logo und Hero auf allen drei Seiten vorkommen. Der Decoder-Negativtest liest
die Rechtecke des SVG per XML, rastert sie mit NumPy/OpenCV auf eine weiße Fläche und verlangt,
dass der bestehende Oracle keinen QR-Payload erkennt; dafür kommt keine SVG-Abhängigkeit hinzu.

- [ ] **Step 2: Führe RED aus**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
.venv\Scripts\python.exe -m pytest tests\test_server.py tests\test_repository.py -k "brand_mark or hero_regeneration" -q
```

Expected: FAIL, weil Asset, Markup und Controller fehlen.

- [ ] **Step 3: Erzeuge das statische SVG-Signet**

Baue ein lokales SVG mit `viewBox="0 0 64 64"`, hart gerasterten Axolotl-Kiemen in Pink,
mintfarbener Körperkontur und drei bewusst unvollständigen QR-Finderformen. Verwende nur die
bestehenden Markenfarben und setze am Wurzelelement `data-brand="axolotl-qr"`. Das Muster darf
keine gültige QR-Matrix bilden.

- [ ] **Step 4: Implementiere die einmalige Hero-Zustandsmaschine**

```javascript
const PHASES = Object.freeze(["damaged", "budding", "regrowing", "complete"]);

function create({ root, session, media }) {
  let timers = [];
  function start() {
    const seen = session.getItem("qrsalvage.heroRegenerationSeen") === "true";
    if (seen || media.matches) {
      root.dataset.phase = "complete";
      return;
    }
    PHASES.forEach((phase, index) => {
      timers.push(setTimeout(() => { root.dataset.phase = phase; }, index * 550));
    });
    session.setItem("qrsalvage.heroRegenerationSeen", "true");
  }
  function destroy() { timers.forEach(clearTimeout); timers = []; }
  function setMotionReduced(value) {
    if (value) { destroy(); root.dataset.phase = "complete"; }
  }
  return { start, setMotionReduced, destroy };
}
```

Das Hero-Markup enthält feste, nicht scannbare Module in drei Gruppen. CSS blendet sie pro Phase
ein; es gibt keine Endlosschleife. Bei `prefers-reduced-motion` oder dem bestehenden
Bewegungsumschalter ist nur `complete` sichtbar. Der Umschalter darf die Animation jederzeit in
den Endzustand überführen und startet sie beim Zurückschalten in derselben Sitzung nicht erneut.

- [ ] **Step 5: Integriere Logo und Hero auf allen Seiten**

Die Brandlinks verwenden das SVG plus sichtbaren Text `qrsalvage`. Nur `index.html` enthält die
animierte Szene. `method.html` und `legal.html` zeigen dasselbe statische Logo. Alle Assets bleiben
relative lokale Pfade. Inventarisiere `brand-mark.svg` und `hero-regeneration.js` explizit in
`Handler.STATIC`, `PAGE_FILES` und dem Repository-Vertrag, damit lokaler Server und Pages-Build
identisch bleiben.

- [ ] **Step 6: Führe GREEN, Build und Decoder-Negativtest aus**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_server.py tests\test_repository.py -k "brand_mark or hero_regeneration" -q
node --check src\qrsalvage\web\hero-regeneration.js
.venv\Scripts\python.exe scripts\build_site.py
```

Expected: Exit 0; Build-Audit meldet keine neue absolute URL; Negativtest findet keinen QR-Text im
Signet oder Hero-Muster.

- [ ] **Step 7: Commit**

```powershell
git add src/qrsalvage/web/brand-mark.svg src/qrsalvage/web/hero-regeneration.js src/qrsalvage/web/index.html src/qrsalvage/web/method.html src/qrsalvage/web/legal.html src/qrsalvage/web/style.css src/qrsalvage/web/locale.js src/qrsalvage/server.py scripts/build_site.py tests/test_server.py tests/test_repository.py
git commit -m "feat(web): add Axolotl regeneration brand"
```

---

### Task 6: Optionales Digital-Pet und unabhängige Bewegungssteuerung

**Files:**
- Modify: `src/qrsalvage/web/companion.js`
- Modify: `src/qrsalvage/web/app.js:98-185`
- Modify: `src/qrsalvage/web/index.html:50-65`
- Modify: `src/qrsalvage/web/style.css:425-475`
- Modify: `src/qrsalvage/web/locale.js`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: LocalStorage-Key `qrsalvage.companionEnabled`, SessionStorage-Key `qrsalvage.companionGreetingSeen`, bestehende Companion-Zustände.
- Produces: `companion.setEnabled(boolean)`, `companion.enabled()`, eigener `#companionToggle`; Bewegungsreduktion bleibt separat.

- [ ] **Step 1: Schreibe fehlschlagende Companion-Verträge**

```python
def test_companion_opt_out_hides_only_the_digital_pet_and_persists():
    result = _call_companion_controller_probe("opt-out")
    assert result["companionHidden"] is True
    assert result["bubbleHidden"] is True
    assert result["brandVisible"] is True
    assert result["heroVisible"] is True
    assert result["stored"] == "false"


def test_companion_greets_once_without_donation_link():
    result = _call_companion_controller_probe("greeting")
    assert result["firstBubbleKey"] == "companion.greeting"
    assert result["secondBubble"] is None
    assert result["donationLink"] is False
```

- [ ] **Step 2: Führe RED aus**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
.venv\Scripts\python.exe -m pytest tests\test_server.py -k "companion_opt_out or companion_greets" -q
```

Expected: FAIL, weil Begleiter und Bewegung noch dasselbe Steuerelement teilen.

- [ ] **Step 3: Trenne Enabled und Motion**

Erweitere den Controller:

```javascript
function setEnabled(value) {
  enabled = Boolean(value);
  local.set("qrsalvage.companionEnabled", String(enabled));
  root.hidden = !enabled;
  root.setAttribute("aria-hidden", String(!enabled));
  if (!enabled) hideBubble();
  invalidatePlacement();
}
```

`destroy()` räumt weiterhin Listener, Observer und Animationen auf. Disabled entfernt alle
Companion-Buttons/Links aus der Fokusreihenfolge über `hidden`; UI-Hinweise außerhalb des
Companions bleiben bestehen.

- [ ] **Step 4: Ergänze Steuerung und Begrüßung**

`#companionToggle` schaltet nur das Pet. `#motionToggle` steuert ausschließlich Bewegung. Die
Begrüßung erscheint nur bei Enabled und nur einmal pro Sitzung, enthält keinen Ko-fi-Link und wird
von Recovery-/Failure-Hinweisen verdrängt.

- [ ] **Step 5: Führe GREEN und Browserzustände aus**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_server.py -k companion -q
node --check src\qrsalvage\web\companion.js
```

Prüfe im Browser Enabled/Disabled nach Reload, Reduced Motion mit Enabled, Logo/Hero bei Disabled
und Ko-fi ausschließlich nach Erfolg. Expected: alle Fälle grün, keine Fokusziele im verborgenen
Pet.

- [ ] **Step 6: Commit**

```powershell
git add src/qrsalvage/web/companion.js src/qrsalvage/web/app.js src/qrsalvage/web/index.html src/qrsalvage/web/style.css src/qrsalvage/web/locale.js tests/test_server.py
git commit -m "feat(web): make the Axolotl pet optional"
```

---

### Task 7: Architektur, Verträge und vollständige Integration

**Files:**
- Modify: `docs/ARCHITECTURE.md`
- Inspect: `src/qrsalvage/web/backend-server.js`
- Inspect: `src/qrsalvage/web/backend-worker.js`
- Inspect: `src/qrsalvage/web/worker.js`
- Modify: `tests/test_worker_bridge.py`
- Modify: `tests/test_repository.py`
- Modify: `tests/test_server.py`

**Interfaces:**
- Consumes: kombinierter API-Vertrag, `manual-editor.js`, Hero- und Companion-Controller.
- Produces: dokumentierter End-to-End-Datenfluss mit identischem Server-/Workerpayload; Repository-Inventar kennt alle neuen Assets.

- [ ] **Step 1: Schreibe fehlschlagende Integrationsverträge**

Teste in ausführbaren JavaScript-Probes, dass beide Backends ein Payload mit `finder_points` und
`outline` bytegleich an `fetch()` beziehungsweise `postMessage()` weitergeben, `worker.js` beide
Teilstrukturen unverändert an `solve_payload()` reicht und alle HTML-Seiten ihre neuen lokalen
Dateien in gültiger Reihenfolge laden.

```python
def test_both_backends_preserve_combined_manual_hints():
    payload = _combined_payload_without_image_bytes()
    assert _probe_server_backend(payload)["request"] == payload
    assert _probe_worker_backend(payload)["message"]["payload"] == payload
```

- [ ] **Step 2: Führe RED aus**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
.venv\Scripts\python.exe -m pytest tests\test_worker_bridge.py tests\test_repository.py tests\test_server.py -k "combined or inventory or architecture" -q
```

Expected: mindestens Inventar-/Architekturvertrag schlägt fehl.

- [ ] **Step 3: Schließe Transport- und Dokumentationslücken**

Halte die Backends weiterhin als generische, austauschbare Fassungen desselben Vertrags;
dupliziere keine Validierung aus `api.py`. Ändere die drei Transportdateien nur, wenn der
ausführbare Vertrag tatsächlich eine Transformation oder einen Verlust zeigt. Ergänze
`docs/ARCHITECTURE.md` um:

```text
manual-editor.js -> app.js payload -> backend.js -> api.solve_payload
                                      -> pipeline.solve(finder_points, outline)
                                      -> shared candidate pool -> ternary sampling/repair
```

Dokumentiere außerdem die Trennung Logo/Hero/Pet und die lokalen Persistenzkeys.

- [ ] **Step 4: Führe Integration und statische Prüfungen aus**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
.venv\Scripts\python.exe -m pytest tests\test_worker_bridge.py tests\test_repository.py tests\test_server.py -q
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m ruff format --check .
.venv\Scripts\python.exe -m mypy
.venv312\Scripts\python.exe -m mypy
```

Expected: alle Läufe Exit 0.

- [ ] **Step 5: Commit**

```powershell
git add docs/ARCHITECTURE.md tests/test_worker_bridge.py tests/test_repository.py tests/test_server.py
# Falls ein Transportdefekt testgetrieben behoben wurde, nur die tatsächlich geänderte Datei ergänzen.
git commit -m "docs: map combined manual recovery"
```

---

### Task 8: Gesamtverifikation, Review und Veröffentlichung

**Files:**
- Verify: gesamtes Repository
- Generate: `site/` (gitignoriert)
- Record: planbezogener Bericht unter `.superpowers/sdd/2026-10-21-combined-manual-axolotl/`

**Interfaces:**
- Consumes: alle vorherigen Tasks und Messinstrument aus Task 2.
- Produces: geprüfter Release-Commit, erfolgreicher CI-/Pages-Lauf und verifizierte Live-Seite.

- [ ] **Step 1: Führe fachliche Messung aus**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
.venv\Scripts\python.exe scripts\ab_manual_geometry.py --samples 16
```

Dokumentiere Finder-only, Outline-only und Combined. Stoppe die Veröffentlichung, falls Combined
einen von einem Einzelarm gelösten Fall verliert oder eine gültige falsche Decodierung erzeugt.

- [ ] **Step 2: Führe die vollständige lokale Matrix aus**

Run:

```powershell
$env:PYTHONPATH=(Resolve-Path 'src').Path
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m ruff format --check .
.venv\Scripts\python.exe -m mypy
.venv312\Scripts\python.exe -m mypy
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe scripts\build_site.py
git diff --check
```

Expected: alle Befehle Exit 0; vollständige Suite ohne Regression; Build-Audit erklärt jede
absolute URL.

- [ ] **Step 3: Führe die reale Browsermatrix aus**

Prüfe 1440, 1024, 768, 375 und 320 CSS-Pixel sowie 812 × 375 quer. Pflichtfälle:

- automatische Rettung des öffentlichen Fixtures;
- Finder-only, Outline-only und Combined mit exakt einem Backendaufruf;
- Werkzeugwechsel, Undo, Ebenenreset, Failure-Retry und Sprachwechsel ohne Geometrieverlust;
- Maus, Touch und vollständiger Tastaturpfad;
- Logo auf drei Seiten, Hero einmal pro Sitzung, Reduced Motion statisch;
- Pet Enabled/Disabled über Reload; Logo/Hero bleiben sichtbar;
- 200 Prozent Text, keine Seite überbreit, keine sichtbare Interaktion unter 44 × 44;
- keine externen Laufzeitrequests und keine Browserfehler.

- [ ] **Step 4: Fordere unabhängigen Code-Review an**

Erzeuge den Review-Diff vom Merge-Base bis HEAD. Der Reviewer prüft besonders:

- gemeinsame Koordinatentransformation ohne `(row, col)`-/`(x, y)`-Vertauschung;
- Einzelpfad-Fallback im Combined-Kandidatenpool;
- keine Binärreduktion der Modulunsicherheit;
- identische Server-/Workerverträge;
- Hero/Pet-Persistenz, Reduced Motion, Lokalisierung und Fokusreihenfolge;
- Messinstrument vergleicht identische Fotos und Markierungen.

Behebe Important-Findings testgetrieben und re-reviewe ausschließlich den Fixdiff.

- [ ] **Step 5: Committe letzte reine Verifikations-/Dokumentationskorrekturen**

```powershell
git status --short
git log --oneline --decorate -12
```

Der Arbeitsbaum muss sauber sein; Produktionsänderungen ohne zugehörigen RED/GREEN-Nachweis werden
nicht veröffentlicht.

- [ ] **Step 6: Veröffentliche und verifiziere live**

Nach bestätigter Freigabe den geprüften HEAD per Fast-Forward nach `main` pushen. Überwache exakt
diesen Commit bis CI und Pages `completed/success` melden. Vergleiche mindestens `index.html`,
`app.js`, `manual-editor.js`, `hero-regeneration.js`, `companion.js`, `style.css`, `locale.js`,
`brand-mark.svg`, `method.html` und `legal.html` bytegenau mit `site/`. Wiederhole Desktop- und
375-Pixel-Smoke-Test auf `https://shadesmaverick.github.io/qrsalvage/`.

