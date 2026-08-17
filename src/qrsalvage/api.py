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
import uuid
from collections import OrderedDict
from collections.abc import Callable

import cv2
import numpy as np

from .core.decoding import reencode, render
from .core.pipeline import solve, solve_many
from .export import (
    PAYLOAD_HINTS,
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


def _png_bytes(matrix: np.ndarray, scale: int = 8) -> bytes:
    ok, buffer = cv2.imencode(".png", render(matrix, scale=scale))
    return buffer.tobytes() if ok else b""


def _png_data_url(matrix: np.ndarray, scale: int = 8) -> str:
    return "data:image/png;base64," + base64.b64encode(_png_bytes(matrix, scale)).decode("ascii")


def solve_payload(payload: dict, progress: ProgressFn | None = None) -> dict:
    """Run one recovery and return everything the page needs, as plain JSON types.

    Accepts either a single ``image`` or a list under ``images``. Several photographs of one
    code are fused -- the strongest measured capability of the whole tool, and the page's
    failure guidance sends people here on purpose. Hand-placed finder points only apply to a
    single photograph: three clicks describe one framing, not several.
    """
    encoded = payload.get("images") or [payload["image"]]
    images: list[np.ndarray] = []
    for entry in encoded:
        raw = base64.b64decode(entry.split(",", 1)[-1])
        image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            which = f" ({len(images) + 1} of {len(encoded)})" if len(encoded) > 1 else ""
            return {"ok": False, "failure": f"the file{which} could not be read as an image"}
        images.append(image)

    points = payload.get("finder_points") or None
    if points and len(images) == 1:
        points = [(float(p["x"]), float(p["y"])) for p in points]
    else:
        points = None

    budget = int(payload.get("budget", 4000))
    if len(images) == 1:
        result = solve(
            images[0],
            budget=budget,
            ensemble=payload.get("ensemble", "off"),
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
            out["payload_info"] = {"kind": kind, "hint": PAYLOAD_HINTS[kind], "fields": fields}
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
    _RECENT[token] = (result, image)
    while len(_RECENT) > _RECENT_LIMIT:
        _RECENT.popitem(last=False)
    out["token"] = token
    out["exportable"] = result.decoded_matrix is not None
    return out


def export_payload(payload: dict) -> tuple[bytes, str, str]:
    """Build one export from a remembered result. Returns (bytes, content type, filename)."""
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
    entries = []
    for entry in payload.get("entries", []):
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
