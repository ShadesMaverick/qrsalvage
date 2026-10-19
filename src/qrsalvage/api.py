"""What a shell asks for and what it gets back -- one dict in, plain JSON types out.

This layer exists because there are now three shells over the same core and two of them are
web pages. The local server hands these functions an HTTP body and writes the answer to a
socket; the browser build calls the very same functions inside Pyodide and posts the answer to
its page. Neither knows anything the other does not, which is the point: a photograph must not
recover differently because of how the request travelled.

Nothing here speaks HTTP, opens a socket or prints. Everything it returns is JSON-serialisable
or bytes, so it crosses a socket and a postMessage boundary equally well. The transport-shaped
concerns -- upload limits, headers, status codes -- stay with the transport, in server.py.
"""

from __future__ import annotations

import base64
import binascii
import math
import threading
import uuid
from collections import OrderedDict
from collections.abc import Callable

import cv2
import numpy as np

from .core.decoding import reencode, render
from .core.pipeline import ENSEMBLE_MODES, SolveResult, solve, solve_many
from .export import (
    PAYLOAD_HINTS,
    PAYLOAD_LABELS,
    payload_fields,
    to_catalog_pdf,
    to_html_report,
    to_json,
    to_pdf,
    to_svg,
)

ProgressFn = Callable[[str, dict], None]

# The exports are produced on demand rather than shipped with every answer, because a PDF and
# an HTML report attached to a result nobody exports would be wasted on every single recovery.
# Recovering again to build one would mean waiting the four to twenty seconds a second time, so
# the last few results are kept here instead. A handful is plenty: this serves one person on
# one machine -- and in the browser build, one person in one tab.
_RECENT: OrderedDict[str, tuple] = OrderedDict()
_RECENT_LIMIT = 4
# The server answers on threads. Storing a token and evicting the oldest are each atomic on
# their own, but "store, then evict while over the limit" is not: two recoveries finishing
# together can both see the cache over its limit and both evict, retiring a token its owner
# has not used yet. The cost is an export that answers "no longer held" for no reason anyone
# can see, which is exactly the kind of fault that gets blamed on the recovery instead.
_RECENT_LOCK = threading.Lock()

# What one person's camera burst plausibly holds. Fusing several photographs is why more than
# one arrives at all; past a dozen the extra frames buy nothing measurable and every one of
# them costs a full recovery's work.
_MAX_IMAGES = 12

# Above any phone sensor, and the point where a decoded frame stops being a photograph and
# starts being a way to spend the machine's memory. Checked after the decode, which is this
# guard's honest limit -- OpenCV has already allocated that one frame by the time it is asked.
# What it does bound is the whole burst behind it, and every stage downstream.
_MAX_PIXELS = 40_000_000

# The descent's default is 4000. Twenty-five times that is far past where more probing still
# finds anything, and it finishes; what the ceiling stops is a caller naming a number that
# never would.
_MAX_BUDGET = 100_000

# One A4 catalogue per household, not per warehouse.
_MAX_CATALOG_ENTRIES = 200


def _png_bytes(matrix: np.ndarray, scale: int = 8) -> bytes:
    ok, buffer = cv2.imencode(".png", render(matrix, scale=scale))
    return buffer.tobytes() if ok else b""


def _png_data_url(matrix: np.ndarray, scale: int = 8) -> str:
    return "data:image/png;base64," + base64.b64encode(_png_bytes(matrix, scale)).decode("ascii")


def solve_payload(
    payload: dict,
    progress: ProgressFn | None = None,
    *,
    trusted_direct_text: str | None = None,
    trusted_direct_texts: list[str | None] | None = None,
) -> dict:
    """Run one recovery and return everything the page needs, as plain JSON types.

    Accepts either a single ``image`` or a list under ``images``. Several photographs of one
    code are fused -- the strongest measured capability of the whole tool, and the page's
    failure guidance sends people here on purpose. Hand-placed finder points only apply to a
    single photograph: three clicks describe one framing, not several.
    """
    encoded = payload.get("images") or ([payload["image"]] if "image" in payload else [])
    if not isinstance(encoded, list) or not encoded:
        return {"ok": False, "failure": "no photograph was given"}
    if len(encoded) > _MAX_IMAGES:
        return {"ok": False, "failure": f"at most {_MAX_IMAGES} photographs of one code at a time"}

    images: list[np.ndarray] = []
    for entry in encoded:
        if not isinstance(entry, str):
            return {"ok": False, "failure": "each photograph must be a base64 string"}
        try:
            raw = base64.b64decode(entry.split(",", 1)[-1], validate=True)
        except (binascii.Error, ValueError):
            return {"ok": False, "failure": "the photograph is not valid base64 data"}
        if not raw:
            return {"ok": False, "failure": "the image data is empty"}
        try:
            image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        except cv2.error:
            image = None
        if image is None:
            which = f" ({len(images) + 1} of {len(encoded)})" if len(encoded) > 1 else ""
            return {"ok": False, "failure": f"the file{which} could not be read as an image"}
        if image.shape[0] * image.shape[1] > _MAX_PIXELS:
            return {
                "ok": False,
                "failure": f"the photograph is larger than {_MAX_PIXELS // 1_000_000} megapixels",
            }
        images.append(image)

    points = payload.get("finder_points") or None
    if points and len(images) == 1:
        # Three clicks describe one framing. Fewer leaves the grid without a corner to sit on
        # and used to reach past the end of the list somewhere down in geometry; more says the
        # caller means something this path cannot honour. Both are worth saying out loud here,
        # where the words can still name what is wrong.
        if not isinstance(points, list) or len(points) != 3:
            return {
                "ok": False,
                "failure": "three finder points describe a framing, not more or fewer",
            }
        try:
            points = [(float(p["x"]), float(p["y"])) for p in points]
        except (TypeError, KeyError, ValueError):
            return {"ok": False, "failure": "each finder point needs a numeric x and y"}
        if not all(math.isfinite(value) for point in points for value in point):
            # NaN survives every comparison the geometry makes and turns into a grid that is
            # neither placed nor refused.
            return {"ok": False, "failure": "finder points must be finite coordinates"}
    else:
        points = None

    if trusted_direct_texts is None:
        trusted_direct_texts = [trusted_direct_text] + [None] * (len(images) - 1)
    if len(trusted_direct_texts) != len(images) or any(
        text is not None and (not isinstance(text, str) or not text)
        for text in trusted_direct_texts
    ):
        return {"ok": False, "failure": "direct decode results must match the photographs"}

    try:
        budget = int(payload.get("budget", 4000))
    except (TypeError, ValueError):
        return {"ok": False, "failure": "budget must be a number"}
    # Clamped rather than refused, unlike the export sizes below: this one is not a measurement
    # anybody reads back, only how hard to try. A caller who asks for more than the descent can
    # use should get the most it can use, not an error about a number that hurt nobody.
    budget = max(1, min(budget, _MAX_BUDGET))
    direct_text = next((text for text in trusted_direct_texts if text is not None), None)
    if direct_text is not None and points is None:
        result = SolveResult(text=direct_text, candidates_tried=1, source="direct")
    elif len(images) == 1:
        ensemble = payload.get("ensemble", "off")
        if ensemble not in ENSEMBLE_MODES:
            return {
                "ok": False,
                "failure": f"unknown ensemble mode: {ensemble!r}",
            }
        result = solve(
            images[0],
            budget=budget,
            ensemble=ensemble,
            finder_points=points,
            progress=progress,
        )
    else:
        result = solve_many(images, budget=budget, progress=progress)
    image = images[0]

    out: dict = {
        "ok": result.solved,
        "text": result.text,
        "failure": result.failure,
        "width": int(image.shape[1]),
        "height": int(image.shape[0]),
        "images_given": len(images),
        "finders": [{"x": x, "y": y} for x, y, _ in result.finders],
        "candidates_tried": result.candidates_tried,
        "source": result.source,
        # The level the original carried. The catalogue re-encodes from text alone, and
        # without this a reprinted label would silently get whatever level the encoder likes.
        "ecc": result.ecc,
    }
    # The follow-up question, answered: what is this payload, and where does one type it. The
    # split fields never leave the device -- on the server path the page is as local as the
    # photograph, and on the browser path there is no server to leave to.
    if result.text:
        recognised = payload_fields(result.text)
        if recognised:
            kind, fields = recognised
            out["payload_info"] = {
                "kind": kind,
                "label": PAYLOAD_LABELS[kind],
                "hint": PAYLOAD_HINTS[kind],
                "fields": fields,
            }
    if result.fusion is not None:
        out["fusion"] = {
            "photographs": result.fusion.members,
            "agreement": [round(a, 4) for a in result.fusion.agreement],
            "mirrored": list(result.fusion.mirrored),
            "rejected": list(result.fusion.rejected),
            "disagreeing": result.fusion.disagreeing,
        }
    if result.modules is not None:
        # The pipeline measures timing whenever it commits to a grid size.
        assert result.timing is not None
        out.update(
            version=result.version,
            modules=result.modules,
            wrong_known=result.wrong_known,
            wrong_sampled=result.wrong_sampled,
            known_total=result.known_total,
            timing=round(result.timing * 100, 1),
            uncertain=result.uncertain,
            per_size=[
                {"modules": f.modules, "wrong": f.wrong_known, "total": f.known_total}
                for f in result.per_size
            ],
        )
    if result.matrix is not None:
        out["grid"] = result.matrix.to_ascii()
    if result.repair is not None:
        out["repair"] = (
            result.repair.failure
            or f"{result.repair.errors_corrected} errors, "
            f"{result.repair.erasures_used} erasures over {result.repair.blocks} blocks"
        )
    # Both result codes at the same scale, or the page shows two QR images of visibly
    # different size side by side and looks like it cannot make up its mind.
    if result.decoded_matrix is not None:
        out["reconstructed_png"] = _png_data_url(result.decoded_matrix, scale=12)
    if result.solved:
        assert result.text is not None
        out["clean_png"] = _png_data_url(reencode(result.text), scale=12)

    token = uuid.uuid4().hex
    with _RECENT_LOCK:
        _RECENT[token] = (result, image)
        while len(_RECENT) > _RECENT_LIMIT:
            _RECENT.popitem(last=False)
    out["token"] = token
    out["exportable"] = result.solved or result.decoded_matrix is not None
    return out


def export_payload(payload: dict) -> tuple[bytes, str, str]:
    """Build one export from a remembered result. Returns (bytes, content type, filename)."""
    with _RECENT_LOCK:
        remembered = _RECENT.get(payload.get("token", ""))
    if remembered is None:
        raise KeyError("that result is no longer held; recover the image again")
    result, image = remembered

    fmt = payload.get("format", "svg")
    size_mm = float(payload.get("size_mm", 40.0))
    if not 5.0 <= size_mm <= 500.0:
        raise ValueError("size must be between 5 and 500 mm")

    # The re-encoded code wherever possible: guaranteed valid, where the reconstruction is one
    # that happened to pass. The error correction level defaults to the one the original
    # carried, so reproducing a label reproduces it rather than inventing a new one.
    ecc = payload.get("ecc") or result.ecc
    matrix = reencode(result.text, ecc=ecc) if result.solved else result.decoded_matrix

    if fmt == "svg":
        return to_svg(matrix, size_mm=size_mm).encode("utf-8"), "image/svg+xml", "code.svg"
    if fmt == "pdf":
        return to_pdf(matrix, size_mm=size_mm), "application/pdf", "code.pdf"
    if fmt == "json":
        body = to_json(result, split_payload=bool(payload.get("split", payload.get("zigbee"))))
        return body.encode("utf-8"), "application/json", "result.json"
    if fmt == "html":
        ok, encoded = cv2.imencode(".png", image)
        page = to_html_report(
            result,
            encoded.tobytes() if ok else b"",
            _png_bytes(result.decoded_matrix) if result.decoded_matrix is not None else b"",
            _png_bytes(matrix, scale=10) if result.solved else b"",
        )
        return page.encode("utf-8"), "text/html", "report.html"
    raise ValueError(f"unknown export format: {fmt}")


def catalog_payload(payload: dict) -> tuple[bytes, str, str]:
    """Build the A4 catalogue from recovered texts. Returns (bytes, content type, filename).

    Stateless on purpose: the page sends title and text per entry and the codes are re-encoded
    from the text, at the error correction level each original carried. Nothing has to be
    remembered between the recoveries and the download, so a catalogue can span more
    recoveries than the export cache holds.
    """
    given = payload.get("entries", [])
    # Every entry is a fresh QR encode plus a page's worth of layout, so the work is the
    # caller's to name. A household's labelled devices do not run to three figures; a request
    # that does is not a catalogue anyone means to print.
    if not isinstance(given, list) or len(given) > _MAX_CATALOG_ENTRIES:
        raise ValueError(f"a catalogue holds at most {_MAX_CATALOG_ENTRIES} entries")

    entries = []
    for entry in given:
        text = (entry.get("text") or "").strip()
        if not text:
            continue
        entries.append(
            {
                "title": (entry.get("title") or "").strip() or "untitled",
                "text": text,
                "matrix": reencode(text, ecc=entry.get("ecc") or None),
                "note": (entry.get("note") or "").strip() or None,
            }
        )
    if not entries:
        raise ValueError("no entries with a recovered text")

    size_mm = float(payload.get("size_mm", 50.0))
    if not 20.0 <= size_mm <= 70.0:
        raise ValueError("catalogue code size must be between 20 and 70 mm")
    return to_catalog_pdf(entries, size_mm=size_mm), "application/pdf", "catalog.pdf"
