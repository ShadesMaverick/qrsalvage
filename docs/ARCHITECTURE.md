# Architecture

One page, so a newcomer can hold the whole thing in their head before opening a file. The
*why* behind every design decision lives in the docstrings of the module it concerns — they
are the most valuable part of this codebase, and this page is only the map to them.

## The idea in one paragraph

A QR code carries a few hundred cells whose correct value is fixed by the standard — finders,
separators, timing, alignment. qrsalvage treats them as a built-in calibration target: the
grid, the version, the polarity and the brightness model are all *searched* and *scored*
against those known cells instead of estimated and trusted. Every module then gets a
probability rather than a verdict, cells that stay in doubt become Reed-Solomon *erasures*
(worth twice an error), and an outside decoder acts as the exact oracle that says valid or
not valid. Nothing is believed that can be measured.

The interactive explainer of exactly this pipeline: `qrsalvage serve`, then `/method`.

## Data flow

```
photograph(s)
   │  preprocess.py      illumination correction, binarisation
   ▼
finder candidates       geometry.py + scanfinder.py   (two detectors, merged;
   │                     an implausible triple additionally tries its best pair)
   ▼
grid per candidate size  geometry.py    coordinate descent on the known cells,
   │                                    then a per-edge bow (8 parameters, Coons-style)
   │                                    for curved and domed surfaces
   ▼
probability per module   sampling.py    two brightness fields + per-cell uncertainty;
   │                                    featureless patches damped towards unknown
   │                                    (fuse_images in ensemble.py merges photographs here)
   ▼
three-state matrix       matrix.py      dark / light / unknown  ← the core invariant
   │
   ▼
decode chain             pipeline.py:_decode_chain
   1. direct decode          decoding.py → oracle.py
   2. erasure ladder         repair.py   (least reliable codewords erased, count climbing)
   3. scattered erasures     repair.py   (arbitrary sets, ordered by total doubt)
   4. ordered cell probe     decoding.py (cheapest doubts first, oracle as judge)
   ▼
text  (+ re-encoded clean matrix, exports, catalogue)
```

`pipeline.py` composes all of this and decides nothing itself. `qrspec.py`, `structure.py`
and `layout.py` are the tables and placement rules of ISO/IEC 18004 — the only
symbology-specific modules; `galois.py` is GF(256) Reed-Solomon with erasure support.

## Reading order

Read the modules in the order the method page explains them — each is short:

1. `structure.py` — what the standard fixes; the calibration target everything scores against
2. `sampling.py` — from rectified pixels to a probability per module
3. `geometry.py` — the searches: finders, corners, the bow
4. `matrix.py` — the three states, confidence, flip cost
5. `galois.py` + `repair.py` — Reed-Solomon, and why an honest "unknown" is worth two guesses
6. `decoding.py` + `oracle.py` — the outside oracle and the ordered probe
7. `pipeline.py` — composition only; also `solve_many` (photograph fusion)
8. `ensemble.py` — three ensembles, two of them measured useless and documented as such

## The three invariants

Break any of these and the project stops being itself:

1. **The core is library-pure.** Nothing under `core/` imports CLI, server or UI code, prints,
   or touches files/network. All shells (CLI, local server, browser build) are thin layers
   over the same core — the moment one grows its own logic, the agent path and the human path
   start giving different answers to the same photograph.
2. **A cell has three states.** Dark, light, unknown — never two, not even "for simplicity" in
   an intermediate layer. Reed-Solomon repairs twice as many erasures as errors; discarding
   uncertainty throws away half the leverage of the method.
3. **Claims are measured.** Every change to the recovery path is quantified with the
   instruments in `scripts/` (see `scripts/README.md`), and negative results are documented in
   place instead of deleted.

## The seams (where the system is meant to be extended)

| Seam | Where | What it decouples |
|---|---|---|
| **Oracle** | `core/oracle.py`, swap with `oracle.use()` | the single native dependency (zxing-cpp); the browser build hands in the same oracle compiled to WASM, both directions synchronous |
| **Request layer** | `api.py` | what a shell asks for from how the request travelled; the local server and the browser worker call these same functions, so their answers cannot diverge |
| **Backend** | `web/backend-server.js` / `web/backend-worker.js`, one of them installed as `backend.js` | the page from where the work happens — loopback HTTP or Pyodide in a worker |
| **Progress** | `progress=` callback on `solve()`/`solve_many()` | live reporting from the core without the core knowing who listens; feeds the CLI, the NDJSON stream and the worker unchanged |
| **Fusion** | `ensemble.fuse_images`, rules in `FUSION_RULES` | how several photographs of one code are combined |
| **Payload intelligence** | `export.payload_fields` | recognising what a recovered text *is* (Zigbee, Matter, Wi-Fi) |
| **Symbology boundary** | `structure.py`, `layout.py`, `qrspec.py` | the only QR-specific modules; a new symbology is a new set of these, not a parameter |

## Where do I change …

| I want to … | Look at |
|---|---|
| improve detection of damaged finders | `geometry.find_finders`, `scanfinder.py`, merged in `pipeline.detect_finders`; a triple past `TRIPLE_DOUBT` additionally tries its best pair (`pipeline._attempt`) |
| improve the grid on curved surfaces | `geometry.refine_corners` / `refine_bow` (read the measured results in its docstring first; the per-edge bow is measured by `scripts/ab_dome.py`) |
| rescue a grid that seated on the wrong thing | `geometry.restart_coarse`, triggered in `pipeline.solve` past `COARSE_RESTART_THRESHOLD`; measured by `scripts/ab_restart.py` |
| improve the per-cell probabilities | `sampling.estimate_levels` / `posterior_dark`; calibration measured by `scripts/calibration.py`, robustness against lying known cells by `scripts/ab_robust.py` |
| handle areas where the print is gone | `sampling.featureless_depth` / `buried_cells` (the counting argument), damped into the posterior in `pipeline.solve`; measured by `scripts/ab_worn.py`. The depth also strikes buried witnesses from `wrong_known` in `geometry._score` — deliberately never from the descent's quality; the docstring records the failure that rule comes from |
| handle coloured overlays (marker, guide lines) | `preprocess.prepare` (`NEUTRAL_SATURATION`) — ships off, cap at zero; `scripts/ab_marker.py` is the instrument that says why |
| change what the repair may try | `repair.py`; the decode chain order is `pipeline._decode_chain` |
| add an export format | `export.py`, wired into the request layer in `api.py` (both web shells inherit it) |
| change the web page | `web/index.html` + `web/app.js` + `web/style.css` — static files, no build step; served by `server.py` locally and copied verbatim into the published site |
| change what a shell may ask for | `api.py` — never one of the two backends, or the paths drift |
| work on the published site | `scripts/build_site.py` assembles `site/`; `web/worker.js` is the browser's shell over the core |
| add a payload type | `export.payload_fields` + a `*_fields` parser + `PAYLOAD_HINTS` |
| touch anything user-visible about waiting | the progress events (`pipeline._emit` call sites) and their consumers |

## Repository conventions

- `fixtures/` — public, synthetic, regenerated by `scripts/make_fixtures.py`; never edited, only extended
- `fixtures-local/` — real photographs, gitignored, never leave the machine
- `out/` — scratch output of every run, gitignored
- `scripts/` — measurement instruments, not production code (`scripts/README.md` is the index)
- `spike/` — feasibility experiments kept as documentation of their findings
- `docs/` — project-internal notes in German (`VISION.md` is the roadmap, `ISSUES.md` the task
  ledger); everything contributor-facing is English
