"""A local web interface, so recovering a code does not require a virtual environment.

Bound to the loopback address and nothing else. The tool exists because the payload of a
damaged code is often a secret -- a device pairing code, a key, a serial number -- and shipping
that to a server would defeat the point. Nothing here reaches out to the network, and the
listening socket is not reachable from another machine.

The page lives in qrsalvage/web/index.html and is served as a single static file. No build
step, no package manager, no dependency that can go stale. It sits inside the package rather
than beside it: resolving it against the repository root worked from a source checkout and
would have shipped a wheel with no page in it at all.
"""

from __future__ import annotations

import base64
import json
import socketserver
import uuid
import webbrowser
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import cv2
import numpy as np

from .core.decoding import reencode, render
from .core.pipeline import solve, solve_many
from .export import to_catalog_pdf, to_html_report, to_json, to_pdf, to_svg

WEB_ROOT = Path(__file__).resolve().parent / "web"
MAX_UPLOAD = 24 * 1024 * 1024

# The exports are produced on demand rather than shipped with every answer, because a PDF and
# an HTML report attached to a result nobody exports would be wasted on every single recovery.
# Recovering again to build one would mean waiting the four to twenty seconds a second time, so
# the last few results are kept here instead. A handful is plenty: this serves one person on
# one machine.
_RECENT: OrderedDict[str, tuple] = OrderedDict()
_RECENT_LIMIT = 4


def _png_bytes(matrix: np.ndarray, scale: int = 8) -> bytes:
    ok, buffer = cv2.imencode(".png", render(matrix, scale=scale))
    return buffer.tobytes() if ok else b""


def _png_data_url(matrix: np.ndarray, scale: int = 8) -> str:
    return "data:image/png;base64," + base64.b64encode(_png_bytes(matrix, scale)).decode("ascii")


def solve_payload(payload: dict, progress=None) -> dict:
    """Run one recovery and return everything the page needs, as plain JSON types.

    Accepts either a single ``image`` or a list under ``images``. Several photographs of one
    code are fused -- the strongest measured capability of the whole tool, and the page's
    failure guidance sends people here on purpose. Hand-placed finder points only apply to a
    single photograph: three clicks describe one framing, not several.
    """
    encoded = payload.get("images") or [payload["image"]]
    images = []
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
    if result.fusion is not None:
        out["fusion"] = {
            "photographs": result.fusion.members,
            "agreement": [round(a, 4) for a in result.fusion.agreement],
            "mirrored": list(result.fusion.mirrored),
            "rejected": list(result.fusion.rejected),
            "disagreeing": result.fusion.disagreeing,
        }
    if result.modules is not None:
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
        body = to_json(result, include_zigbee=bool(payload.get("zigbee")))
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


class Handler(BaseHTTPRequestHandler):
    server_version = "qrsalvage"

    def log_message(self, *args) -> None:  # noqa: D102 - quiet by default
        pass

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        # The page never loads anything from elsewhere, so forbid it outright.
        self.send_header(
            "Content-Security-Policy", "default-src 'self' data: blob: 'unsafe-inline'"
        )
        self.end_headers()
        self.wfile.write(body)

    # Only these, by name. No path joining, so no traversal to worry about. The figures on the
    # method page are listed one by one for the same reason; docs/make_method_figures.py builds
    # them, and test_server.py checks that every figure the page asks for is in here.
    STATIC = {
        "/": ("index.html", "text/html; charset=utf-8"),
        "/index.html": ("index.html", "text/html; charset=utf-8"),
        "/method": ("method.html", "text/html; charset=utf-8"),
        "/method.html": ("method.html", "text/html; charset=utf-8"),
        "/axolotl.png": ("axolotl.png", "image/png"),
        "/fig-known.svg": ("fig-known.svg", "image/svg+xml"),
        "/fig-levels.svg": ("fig-levels.svg", "image/svg+xml"),
        "/fig-posterior.svg": ("fig-posterior.svg", "image/svg+xml"),
        "/fig-objective.svg": ("fig-objective.svg", "image/svg+xml"),
        "/fig-probe.svg": ("fig-probe.svg", "image/svg+xml"),
        "/fig-rs.svg": ("fig-rs.svg", "image/svg+xml"),
    }

    def do_GET(self) -> None:  # noqa: N802 - name fixed by BaseHTTPRequestHandler
        entry = self.STATIC.get(self.path)
        if entry is None:
            self._send(404, b"not found", "text/plain; charset=utf-8")
            return
        name, content_type = entry
        path = WEB_ROOT / name
        if not path.is_file():
            self._send(500, f"{name} is missing".encode(), "text/plain; charset=utf-8")
            return
        self._send(200, path.read_bytes(), content_type)

    def _send_file(self, body: bytes, content_type: str, filename: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802 - name fixed by BaseHTTPRequestHandler
        if self.path not in ("/api/solve", "/api/export", "/api/catalog"):
            self._send(404, b"not found", "text/plain; charset=utf-8")
            return
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0 or length > MAX_UPLOAD:
            self._send(413, b'{"ok":false,"failure":"image too large"}', "application/json")
            return

        if self.path in ("/api/export", "/api/catalog"):
            builder = export_payload if self.path == "/api/export" else catalog_payload
            try:
                body, content_type, filename = builder(json.loads(self.rfile.read(length)))
            except Exception as exc:
                message = json.dumps({"ok": False, "failure": f"{exc}"}).encode("utf-8")
                self._send(400, message, "application/json; charset=utf-8")
                return
            self._send_file(body, content_type, filename)
            return

        try:
            payload = json.loads(self.rfile.read(length))
        except Exception as exc:
            answer = {"ok": False, "failure": f"{type(exc).__name__}: {exc}"}
            self._send(200, json.dumps(answer).encode("utf-8"), "application/json; charset=utf-8")
            return

        if payload.get("stream"):
            # Newline-delimited JSON: progress events as they happen, the result as the last
            # line. HTTP/1.0 close-delimits the body, so no length is needed up front -- which
            # is the whole point, the length is not known until the recovery is over. The page
            # gets to *show* the descent instead of a spinner, and the events are the same ones
            # every other shell sees; the core neither knows nor cares that this one is a wire.
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
            self.send_header(
                "Content-Security-Policy", "default-src 'self' data: blob: 'unsafe-inline'"
            )
            self.end_headers()
            alive = True

            def push(event: str, data: dict) -> None:
                nonlocal alive
                if not alive:
                    return
                try:
                    line = json.dumps({"type": event, **data}) + "\n"
                    self.wfile.write(line.encode("utf-8"))
                    self.wfile.flush()
                except OSError:
                    # The reader hung up. The recovery finishes anyway -- it cannot be
                    # interrupted mid-flight -- but there is no one left to talk to.
                    alive = False

            try:
                answer = solve_payload(payload, progress=push)
            except Exception as exc:
                answer = {"ok": False, "failure": f"{type(exc).__name__}: {exc}"}
            push("result", answer)
            return

        try:
            answer = solve_payload(payload)
        except Exception as exc:  # a bad upload must not take the server down
            answer = {"ok": False, "failure": f"{type(exc).__name__}: {exc}"}
        self._send(200, json.dumps(answer).encode("utf-8"), "application/json; charset=utf-8")


def serve(port: int = 8765, open_browser: bool = True) -> int:
    """Start the local interface. Listens on the loopback address only."""
    socketserver.TCPServer.allow_reuse_address = True
    with ThreadingHTTPServer(("127.0.0.1", port), Handler) as httpd:
        url = f"http://127.0.0.1:{port}/"
        print(f"qrsalvage is listening on {url}  (loopback only, press Ctrl+C to stop)")
        if open_browser:
            webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")
    return 0
