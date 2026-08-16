# Third-party software

qrsalvage is licensed under the Apache License 2.0 (see `LICENSE`). It stands on the following
software. All of it is permissively licensed; none of it imposes conditions beyond attribution
and preservation of license texts, and nothing prevents offering qrsalvage as free software or
funding its development through donations.

## Runtime dependencies (Python package)

| Package | License | Used for |
|---|---|---|
| [NumPy](https://numpy.org) | BSD-3-Clause (with 0BSD/MIT/Zlib/CC0 components) | every matrix in the pipeline |
| [OpenCV](https://opencv.org) (`opencv-python`) | Apache-2.0 | image warping, filtering, contour search |
| [Pillow](https://python-pillow.org) | MIT-CMU | image handling |
| [zxing-cpp](https://github.com/zxing-cpp/zxing-cpp) | Apache-2.0 | the outside decode oracle, and re-encoding |

## Development tools (not distributed)

| Package | License |
|---|---|
| [pytest](https://pytest.org) | MIT |
| [ruff](https://github.com/astral-sh/ruff) | MIT |

## Planned browser build (static site)

The in-browser version additionally ships, self-hosted as static assets:

| Component | License | Note |
|---|---|---|
| [Pyodide](https://pyodide.org) | MPL-2.0 | CPython on WebAssembly. File-level copyleft: ship it unmodified and link its source; our code stays Apache-2.0 |
| [CPython](https://python.org) (inside Pyodide) | PSF-2.0 | |
| NumPy / OpenCV Pyodide builds | as above | |
| [zxing-cpp WASM build](https://github.com/zxing-cpp/zxing-cpp) | Apache-2.0 | includes Emscripten runtime parts (MIT) |

## Obligations when distributing

- Keep `LICENSE` and this file alongside every distribution, including the static site.
- The Apache-2.0 dependencies (OpenCV, zxing-cpp) each carry a NOTICE file; the site build
  copies those verbatim into the published assets.
- Pyodide (MPL-2.0) is shipped unmodified; its source lives at the linked repository, which
  satisfies MPL section 3.2. If it were ever patched here, the patched files' source must be
  published.
- None of the above restricts commercial use, donations, or sponsorship.
