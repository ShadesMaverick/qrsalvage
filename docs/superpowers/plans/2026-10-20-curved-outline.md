# Curved QR Outline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a person place four QR corners and bend each edge so that the real recovery pipeline samples that curved outline.

**Architecture:** A `CurvedOutline` value converts the public clockwise corner/midpoint contract into the core's existing homography-plus-eight-bow-parameter model. The API validates and routes a single-image outline through the same pipeline, while progress events expose the fitted curves. The static Canvas UI edits the eight handles with Pointer Events and sends the shared API contract.

**Tech Stack:** Python 3.11/3.12, NumPy, OpenCV, pytest, plain HTML/CSS/JavaScript Canvas, Pyodide worker

**Spec:** `docs/superpowers/specs/2026-10-20-curved-outline-design.md`

## Global Constraints

- Nothing under `src/qrsalvage/core/` imports CLI, server, or UI code or writes to stdout.
- A module remains black, white, or unknown; no layer may collapse the posterior to two states.
- There is no runtime network access, and photographs or decoded text never leave the project.
- No dependency or virtual-environment change is allowed.
- `fixtures/` is never overwritten or deleted.
- All identifiers, file names, docstrings, comments, tests, errors, and UI copy added by this plan are English.
- Module coordinates are `(row, col)` and pixel coordinates are `(x, y)`.
- Public outline order is corners `top-left, top-right, bottom-right, bottom-left` and edge midpoints `top, right, bottom, left`.
- The existing three-finder manual route remains supported and unchanged.
- Manual outlines apply only to one photograph and are mutually exclusive with `finder_points`.
- Every task follows red-green TDD and commits only its named files.

---

### Task 1: Represent and score a curved outline in the pure core

**Files:**
- Modify: `src/qrsalvage/core/geometry.py`
- Modify: `tests/test_solver.py`

**Interfaces:**
- Consumes: the existing internal corner order and `_bowed_warp` bow order `(top, bottom, left, right)` as x/y pairs.
- Produces: `CurvedOutline`, `outline_midpoints(corners, bow)`, `bow_from_midpoints(corners, midpoints)`, `fit_outline(...)`, and a `GridFit.bow` value preserved by `refine_bow`.

- [ ] **Step 1: Write failing geometry contract tests**

Add tests that import the new interfaces and assert the public order and round trip:

```python
def test_outline_midpoints_round_trip_through_existing_bow_model():
    corners = np.array([[10.0, 20.0], [210.0, 18.0], [7.0, 225.0], [218.0, 222.0]])
    bow = np.array([0.0, -8.0, 0.0, 7.0, -6.0, 0.0, 9.0, 0.0])
    midpoints = outline_midpoints(corners, bow)
    assert np.allclose(bow_from_midpoints(corners, midpoints), bow, atol=1e-6)
    assert midpoints.shape == (4, 2)
```

Add a second test using a synthetic curved image. Build a clockwise `CurvedOutline` from the known rendered code bounds, call `fit_outline`, choose the best fit, call `refine_bow`, and assert that its `posterior.shape` matches `(modules, modules)`, its `bow` is finite, and its known-cell error count does not increase during bow refinement. Task 2 owns the end-to-end recovery assertion once `solve` accepts this interface.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='src'; ..\..\.venv\Scripts\python.exe -m pytest tests\test_solver.py -k "outline or bow" -q
```

Expected: collection fails because `CurvedOutline`, `outline_midpoints`, `bow_from_midpoints`, or `fit_outline` does not exist.

- [ ] **Step 3: Add the curved-outline value and conversions**

Implement these exact public interfaces in `geometry.py`:

```python
@dataclass(frozen=True)
class CurvedOutline:
    """Four clockwise QR corners and the top/right/bottom/left curve midpoints."""

    corners: np.ndarray
    edge_midpoints: np.ndarray


def outline_midpoints(corners: np.ndarray, bow: np.ndarray | None) -> np.ndarray:
    """Return actual top/right/bottom/left points at the middle of each curved edge."""


def bow_from_midpoints(corners: np.ndarray, midpoints: np.ndarray) -> np.ndarray:
    """Translate actual top/right/bottom/left midpoint positions to the eight bow scalars."""
```

Use a unit-square-to-image homography to project `(0.5, 0)`, `(1, 0.5)`, `(0.5, 1)`, and `(0, 0.5)`. Add/subtract bow pairs with the mapping top `[0:2]`, right `[6:8]`, bottom `[2:4]`, left `[4:6]`. Reject malformed NumPy shapes with `ValueError` inside `CurvedOutline.__post_init__`.

- [ ] **Step 4: Preserve bow state in scored fits**

Append an optional field without breaking existing constructors:

```python
@dataclass(frozen=True)
class GridFit:
    # existing fields stay in their current order
    bow: np.ndarray | None = None
```

Give `_score` an optional `bow` parameter, copy it into `GridFit`, and add:

```python
def evaluate_bowed(
    gray: np.ndarray,
    corners: np.ndarray,
    bow: np.ndarray,
    modules: int,
    scale: int,
    known_dark: np.ndarray,
    known_light: np.ndarray,
) -> GridFit:
    warped = _bowed_warp(gray, corners, bow, modules, scale)
    return _score(warped, corners, modules, scale, known_dark, known_light, bow=bow)
```

Start `refine_bow` from `fit.bow.copy()` when present, otherwise eight zeros; every candidate score must retain its candidate bow.

- [ ] **Step 5: Fit every candidate size from the manual outline**

Implement:

```python
def fit_outline(
    gray: np.ndarray,
    outline: CurvedOutline,
    sizes: Sequence[int],
    start_delta: float = 12.0,
    on_step: Callable[[GridFit], None] | None = None,
) -> list[GridFit]:
```

Import `Sequence` from `collections.abc`. Convert clockwise corners to internal order with `outline.corners[[0, 1, 3, 2]]`. For every valid module size supplied by the pipeline, call existing `refine_corners`, derive a bow from the supplied edge midpoints and the refined corners, score with `evaluate_bowed`, append the curved score, and report it through `on_step`. Do not import the pipeline's `DEFAULT_SIZES` into the pure geometry module and do not run the expensive bow descent for every version; `solve` supplies the sizes and refines only the chosen winner.

- [ ] **Step 6: Run focused tests and commit**

Run:

```powershell
$env:PYTHONPATH='src'; ..\..\.venv\Scripts\python.exe -m pytest tests\test_solver.py -k "outline or bow" -q
$env:PYTHONPATH='src'; ..\..\.venv\Scripts\python.exe -m pytest tests\test_policy.py tests\test_solver.py -m "not regression" -q
```

Expected: both commands pass.

Commit:

```powershell
git add src/qrsalvage/core/geometry.py tests/test_solver.py
git commit -m "feat(core): fit curved outline hints"
```

---

### Task 2: Route and validate outlines through the shared API

**Files:**
- Modify: `src/qrsalvage/core/pipeline.py`
- Modify: `src/qrsalvage/api.py`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `tests/test_server.py`
- Modify: `tests/test_worker_bridge.py`

**Interfaces:**
- Consumes: Task 1's `CurvedOutline`, `fit_outline`, `outline_midpoints`, and bow-preserving `refine_bow`.
- Produces: optional `outline: CurvedOutline | None` on `core.pipeline.solve`, validated JSON key `outline` in `solve_payload`, and `grid.edge_midpoints` progress data in original-image pixel coordinates.

- [ ] **Step 1: Write failing API and progress tests**

Add an API test that synthesizes a readable curved QR, supplies this exact shape, and checks recovery:

```python
outline = {
    "corners": [
        {"x": float(x), "y": float(y)}
        for x, y in clockwise_corners
    ],
    "edge_midpoints": [
        {"x": float(x), "y": float(y)}
        for x, y in edge_midpoints
    ],
}
answer = solve_payload({"image": _data_url(photo), "outline": outline})
assert answer["ok"] is True
assert answer["text"] == TEXT
```

Capture progress events through `solve_payload` and assert every emitted `grid` event has four `corners` and four `edge_midpoints`. Add parametrized invalid cases for missing arrays, wrong lengths, strings, NaN/Infinity, simultaneous `finder_points`, and `images` containing two photographs. Each must return `ok is False` with an English failure naming the outline problem.

Extend `test_worker_bridge.py` to assert the worker forwards `outline` unchanged through the existing JSON bridge and does not create a second browser-only contract.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='src'; ..\..\.venv\Scripts\python.exe -m pytest tests\test_server.py tests\test_worker_bridge.py -k outline -q
```

Expected: the valid request ignores `outline`, invalid requests are accepted, or progress lacks `edge_midpoints`.

- [ ] **Step 3: Validate the JSON contract in the API shell**

Parse the public shape only after the image is decoded so dimensions are available:

```python
raw_outline = payload.get("outline")
outline: CurvedOutline | None = None
if raw_outline is not None:
    if len(images) != 1:
        return {"ok": False, "failure": "a manual outline applies to one photograph only"}
    if payload.get("finder_points"):
        return {"ok": False, "failure": "use either finder points or a manual outline, not both"}
```

Require a dict with exactly four point dicts in `corners` and `edge_midpoints`; convert x/y to floats and require all values finite. Construct NumPy arrays and `CurvedOutline`. Keep this validation in `api.py`, never in the library-pure geometry module.

- [ ] **Step 4: Add an outline preparation and fit path**

Add `outline: CurvedOutline | None = None` to `solve` and `_attempt`. Implement a private preparation function that crops around all eight handles with a 15 percent side-length margin, rescales the average outer side to the working module range using the middle default size, preprocesses the region, and returns a transformed `CurvedOutline` plus `(offset_x, offset_y, factor)`.

When an outline is present, `_attempt` calls `fit_outline` instead of finder detection. It emits `grid` progress with:

```python
{
    "corners": original_space_corners,
    "edge_midpoints": original_space_midpoints,
}
```

Skip the external direct decoder, finder-count failure, anchor sweep, and flat coarse restart for an outline. Keep polarity comparison. Refine only the selected winner through `refine_bow`; because Task 1 preserved the seed bow, descent begins at the user's curves. Extend crop shifting to both corner and midpoint lists.

- [ ] **Step 5: Pass the validated outline to the core and document the route**

Pass `outline=outline` only on the single-image call to `solve`. Update `docs/ARCHITECTURE.md` so the data-flow diagram and geometry seam name the manual clockwise outline, API validation, and conversion to the existing per-edge bow model.

- [ ] **Step 6: Run contract tests and commit**

Run:

```powershell
$env:PYTHONPATH='src'; ..\..\.venv\Scripts\python.exe -m pytest tests\test_server.py tests\test_worker_bridge.py tests\test_contracts.py -q
$env:PYTHONPATH='src'; ..\..\.venv\Scripts\python.exe -m mypy
```

Expected: both commands pass.

Commit:

```powershell
git add src/qrsalvage/core/pipeline.py src/qrsalvage/api.py docs/ARCHITECTURE.md tests/test_server.py tests/test_worker_bridge.py
git commit -m "feat(api): accept curved outline hints"
```

---

### Task 3: Build the touch-friendly Canvas outline editor

**Files:**
- Modify: `src/qrsalvage/web/index.html`
- Modify: `src/qrsalvage/web/style.css`
- Modify: `src/qrsalvage/web/app.js`
- Modify: `tests/test_server.py`

**Interfaces:**
- Consumes: Task 2's JSON `outline` and progress `edge_midpoints`, both in public clockwise order.
- Produces: `Mark the QR outline`, four ordered corner handles, four draggable edge handles, `Recover with this outline`, and curved live/persisted grid drawing.

- [ ] **Step 1: Write a failing served-asset test**

Fetch `/`, `/style.css`, and `/app.js`. Assert the page contains `outlineRetry` and `outlineSolve`; CSS contains `.outline-editing` with `touch-action: none`; JavaScript contains `pointerdown`, `setPointerCapture`, `edge_midpoints`, `quadraticCurveTo`, and an `outline:` payload with `corners` and `edge_midpoints`. Assert the instructions include the ordered English corner names.

- [ ] **Step 2: Run the web test and verify RED**

Run:

```powershell
$env:PYTHONPATH='src'; ..\..\.venv\Scripts\python.exe -m pytest tests\test_server.py -k outline_editor -q
```

Expected: `outlineRetry` is absent.

- [ ] **Step 3: Add explicit controls and touch styling**

Add under the input canvas:

```html
<button id="outlineRetry" class="hidden">Mark the QR outline</button>
<button id="outlineSolve" class="hidden">Recover with this outline</button>
```

Use the existing Cancel button for both manual modes. Add `.outline-editing { touch-action: none; }` and visible cursor/handle states without adding animation. Controls must remain usable at 320 CSS pixels and use existing button styles.

- [ ] **Step 4: Implement the four-corner editor state**

Add state for `outlineEditing`, `outlineCorners`, `outlineMidpoints`, and `outlineDrag`. Entering the mode clears finder picking and asks for top left, top right, bottom right, bottom left in that order. Pointer coordinates use the same CSS-to-canvas-to-image conversion as finder clicks.

After the fourth corner, initialize midpoints as the mean of adjacent corners. On corner drag, apply the full delta to that corner and half the delta to its previous and next edge midpoints. On midpoint drag, update only that midpoint. Use a touch hit radius of at least 18 CSS pixels and call `setPointerCapture` during a drag.

- [ ] **Step 5: Draw the editable and fitted curves**

For each clockwise edge from `start` to `end` through actual midpoint `middle`, compute the Canvas quadratic control point:

```javascript
const controlX = 2 * middle.x - (start.x + end.x) / 2;
const controlY = 2 * middle.y - (start.y + end.y) / 2;
ctx.quadraticCurveTo(controlX * scale, controlY * scale, end.x * scale, end.y * scale);
```

Draw numbered corner rings and smaller diamond midpoint handles over the photograph. Change `liveGrid`/`settledGrid` entries from bare corner arrays to `{ corners, edgeMidpoints }`; straight events remain drawable by deriving default midpoints. `grid.edge_midpoints` must bend the visible live and final outline.

- [ ] **Step 6: Send, reset, and offer the outline correctly**

Extend `solve` so the backend request contains:

```javascript
outline: outlineHint ? {
  corners: outlineHint.corners,
  edge_midpoints: outlineHint.edgeMidpoints,
} : null,
```

Show both manual choices only for a failed single photograph. Keep finder marking unchanged. The outline recovery button freezes editing and calls solve; cancel, reset, new files, catalogue mode, success, and failure must not leak stale drag state into the next run. Preserve the submitted outline while its solve is live so the user sees the exact starting geometry.

- [ ] **Step 7: Run web tests, syntax check, and commit**

Run:

```powershell
$env:PYTHONPATH='src'; ..\..\.venv\Scripts\python.exe -m pytest tests\test_server.py tests\test_worker_bridge.py -q
node --check src/qrsalvage/web/app.js
```

Expected: both commands pass.

Commit:

```powershell
git add src/qrsalvage/web/index.html src/qrsalvage/web/style.css src/qrsalvage/web/app.js tests/test_server.py
git commit -m "feat(web): edit curved QR outlines"
```

---

### Task 4: Verify the complete feature and publication artifact

**Files:**
- Modify only if a verification finding requires a reviewed fix in the files above.

**Interfaces:**
- Consumes: Tasks 1-3 as one browser-to-core flow.
- Produces: a self-contained static site whose manual curved outline produces the same result contract as the local server.

- [ ] **Step 1: Run all static checks and both Python type environments**

Run:

```powershell
$env:PYTHONPATH='src'; ..\..\.venv\Scripts\python.exe -m ruff check .
$env:PYTHONPATH='src'; ..\..\.venv\Scripts\python.exe -m ruff format --check .
$env:PYTHONPATH='src'; ..\..\.venv\Scripts\python.exe -m mypy
$env:PYTHONPATH='src'; ..\..\.venv312\Scripts\python.exe -m mypy
git diff --check
```

Expected: every command exits zero.

- [ ] **Step 2: Build and inspect the static site**

Run:

```powershell
$env:PYTHONPATH='src'; ..\..\.venv\Scripts\python.exe scripts\build_site.py
```

Expected: the self-containment audit accounts for every absolute URL and the generated `site/app.js` contains the `outline` payload and Pointer Event editor.

- [ ] **Step 3: Exercise the editor in a real browser**

Serve `site/` on `127.0.0.1:8833`, load a public fixture, enter outline mode, place four corners, drag all four edge handles using Pointer Events, start recovery, and verify the visible fitted curve follows the dragged handles. Repeat at a 320-pixel viewport and with reduced motion. Save no private photograph or recovered payload.

- [ ] **Step 4: Run the complete suite**

Run:

```powershell
$env:PYTHONPATH='src'; ..\..\.venv\Scripts\python.exe -m pytest
```

Expected: all collected tests pass with zero failures.

- [ ] **Step 5: Record final verification**

Do not create a feature-code commit unless a reviewed verification fix was required. Record exact command outputs in the SDD report and hand the entire branch to the final independent reviewer.
