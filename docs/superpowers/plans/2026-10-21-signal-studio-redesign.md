# Signal Studio Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the complete qrsalvage website as the approved adaptive Signal Studio, with Easy/Pro density, automatic DE/EN selection and a state-driven pixel Axolotl companion, without changing recovery behavior.

**Architecture:** Keep the static no-build web shell and preserve every existing DOM hook used by recovery. Add three small browser/CommonJS modules for studio state, locale and companion behavior; `app.js` remains the orchestration shell and reports normalized UI events to them. All new assets are local and explicitly allowlisted for both the loopback server and the GitHub Pages build.

**Tech Stack:** Static HTML/CSS/JavaScript, CommonJS-compatible pure helpers tested through Node from pytest, Python 3.11/3.12, Pillow for asset validation, existing Pyodide/OpenCV/zxing browser runtime.

**Spec:** `docs/superpowers/specs/2026-10-21-signal-studio-redesign-design.md`

## Global Constraints

- Nothing under `src/qrsalvage/core/` changes or imports UI code.
- Easy and Pro use identical requests, algorithms and results; the mode changes presentation only.
- Runtime network access remains forbidden. No remote font, image, script, analytics or embedded donation widget.
- Photos and decoded payloads never leave the device and never enter tests, commits, issues or logs.
- No dependency, npm step or new build system is added.
- Code, identifiers, comments, tests and UI copy are English; German documentation and translated UI copy are the only German project text.
- Existing colors remain exact: `#1b252e`, `#232f3a`, `#26333f`, `#1f2a34`, `#37485a`, `#f2f4f5`, `#93a3b0`, `#f07ea3`, `#f7b3c8`, `#8fd3b0`, `#e0b356`, `#e0644a`.
- Typography uses local system fonts only; prose measures 65–75 characters and monospace is reserved for measurements, steps and technical labels.
- Spacing follows a 4/8-pixel grid with a single shared radius, border and elevation scale.
- Touch targets are at least 44 by 44 CSS pixels; keyboard focus remains visible.
- `prefers-reduced-motion: reduce` produces a complete static experience.
- `fixtures/` is never overwritten or deleted.
- Use `.venv\Scripts\python.exe` without activating the venv; CI-parity mypy uses `.venv312\Scripts\python.exe`.
- Preserve all unrelated dirty worktree changes. Stage only files named by the current task.

## File Map

### New production files

- `src/qrsalvage/web/studio-state.js` — pure phase and Easy/Pro reducer; no DOM or backend access.
- `src/qrsalvage/web/locale.js` — DE/EN dictionaries, selection, interpolation and page binding.
- `src/qrsalvage/web/companion.js` — pure companion decisions plus a thin DOM controller.
- `src/qrsalvage/web/axolotl-companion.png` — transparent local sprite sheet derived from the existing mark.

### Existing production files

- `src/qrsalvage/web/index.html` — adaptive stage, Studio shell, bilingual semantic content and stable recovery IDs.
- `src/qrsalvage/web/style.css` — shared tokens, layout, component states, responsive rules and motion fallbacks for every page.
- `src/qrsalvage/web/app.js` — existing recovery orchestration; dispatches normalized Studio and companion events and requests translated UI text.
- `src/qrsalvage/web/method.html` — bilingual Signal Manual in the shared shell.
- `src/qrsalvage/web/legal.html` — bilingual quiet legal layout; German remains authoritative.
- `src/qrsalvage/server.py` — explicit local static-file allowlist.
- `scripts/build_site.py` — explicit Pages asset inventory.
- `docs/ARCHITECTURE.md` — new browser-module boundaries and event flow.
- `.gitignore` — ignore persisted `.superpowers/` visual-brainstorm sessions.

### Tests

- `tests/test_server.py` — Node helper tests, DOM contracts, accessibility, static serving and runtime-network invariants.
- `tests/test_repository.py` — legal, package and companion-asset invariants.

---

### Task 1: Studio state reducer and Easy/Pro contract

**Files:**
- Create: `src/qrsalvage/web/studio-state.js`
- Modify: `tests/test_server.py`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `createStudioState(mode?: string) -> {phase: string, mode: "easy" | "pro"}`
- Produces: `reduceStudioState(state, event) -> state`
- Produces: `viewForState(state) -> {phaseClass, modeClass, diagnosticsExpanded, manualToolsExpanded}`
- Consumes: normalized events whose `type` is one of `RESET`, `IMAGES_READY`, `PREPARING`, `RECOVERY_STARTED`, `ASSISTANCE_REQUIRED`, `RECOVERY_SUCCEEDED`, `RECOVERY_FAILED`, `SET_MODE`.

- [ ] **Step 1: Generalize the existing Node helper and write reducer tests**

Add a helper beside `_call_outline_editor` in `tests/test_server.py`:

```python
def _call_web_module(file_name: str, function: str, *args):
    helper = ROOT / "src" / "qrsalvage" / "web" / file_name
    script = """
const helper = require(process.argv[1]);
const args = JSON.parse(process.argv[3]);
process.stdout.write(JSON.stringify(helper[process.argv[2]](...args)));
"""
    completed = subprocess.run(
        ["node", "-e", script, str(helper), function, json.dumps(args)],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)
```

Retain `_call_outline_editor` as a small wrapper over this helper. Add tests that pin these exact transitions:

```python
def test_studio_state_reducer_keeps_mode_separate_from_recovery_phase():
    state = _call_web_module("studio-state.js", "createStudioState", "pro")
    assert state == {"phase": "welcome", "mode": "pro"}
    state = _call_web_module(
        "studio-state.js", "reduceStudioState", state, {"type": "RECOVERY_STARTED"}
    )
    assert state == {"phase": "recovering", "mode": "pro"}
    state = _call_web_module(
        "studio-state.js", "reduceStudioState", state, {"type": "SET_MODE", "mode": "easy"}
    )
    assert state == {"phase": "recovering", "mode": "easy"}


@pytest.mark.parametrize(
    ("event", "phase"),
    [
        ("RESET", "welcome"),
        ("IMAGES_READY", "ready"),
        ("PREPARING", "preparing"),
        ("RECOVERY_STARTED", "recovering"),
        ("ASSISTANCE_REQUIRED", "assistance"),
        ("RECOVERY_SUCCEEDED", "success"),
        ("RECOVERY_FAILED", "failure"),
    ],
)
def test_studio_state_reducer_has_one_named_phase(event, phase):
    state = _call_web_module("studio-state.js", "createStudioState", "invalid")
    state = _call_web_module(
        "studio-state.js", "reduceStudioState", state, {"type": event}
    )
    view = _call_web_module("studio-state.js", "viewForState", state)
    assert state["phase"] == phase
    assert state["mode"] == "easy"
    assert view["phaseClass"] == f"studio-phase-{phase}"
```

- [ ] **Step 2: Run the reducer tests and verify the missing module fails**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_server.py -k "studio_state" -v
```

Expected: FAIL because `studio-state.js` does not exist.

- [ ] **Step 3: Implement the pure reducer**

Create `studio-state.js` as an IIFE/CommonJS helper. Use an immutable reducer and reject unknown phase changes by returning the current state:

```javascript
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.qrStudioState = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const PHASE_FOR_EVENT = Object.freeze({
    RESET: "welcome",
    IMAGES_READY: "ready",
    PREPARING: "preparing",
    RECOVERY_STARTED: "recovering",
    ASSISTANCE_REQUIRED: "assistance",
    RECOVERY_SUCCEEDED: "success",
    RECOVERY_FAILED: "failure",
  });

  function normalizeMode(value) {
    return value === "pro" ? "pro" : "easy";
  }

  function createStudioState(mode) {
    return { phase: "welcome", mode: normalizeMode(mode) };
  }

  function reduceStudioState(state, event) {
    if (event.type === "SET_MODE") return { ...state, mode: normalizeMode(event.mode) };
    const phase = PHASE_FOR_EVENT[event.type];
    return phase ? { ...state, phase } : state;
  }

  function viewForState(state) {
    const mode = normalizeMode(state.mode);
    return {
      phaseClass: `studio-phase-${state.phase}`,
      modeClass: `studio-mode-${mode}`,
      diagnosticsExpanded: mode === "pro",
      manualToolsExpanded: mode === "pro",
    };
  }

  return { createStudioState, reduceStudioState, viewForState };
});
```

Add `.superpowers/` to `.gitignore`; do not delete or stage the existing persisted brainstorm directory.

- [ ] **Step 4: Run focused and formatting checks**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_server.py -k "studio_state" -v
.venv\Scripts\python.exe -m ruff check tests\test_server.py
git diff --check
```

Expected: all pass.

- [ ] **Step 5: Commit the state contract**

```powershell
git add .gitignore src/qrsalvage/web/studio-state.js tests/test_server.py
git commit -m "feat(web): add Studio view state"
```

---

### Task 2: Locale module and language persistence

**Files:**
- Create: `src/qrsalvage/web/locale.js`
- Modify: `tests/test_server.py`
- Modify: `src/qrsalvage/server.py:152-169`
- Modify: `scripts/build_site.py:103-114`

**Interfaces:**
- Produces: `chooseLocale(stored: string | null, preferred: string[]) -> "de" | "en"`
- Produces: `translate(locale: string, key: string, values?: object) -> string`
- Produces: `createLocaleController(options) -> {locale, setLocale, t, apply}`
- Browser global: `window.qrLocale`.
- Consumes: elements with `data-i18n`, `data-i18n-aria`, `data-lang`, and buttons with `data-locale`.
- Storage key: `qrsalvage.locale`; a failed storage read or write leaves the in-memory locale active.

- [ ] **Step 1: Write locale-selection, interpolation and completeness tests**

Add focused tests using `_call_web_module`:

```python
def test_locale_prefers_a_saved_choice_then_browser_german_then_english():
    assert _call_web_module("locale.js", "chooseLocale", "en", ["de-DE"]) == "en"
    assert _call_web_module("locale.js", "chooseLocale", None, ["de-DE", "en"]) == "de"
    assert _call_web_module("locale.js", "chooseLocale", None, ["fr-FR"]) == "en"


def test_locale_interpolates_values_and_falls_back_to_english():
    assert _call_web_module(
        "locale.js", "translate", "de", "progress.photoCount", {"count": 3}
    ) == "3 Fotos werden gemeinsam gelesen"
    assert _call_web_module("locale.js", "translate", "fr", "action.reset") == "Start over"


def test_locale_dictionaries_have_identical_keys():
    keys = _call_web_module("locale.js", "dictionaryKeys")
    assert keys["en"] == keys["de"]
```

- [ ] **Step 2: Run the locale tests and verify they fail**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_server.py -k "locale_" -v
```

Expected: FAIL because `locale.js` does not exist.

- [ ] **Step 3: Implement the locale dictionary and pure functions**

Create an IIFE/CommonJS module with exact symmetric keys. The initial dictionary must include
all shell, mode, step, input, camera, recovery, assistance, result, catalogue, export,
companion and donation keys used by later tasks. Start with this required manifest and its full
English/German values, not empty fallbacks:

```javascript
const en = {
  "nav.studio": "Studio", "nav.method": "Method", "nav.github": "GitHub",
  "nav.privacy": "Privacy", "mode.easy": "Easy", "mode.pro": "Pro",
  "stage.input": "Input", "stage.geometry": "Geometry", "stage.recover": "Recover",
  "stage.export": "Export", "action.choose": "Choose a photograph",
  "action.camera": "Use the camera", "action.reset": "Start over",
  "action.cancel": "Cancel", "action.copy": "Copy",
  "progress.photoCount": "{count} photographs are read together",
  "progress.preparing": "Preparing the recovery engine…",
  "progress.recovering": "Reading what remains…",
  "result.success": "QR code recovered", "result.failure": "Recovery failed",
  "companion.outline": "I found the outline. I’ll ask only if a damaged corner needs help.",
  "companion.success": "Recovered. Your result is ready.",
  "donation.prompt": "Did qrsalvage help? You can support its development on Ko-fi.",
  "donation.action": "Support on Ko-fi", "donation.dismiss": "Not now",
};
const de = {
  "nav.studio": "Studio", "nav.method": "Methode", "nav.github": "GitHub",
  "nav.privacy": "Datenschutz", "mode.easy": "Einfach", "mode.pro": "Pro",
  "stage.input": "Eingabe", "stage.geometry": "Geometrie", "stage.recover": "Rettung",
  "stage.export": "Export", "action.choose": "Foto auswählen",
  "action.camera": "Kamera verwenden", "action.reset": "Neu beginnen",
  "action.cancel": "Abbrechen", "action.copy": "Kopieren",
  "progress.photoCount": "{count} Fotos werden gemeinsam gelesen",
  "progress.preparing": "Recovery-Engine wird vorbereitet…",
  "progress.recovering": "Vorhandene Spuren werden gelesen…",
  "result.success": "QR-Code wiederhergestellt", "result.failure": "Rettung fehlgeschlagen",
  "companion.outline": "Ich habe den Umriss gefunden. Nur bei einer beschädigten Ecke frage ich nach Hilfe.",
  "companion.success": "Gerettet. Dein Ergebnis ist bereit.",
  "donation.prompt": "Hat qrsalvage geholfen? Du kannst die Entwicklung auf Ko-fi unterstützen.",
  "donation.action": "Auf Ko-fi unterstützen", "donation.dismiss": "Nicht jetzt",
};

function chooseLocale(stored, preferred) {
  if (stored === "de" || stored === "en") return stored;
  return preferred.some((value) => value.toLowerCase().startsWith("de")) ? "de" : "en";
}

function interpolate(template, values = {}) {
  return template.replace(/\{([a-zA-Z0-9_]+)\}/g, (_, key) => String(values[key] ?? `{${key}}`));
}

function translate(locale, key, values) {
  const dictionary = locale === "de" ? de : en;
  if (!(key in dictionary) && !(key in en)) throw new Error(`Unknown translation key: ${key}`);
  return interpolate(dictionary[key] ?? en[key], values);
}
```

Before this task passes, expand this manifest with every dynamic string that Task 4 will replace;
the identical-key test is the gate. `translate` replaces `{name}` tokens from `values`, falls
back to English for an unknown locale, and throws for an unknown key so missing copy is caught
in development.

The DOM controller must catch `localStorage` access, set `document.documentElement.lang`, hide
inactive `[data-lang]` blocks with the `hidden` attribute, update `aria-pressed` on locale
buttons and apply `data-i18n`/`data-i18n-aria` values. In a browser, the module creates one
controller from `chooseLocale(localStorage.getItem("qrsalvage.locale"), navigator.languages)` at
load. `setLocale` writes only `qrsalvage.locale`. The module exposes its bound `t`, `setLocale`
and `apply` methods alongside the pure
exports on `window.qrLocale`; in CommonJS it exports only deterministic functions and the
controller factory.

- [ ] **Step 4: Allowlist and serve the locale module explicitly**

Add `/locale.js` to `Handler.STATIC` with JavaScript content type and add `locale.js` to
`PAGE_FILES`. Extend the existing static-asset test to request it and assert HTTP 200.

- [ ] **Step 5: Run focused tests and the self-containment build**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_server.py -k "locale_ or static" -v
.venv\Scripts\python.exe scripts\build_site.py
git diff --check
```

Expected: tests pass; the build lists no unexplained runtime URL.

- [ ] **Step 6: Commit localization infrastructure**

```powershell
git add src/qrsalvage/web/locale.js src/qrsalvage/server.py scripts/build_site.py tests/test_server.py
git commit -m "feat(web): add local DE and EN copy"
```

---

### Task 3: Adaptive homepage and Studio shell

**Files:**
- Modify: `src/qrsalvage/web/index.html`
- Modify: `src/qrsalvage/web/style.css`
- Modify: `src/qrsalvage/web/app.js`
- Modify: `src/qrsalvage/server.py`
- Modify: `scripts/build_site.py`
- Modify: `tests/test_server.py`

**Interfaces:**
- Consumes: `window.qrStudioState` and `window.qrLocale` from Tasks 1–2.
- Produces: `dispatchStudio(event)` in `app.js`, the single path for UI phase changes.
- Produces stable elements: `#studioShell`, `#siteHero`, `#studio`, `#modeEasy`, `#modePro`, `#localeDe`, `#localeEn`.
- Preserves every existing ID consumed by `app.js`, especially `#drop`, `#file`, `#workspace`, `#results`, `#photo`, `#metrics`, `#payload`, `#exports`, manual geometry controls and catalogue controls.

- [ ] **Step 1: Write structural and script-order tests for the approved shell**

Add assertions to `tests/test_server.py`:

```python
def test_front_page_has_the_adaptive_studio_shell(running_server):
    host, port = running_server
    connection = http.client.HTTPConnection(host, port, timeout=10)
    connection.request("GET", "/")
    page = connection.getresponse().read().decode("utf-8")
    for marker in (
        'id="studioShell"', 'id="siteHero"', 'id="studio"',
        'id="modeEasy"', 'id="modePro"', 'id="localeDe"', 'id="localeEn"',
        'data-companion-anchor="hero"', 'data-companion-anchor="studio"',
    ):
        assert marker in page
    assert page.index('src="studio-state.js"') < page.index('src="app.js"')
    assert page.index('src="locale.js"') < page.index('src="app.js"')
```

Extend the existing accessibility test to require one `<main id="mainContent">`, a skip link,
visible button labels and `aria-pressed` on both mode and locale controls.

- [ ] **Step 2: Run the shell tests and verify they fail on old markup**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_server.py -k "adaptive_studio_shell or wait_feedback" -v
```

Expected: FAIL on missing new shell IDs.

- [ ] **Step 3: Rebuild `index.html` around the existing functional elements**

Create this semantic order without renaming existing functional IDs:

```html
<a class="skip-link" href="#mainContent" data-i18n="a11y.skip">Skip to the tool</a>
<nav class="site-nav" aria-label="Primary">
  <a class="site-brand" href="index.html" aria-label="qrsalvage home">qrsalvage</a>
  <a href="method.html" data-i18n="nav.method">Method</a>
  <a href="https://github.com/ShadesMaverick/qrsalvage">GitHub</a>
  <a href="legal.html" data-i18n="nav.privacy">Privacy</a>
  <div class="mode-switch" aria-label="Workspace mode">
    <button id="modeEasy" type="button" aria-pressed="true">Easy</button>
    <button id="modePro" type="button" aria-pressed="false">Pro</button>
  </div>
  <div class="locale-switch" aria-label="Language">
    <button id="localeDe" type="button" data-locale="de" aria-pressed="false">DE</button>
    <button id="localeEn" type="button" data-locale="en" aria-pressed="true">EN</button>
  </div>
</nav>
<main id="mainContent">
  <div id="studioShell" class="studio-phase-welcome studio-mode-easy">
    <section id="siteHero" data-companion-anchor="hero">
      <p class="eyebrow" data-i18n="hero.eyebrow">Recover the signal</p>
      <h1 data-i18n="hero.title">A damaged QR code is still data.</h1>
      <p data-i18n="hero.lead">Reconstruct curved, faded and incomplete codes entirely on your device.</p>
      <a class="primary-action" href="#studio" data-i18n="hero.action">Open Signal Studio</a>
    </section>
    <section id="studio" data-companion-anchor="studio">
      <header class="studio-header">
        <p class="eyebrow" data-i18n="studio.eyebrow">Signal Studio</p>
        <h2 data-i18n="studio.title">Reconstruction workspace</h2>
      </header>
      <div id="studioStatus" class="session-strip" role="status" aria-live="polite"></div>
    </section>
  </div>
  <section id="methodSummary">
    <p class="eyebrow">01–03</p><h2 data-i18n="method.title">From damaged image to verified payload</h2>
    <ol><li>Find the grid</li><li>Measure uncertainty</li><li>Verify the reconstruction</li></ol>
  </section>
  <section id="situations"><h2 data-i18n="situations.title">Built for difficult surfaces</h2></section>
  <section id="privacyOpenSource"><h2 data-i18n="privacy.title">Private by construction, open by default</h2></section>
</main>
```

Relocate the existing `#workspace` element, including every child and ID, directly after
`#studioStatus` inside `#studio`; do not recreate or rename its functional controls. Move the
current English and German FAQ entries into `#situations` and render only the selected locale.
Populate `#methodSummary` with the three exact steps above plus the existing method link, and
populate `#privacyOpenSource` with the existing local-processing proof, repository link and legal
link.

Load scripts in this order: `backend.js`, `studio-state.js`, `locale.js`,
`outline-editor.js`, `app.js`. Keep the CSP same-origin-only.

- [ ] **Step 4: Replace the stylesheet with shared Signal Studio layers**

Keep the exact existing tokens and organize `style.css` in this order:

1. tokens/reset/a11y;
2. shared navigation and typography;
3. adaptive hero;
4. Studio toolbar, session strip, canvas, inspector and output;
5. editorial sections, method and legal pages;
6. phase and Easy/Pro visibility rules;
7. responsive breakpoints;
8. one final `prefers-reduced-motion` block.

Use class changes rather than inline styles. `studio-phase-welcome` shows the full hero;
all later phases use the compact hero. At 768 px the inspector stacks below the canvas; at
320 px controls wrap without horizontal page overflow.

- [ ] **Step 5: Wire phase and mode changes through `dispatchStudio`**

At the top of `app.js`, initialize safely from storage and render classes/ARIA from the pure
module:

```javascript
let studioState = window.qrStudioState.createStudioState(readPreference("qrsalvage.mode"));

function dispatchStudio(event) {
  studioState = window.qrStudioState.reduceStudioState(studioState, event);
  const view = window.qrStudioState.viewForState(studioState);
  const shell = $("studioShell");
  shell.className = `${view.phaseClass} ${view.modeClass}`;
  $("modeEasy").setAttribute("aria-pressed", String(studioState.mode === "easy"));
  $("modePro").setAttribute("aria-pressed", String(studioState.mode === "pro"));
}
```

Use guarded `readPreference`/`writePreference`. Dispatch `IMAGES_READY` after accepted bitmaps,
`PREPARING` before backend readiness, `RECOVERY_STARTED` when solve/catalogue begins,
`ASSISTANCE_REQUIRED` when manual finder or outline editing starts,
`RECOVERY_SUCCEEDED` only after result rendering and `RECOVERY_FAILED` in the corresponding
failure path. `resetAll()` dispatches `RESET` after invalidating async owners.

- [ ] **Step 6: Serve and build `studio-state.js` explicitly**

Add `/studio-state.js` to `Handler.STATIC` and `studio-state.js` to `PAGE_FILES`; extend the
static asset and script-order tests.

- [ ] **Step 7: Run homepage behavior and legacy contract tests**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_server.py -k "studio or wait_feedback or success_reveal or async_input or manual" -v
.venv\Scripts\python.exe -m pytest tests\test_repository.py -v
.venv\Scripts\python.exe scripts\build_site.py
git diff --check
```

Expected: all pass and build remains self-contained.

- [ ] **Step 8: Commit the adaptive shell**

```powershell
git add src/qrsalvage/web/index.html src/qrsalvage/web/style.css src/qrsalvage/web/app.js src/qrsalvage/server.py scripts/build_site.py tests/test_server.py
git commit -m "feat(web): build adaptive Signal Studio"
```

---

### Task 4: Complete Easy/Pro behavior and dynamic translations

**Files:**
- Modify: `src/qrsalvage/web/app.js`
- Modify: `src/qrsalvage/web/locale.js`
- Modify: `src/qrsalvage/web/index.html`
- Modify: `src/qrsalvage/web/style.css`
- Modify: `tests/test_server.py`

**Interfaces:**
- Consumes: `window.qrLocale.t(key, values)` and the mode in `studioState`.
- Produces: one localized code path for all user-facing runtime messages.
- Maintains: identical backend calls and payloads in Easy and Pro.

- [ ] **Step 1: Write mode-visibility and no-request-divergence tests**

Add a Node test for `viewForState` and static contract assertions:

```python
def test_easy_and_pro_change_visibility_not_recovery_requests():
    easy = _call_web_module(
        "studio-state.js", "viewForState", {"phase": "recovering", "mode": "easy"}
    )
    pro = _call_web_module(
        "studio-state.js", "viewForState", {"phase": "recovering", "mode": "pro"}
    )
    assert easy["diagnosticsExpanded"] is False
    assert pro["diagnosticsExpanded"] is True
    script = (ROOT / "src" / "qrsalvage" / "web" / "app.js").read_text(encoding="utf-8")
    solve = script[script.index("async function solve") : script.index("/* --- the live view")]
    assert "studioState.mode" not in solve
```

Add a test that the app contains no raw English assignments for the current camera, progress,
solve, catalogue and export status messages; each exact old literal must be absent and its
locale key present.

- [ ] **Step 2: Run focused tests and verify old literals fail the contract**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_server.py -k "easy_and_pro or runtime_messages" -v
```

Expected: FAIL until dynamic copy is routed through locale keys.

- [ ] **Step 3: Finish the symmetric DE/EN runtime dictionary**

Add exact keys for boot (`boot.*`), camera (`camera.*`), input (`input.*`), progress
(`progress.*`), manual geometry (`manual.*`), verdicts (`verdict.*`), catalogue
(`catalogue.*`), export (`export.*`) and clipboard (`clipboard.*`). Replace every visible
literal assignment in `app.js` with `t(key, values)`. Keep payload strings, decoded values,
file names and exception details verbatim.

Use one local alias only:

```javascript
const t = (key, values) => window.qrLocale.t(key, values);
```

Do not build HTML from translated text unless the values pass through `escapeHtml` first.

- [ ] **Step 4: Implement Easy and Pro disclosure without duplicate controls**

Keep one Diagnostics DOM subtree and one set of manual/export controls. CSS uses
`.studio-mode-easy` and `.studio-mode-pro`; JavaScript only updates `hidden`, `open`,
`aria-expanded` and labels when a control genuinely changes availability. Easy keeps the
verdict, current stage and recovery action visible; Pro expands live sizes, heatmap, matrix,
advanced export fields and direct manual geometry entry.

Mode buttons dispatch `SET_MODE`, persist `qrsalvage.mode`, and never call `solve`, `catalogRun`
or backend methods.

- [ ] **Step 5: Test language switching, mode switching and existing recovery tests**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_server.py -k "locale or mode or recovery or catalog or export" -v
.venv\Scripts\python.exe -m ruff check tests\test_server.py
git diff --check
```

Expected: all pass.

- [ ] **Step 6: Commit view density and translated runtime copy**

```powershell
git add src/qrsalvage/web/app.js src/qrsalvage/web/locale.js src/qrsalvage/web/index.html src/qrsalvage/web/style.css tests/test_server.py
git commit -m "feat(web): add Easy and Pro views"
```

---

### Task 5: Pixel companion, contextual hints and Ko-fi success moment

**Files:**
- Create: `src/qrsalvage/web/companion.js`
- Create: `src/qrsalvage/web/axolotl-companion.png`
- Modify: `src/qrsalvage/web/index.html`
- Modify: `src/qrsalvage/web/style.css`
- Modify: `src/qrsalvage/web/app.js`
- Modify: `src/qrsalvage/web/locale.js`
- Modify: `src/qrsalvage/server.py`
- Modify: `scripts/build_site.py`
- Modify: `tests/test_server.py`
- Modify: `tests/test_repository.py`

**Interfaces:**
- Produces: `companionDecision(state, memory) -> {pose, anchor, hintKey, offerDonation, motion}`.
- Produces: `createCompanionController(options) -> {update, dismissHint, destroy}`.
- Consumes: Studio phases plus detail `{assistance: "finders" | "outline" | null, payloadReady: bool, reducedMotion: bool}`.
- Storage keys: `qrsalvage.hints.<hintKey>` and `qrsalvage.motionReduced` in local storage;
  `qrsalvage.donationShown` in session storage.

- [ ] **Step 1: Write pure companion decision tests**

```python
def test_companion_only_offers_kofi_after_a_visible_success_once_per_session():
    success = {"phase": "success", "payloadReady": True, "reducedMotion": False}
    first = _call_web_module("companion.js", "companionDecision", success, {})
    assert first["pose"] == "celebrate"
    assert first["offerDonation"] is True
    again = _call_web_module(
        "companion.js", "companionDecision", success, {"donationShown": True}
    )
    assert again["offerDonation"] is False
    failed = _call_web_module(
        "companion.js", "companionDecision",
        {"phase": "failure", "payloadReady": False, "reducedMotion": False},
        {},
    )
    assert failed["offerDonation"] is False


def test_companion_reduced_motion_is_static_and_hints_are_once_only():
    state = {
        "phase": "assistance", "assistance": "outline",
        "payloadReady": False, "reducedMotion": True,
    }
    first = _call_web_module("companion.js", "companionDecision", state, {})
    assert first["motion"] == "still"
    assert first["hintKey"] == "companion.outline"
    seen = _call_web_module(
        "companion.js", "companionDecision", state,
        {"seenHints": ["companion.outline"]},
    )
    assert seen["hintKey"] is None
```

Add a static contract that `#motionToggle` is a labelled button with `aria-pressed`, and that
an explicit reduced-motion preference can disable animation but can never override an operating
system request to reduce motion.

- [ ] **Step 2: Run the decision tests and verify they fail**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_server.py -k "companion_" -v
```

Expected: FAIL because `companion.js` does not exist.

- [ ] **Step 3: Implement the pure decisions before any DOM animation**

Use this deterministic phase map:

```javascript
const POSE_FOR_PHASE = Object.freeze({
  welcome: ["idle", "hero"], ready: ["point", "studio"],
  preparing: ["inspect", "progress"], recovering: ["walk", "canvas"],
  assistance: ["point", "manual"], success: ["celebrate", "result"],
  failure: ["inspect", "recovery"],
});
```

`offerDonation` is true only for `success && payloadReady && !memory.donationShown`.
Assistance hints are keyed by assistance kind and suppressed by `memory.seenHints`.
`reducedMotion` always returns `motion: "still"`.

- [ ] **Step 4: Create and validate the local companion sprite**

Use the `imagegen` skill with `src/qrsalvage/web/axolotl.png` as the visual reference. Produce
one transparent horizontal PNG sprite sheet with six equal square frames in this order:
`idle`, `walk-a`, `walk-b`, `point`, `inspect`, `celebrate`. Preserve the existing pink
axolotl, finder-pattern fragments, hard pixel edges and transparent background; do not add text,
shadows or a new mascot design.

Add a repository test using Pillow:

```python
def test_companion_sprite_has_six_square_transparent_frames():
    from PIL import Image
    path = ROOT / "src" / "qrsalvage" / "web" / "axolotl-companion.png"
    with Image.open(path) as image:
        assert image.mode == "RGBA"
        assert image.width == image.height * 6
        assert image.getextrema()[3][0] == 0
```

Visually compare every frame at 1× and 4× nearest-neighbor scale before accepting the asset.

- [ ] **Step 5: Add one anchored companion layer and DOM controller**

Add one `#companion` after `#studioShell`, with an `aria-hidden` sprite and a separate,
initially hidden hint element. Mark hero, studio, progress, canvas, manual, result and recovery
with `data-companion-anchor`.

The controller reads anchor rectangles only when the target changes, animates translation with
the Web Animations API, uses `background-position` plus `steps()` for frames, and uses
`IntersectionObserver` for long-page section changes. The layer has `pointer-events: none`;
only visible bubble buttons opt back into pointer events. `destroy()` disconnects observers and
cancels animations.

Implement the controller around this stable surface:

```javascript
function createCompanionController({ root, bubble, anchors, t, local, session, media }) {
  let currentAnimation = null;
  let observer = null;

  function update(state) {
    const reducedMotion = media.matches || local.get("qrsalvage.motionReduced") === "true";
    const decision = companionDecision({ ...state, reducedMotion }, readMemory(local, session));
    renderDecision(decision);
    return decision;
  }

  function dismissHint(key) {
    local.set(`qrsalvage.hints.${key}`, "true");
    bubble.hidden = true;
  }

  function destroy() {
    currentAnimation?.cancel();
    observer?.disconnect();
  }

  return { update, dismissHint, destroy };
}
```

`local` and `session` are guarded adapters whose `get` and `set` methods absorb storage
exceptions. Add `#motionToggle` to the navigation overflow: pressing it can set reduction to
true or false, updates `aria-pressed`, and re-renders the current pose. The OS media query always
wins when it requests reduced motion.

- [ ] **Step 6: Connect real events and replace the existing donation placement**

Call `companion.update` after every `dispatchStudio`. Pass `assistance: "finders"` or
`"outline"` from the existing manual entry handlers. Pass `payloadReady: true` only after
`renderAnswer` has inserted the successful payload and moved focus to the result heading.

Remove the always-present success-card donation ask. The new dismissible bubble renders the
same literal URL `https://ko-fi.com/shadesmaverick` as a normal `<a target="_blank"
rel="noopener noreferrer">`; it does not fetch, iframe or script Ko-fi.

- [ ] **Step 7: Add serving, build and motion-safety contracts**

Allowlist `companion.js` and `axolotl-companion.png`; add both to `PAGE_FILES`. Extend tests to
assert script order `locale.js` → `companion.js` → `app.js`, `pointer-events: none`, the
Reduced Motion static rules, no donation on failure and one session-storage flag.

- [ ] **Step 8: Run companion, server and build tests**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_server.py -k "companion or kofi or success or reduced_motion" -v
.venv\Scripts\python.exe -m pytest tests\test_repository.py -v
.venv\Scripts\python.exe scripts\build_site.py
git diff --check
```

Expected: all pass; the URL audit explains Ko-fi only as a user-clicked link.

- [ ] **Step 9: Commit the companion**

```powershell
git add src/qrsalvage/web/companion.js src/qrsalvage/web/axolotl-companion.png src/qrsalvage/web/index.html src/qrsalvage/web/style.css src/qrsalvage/web/app.js src/qrsalvage/web/locale.js src/qrsalvage/server.py scripts/build_site.py tests/test_server.py tests/test_repository.py
git commit -m "feat(web): add Axolotl companion"
```

---

### Task 6: Signal Manual and bilingual legal page

**Files:**
- Modify: `src/qrsalvage/web/method.html`
- Modify: `src/qrsalvage/web/legal.html`
- Modify: `src/qrsalvage/web/style.css`
- Modify: `src/qrsalvage/web/locale.js`
- Modify: `tests/test_repository.py`
- Modify: `tests/test_server.py`

**Interfaces:**
- Consumes: shared `.site-nav`, `.manual-*`, `.legal-*`, locale buttons and `locale.js` page binding.
- Produces: the same eight method anchors `known`, `levels`, `posterior`, `grid`, `search`, `probe`, `rs`, `limits`.
- Preserves: every legal operator detail and required external legal/source link verbatim.

- [ ] **Step 1: Write shared-shell, anchor and legal-preservation tests**

```python
def test_method_and_legal_share_navigation_and_locale_without_loading_the_backend():
    for name in ("method.html", "legal.html"):
        page = (ROOT / "src" / "qrsalvage" / "web" / name).read_text(encoding="utf-8")
        assert 'class="site-nav"' in page
        assert 'src="locale.js"' in page
        assert 'data-locale="de"' in page and 'data-locale="en"' in page
        assert 'src="backend.js"' not in page
        assert 'src="app.js"' not in page


def test_signal_manual_preserves_all_method_sections_and_figures():
    page = (ROOT / "src" / "qrsalvage" / "web" / "method.html").read_text(encoding="utf-8")
    for section in ("known", "levels", "posterior", "grid", "search", "probe", "rs", "limits"):
        assert f'id="{section}"' in page
    for figure in ("fig-known.svg", "fig-levels.svg", "fig-posterior.svg", "fig-probe.svg", "fig-rs.svg"):
        assert figure in page
```

Keep the existing legal assertions for name, address, placeholder absence, device-local processing and
host privacy link.

- [ ] **Step 2: Run the page tests and verify the shared shell fails**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_repository.py tests\test_server.py -k "method or legal or signal_manual" -v
```

Expected: FAIL on missing locale/shared-shell markup.

- [ ] **Step 3: Rebuild `method.html` as the Signal Manual**

Remove its inline design system. Use the shared stylesheet and navigation. Keep formulas,
tables, SVGs, measured values and anchor IDs exactly where they belong. Add one compact sticky
section rail on desktop and a wrapping jump list on mobile. For each prose group, render
semantic sibling blocks `data-lang="en"` and `data-lang="de"`; figures and formulas remain one
shared element with localized caption spans.

Use this structure for the shell and repeat the article section pattern for all eight preserved
anchors:

```html
<body class="manual-page"
      data-title-en="Signal Manual · qrsalvage"
      data-title-de="Signal-Handbuch · qrsalvage"
      data-description-en="How qrsalvage reconstructs damaged QR codes."
      data-description-de="Wie qrsalvage beschädigte QR-Codes rekonstruiert.">
  <nav class="site-nav" aria-label="Primary navigation">
    <a class="site-brand" href="index.html">qrsalvage</a>
    <a href="index.html#studio"><span data-lang="en">Studio</span><span data-lang="de" hidden>Studio</span></a>
    <a href="method.html" aria-current="page"><span data-lang="en">Method</span><span data-lang="de" hidden>Methode</span></a>
    <a href="https://github.com/ShadesMaverick/qrsalvage">GitHub</a>
    <a href="legal.html"><span data-lang="en">Privacy</span><span data-lang="de" hidden>Datenschutz</span></a>
    <div class="locale-switch" aria-label="Language">
      <button type="button" data-locale="de">DE</button>
      <button type="button" data-locale="en">EN</button>
    </div>
  </nav>
  <main class="manual-layout">
    <aside class="manual-rail" aria-label="Manual sections">
      <a href="#known"><span data-lang="en">Known structure</span><span data-lang="de" hidden>Bekannte Struktur</span></a>
      <a href="#levels"><span data-lang="en">Brightness fields</span><span data-lang="de" hidden>Helligkeitsfelder</span></a>
      <a href="#posterior"><span data-lang="en">Module probability</span><span data-lang="de" hidden>Modulwahrscheinlichkeit</span></a>
      <a href="#grid"><span data-lang="en">Grid fitting</span><span data-lang="de" hidden>Gitteranpassung</span></a>
      <a href="#search"><span data-lang="en">Search space</span><span data-lang="de" hidden>Suchraum</span></a>
      <a href="#probe"><span data-lang="en">Ordered probing</span><span data-lang="de" hidden>Geordnetes Nachtasten</span></a>
      <a href="#rs"><span data-lang="en">Reed–Solomon</span><span data-lang="de" hidden>Reed–Solomon</span></a>
      <a href="#limits"><span data-lang="en">Limits</span><span data-lang="de" hidden>Grenzen</span></a>
    </aside>
    <article class="manual-content">
      <section id="known">
        <h1><span data-lang="en">The known cells</span><span data-lang="de" hidden>Die bekannten Zellen</span></h1>
      </section>
    </article>
  </main>
  <script src="locale.js"></script>
</body>
```

For each current chapter, move its existing English prose, table, formula and figure below the
matching section heading without changing technical values. Add a German sibling for each prose
paragraph and caption. Use the chapter names shown in the rail; translate technical terms
consistently as `module` → `Modul`, `erasure` → `Auslassung`, `finder pattern` →
`Suchmuster`, and leave formulas and symbols untranslated. The five existing SVG filenames stay
unchanged and occur only once each.

Permit only `locale.js` in the page CSP: `script-src 'self'`; retain `connect-src 'none'` and
do not load backend, worker or companion code.

- [ ] **Step 4: Rebuild `legal.html` in the quiet shared layout**

Use the shared nav and narrow `.legal-page` column. Keep the German text byte-for-meaning
unchanged. Add a clearly labelled English translation in `data-lang="en"`; include the sentence
“The German version is authoritative.” The operator name, physical address, email, GitHub
Privacy Statement link and repository link must appear in both blocks. No companion markup or
motion is present.

```html
<main class="legal-page">
  <section data-lang="de">
    <h1>Impressum &amp; Datenschutz</h1>
  </section>
  <section data-lang="en" hidden>
    <h1>Legal notice &amp; privacy</h1>
    <p class="legal-authority">The German version is authoritative.</p>
  </section>
</main>
```

Move every existing German node after its `h1` into the German section, removing only the old
inline `style` attribute on the final backlink. Translate each heading, paragraph, definition-list
label and backlink into an English counterpart in the same order. Preserve `Fabian Marius
Freitag`, `Wilhelmstraße 9/1`, `73779 Deizisau`, `f.freitag@ik.me`, both GitHub URLs and all cited
legal article numbers exactly; the German section is the authoritative source.

Set the exact policy in both pages:

```html
<meta http-equiv="Content-Security-Policy"
      content="default-src 'self'; img-src 'self' data: blob:; style-src 'self'; script-src 'self'; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">
```

- [ ] **Step 5: Add translated navigation/metadata hooks and responsive styles**

Use `data-title-en`, `data-title-de`, `data-description-en` and `data-description-de` on each
page body; `locale.js` updates `document.title` and the description meta on selection. Method
figures may scroll inside their plot at 320 px but the page itself must not overflow.

- [ ] **Step 6: Run page, CSP and legal tests**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_repository.py tests\test_server.py -k "method or legal or csp or locale" -v
git diff --check
```

Expected: all pass.

- [ ] **Step 7: Commit the remaining pages**

```powershell
git add src/qrsalvage/web/method.html src/qrsalvage/web/legal.html src/qrsalvage/web/style.css src/qrsalvage/web/locale.js tests/test_repository.py tests/test_server.py
git commit -m "feat(web): redesign method and legal pages"
```

---

### Task 7: Architecture documentation and static delivery audit

**Files:**
- Modify: `docs/ARCHITECTURE.md`
- Modify: `src/qrsalvage/server.py`
- Modify: `scripts/build_site.py`
- Modify: `tests/test_server.py`
- Modify: `tests/test_repository.py`

**Interfaces:**
- Documents: `studio-state.js`, `locale.js`, `companion.js` and their one-way relationship to `app.js`.
- Verifies: exact same production asset set in the wheel, loopback server and Pages build.

- [ ] **Step 1: Add a single inventory contract test**

Read `Handler.STATIC` and `PAGE_FILES` in a test and require these files in both:

```python
expected = {
    "studio-state.js", "locale.js", "companion.js", "axolotl-companion.png",
    "outline-editor.js", "app.js", "style.css", "axolotl.png",
}
assert expected <= set(PAGE_FILES)
assert {f"/{name}" for name in expected} <= set(Handler.STATIC)
```

Also assert `pyproject.toml` package-data globs still cover `.html`, `.css`, `.js`, `.png` and
`.svg` without introducing a broad recursive include.

- [ ] **Step 2: Run the inventory test and fix any omissions**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_server.py tests\test_repository.py -k "inventory or static_build" -v
```

Expected: PASS after any missing explicit entries are added.

- [ ] **Step 3: Update architecture documentation**

In `docs/ARCHITECTURE.md`, replace the three-file UI description with the exact browser-module
map. Document this one-way flow:

```text
backend progress + user actions
        -> app.js
        -> studio-state.js (pure phase/mode)
        -> companion.js (presentation only)
        -> DOM/CSS

locale.js -> visible and accessible copy only
```

State explicitly that no UI module may change API payloads or import the core and that the
loopback and worker backends remain interchangeable.

- [ ] **Step 4: Run packaging, server and build audits**

```powershell
.venv\Scripts\python.exe -m pytest tests\test_server.py tests\test_repository.py -v
.venv\Scripts\python.exe scripts\build_site.py
$wheel = Get-ChildItem site -Filter 'qrsalvage-*.whl' | Select-Object -First 1
.venv\Scripts\python.exe -m zipfile -l $wheel.FullName
git diff --check
```

Inspect the built wheel and verify all four new production assets are present under
`qrsalvage/web/`; never touch fixtures or unrelated files.

- [ ] **Step 5: Commit contracts and documentation**

```powershell
git add docs/ARCHITECTURE.md src/qrsalvage/server.py scripts/build_site.py tests/test_server.py tests/test_repository.py
git commit -m "docs: map Signal Studio browser modules"
```

---

### Task 8: Full verification, browser QA and publication

**Files:**
- Modify only if verification exposes a defect; any fix receives its own failing test and commit.

**Interfaces:**
- Consumes: the complete approved implementation.
- Produces: verified local build, green CI, successful Pages deployment and content-identical live assets.

- [ ] **Step 1: Run all local static checks**

```powershell
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m ruff format --check .
.venv\Scripts\python.exe -m mypy
.venv312\Scripts\python.exe -m mypy
git diff --check
```

Expected: all exit 0.

- [ ] **Step 2: Run the complete test suite**

```powershell
.venv\Scripts\python.exe -m pytest
```

Expected: all tests, including image regression, pass. Do not report a success count until the
command finishes and prints it.

- [ ] **Step 3: Build and serve the exact Pages artifact**

```powershell
.venv\Scripts\python.exe scripts\build_site.py
.venv\Scripts\python.exe -m http.server 8873 --directory site --bind 127.0.0.1
```

Use a dedicated port and stop only that process after QA.

- [ ] **Step 4: Perform browser QA at required widths and states**

Verify at 1440, 1024, 768, 375 and 320 CSS pixels:

- welcome → photo selection → preparing → recovering → assistance → success → reset;
- Easy/Pro switch preserves photo, geometry and result;
- automatic German selection, manual DE/EN switch and persistence;
- keyboard-only photo selection, mode, locale, manual outline, copy and export;
- 200% text zoom and no page-level horizontal overflow;
- reduced motion shows static companion and static success state;
- mobile portrait and landscape keep all primary targets at least 44 px;
- public `fixtures/engraved-curved-hard.png` recovers through the built site;
- Ko-fi appears after payload, once per session, is dismissible and is absent on failure;
- method and legal pages have shared navigation, correct active language and readable figures.

Do not use private fixtures or expose decoded private payloads in screenshots/logs.

- [ ] **Step 5: Request final code review and fix only evidence-backed findings**

Use `superpowers:requesting-code-review` over the complete branch against its base. For every
accepted defect, first add the smallest reproducing test, then fix, rerun the focused test and
commit. Re-run Steps 1–4 after the final fix.

- [ ] **Step 6: Push the verified commit to the feature branch and `main`**

```powershell
git push origin HEAD:harden-declared-invariants
git push origin HEAD:main
```

This publication is authorized by the standing project requirement that the completed local
site also become the online site. Push only the verified feature commits; unrelated dirty files
remain unstaged.

- [ ] **Step 7: Monitor CI and Pages to completion**

Use the GitHub Actions API for the exact `git rev-parse HEAD`. Require every CI job to conclude
`success`, then require the resulting Pages workflow `build` and `deploy` jobs to conclude
`success`. A queued or in-progress run is not completion.

- [ ] **Step 8: Verify the public deployment against the local build**

Fetch these cache-busted URLs from `https://shadesmaverick.github.io/qrsalvage/`:

```text
index.html
style.css
studio-state.js
locale.js
companion.js
app.js
method.html
legal.html
axolotl-companion.png
```

Require HTTP 200 and compare normalized-text SHA-256 for text files and byte SHA-256 for the
PNG against `site/`. Finally perform one live desktop and 375-pixel smoke test of language,
mode and photo selection.
