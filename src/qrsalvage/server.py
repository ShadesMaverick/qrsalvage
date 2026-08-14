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
from .core.pipeline import solve
from .export import to_html_report, to_json, to_pdf, to_svg

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


def solve_payload(payload: dict) -> dict:
    """Run one recovery and return everything the page needs, as plain JSON types."""
    raw = base64.b64decode(payload["image"].split(",", 1)[-1])
    buffer = np.frombuffer(raw, dtype=np.uint8)
    image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if image is None:
        return {"ok": False, "failure": "the file could not be read as an image"}

    points = payload.get("finder_points") or None
    if points:
        points = [(float(p["x"]), float(p["y"])) for p in points]

    result = solve(
        image,
        budget=int(payload.get("budget", 4000)),
        ensemble=payload.get("ensemble", "off"),
        finder_points=points,
    )

    out: dict = {
        "ok": result.solved,
        "text": result.text,
        "failure": result.failure,
        "width": int(image.shape[1]),
        "height": int(image.shape[0]),
        "finders": [{"x": x, "y": y} for x, y, _ in result.finders],
        "candidates_tried": result.candidates_tried,
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
    if result.decoded_matrix is not None:
        out["reconstructed_png"] = _png_data_url(result.decoded_matrix)
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

    # Only these, by name. No path joining, so no traversal to worry about.
    STATIC = {
        "/": ("index.html", "text/html; charset=utf-8"),
        "/index.html": ("index.html", "text/html; charset=utf-8"),
        "/axolotl.png": ("axolotl.png", "image/png"),
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
        if self.path not in ("/api/solve", "/api/export"):
            self._send(404, b"not found", "text/plain; charset=utf-8")
            return
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0 or length > MAX_UPLOAD:
            self._send(413, b'{"ok":false,"failure":"image too large"}', "application/json")
            return

        if self.path == "/api/export":
            try:
                body, content_type, filename = export_payload(json.loads(self.rfile.read(length)))
            except Exception as exc:
                message = json.dumps({"ok": False, "failure": f"{exc}"}).encode("utf-8")
                self._send(400, message, "application/json; charset=utf-8")
                return
            self._send_file(body, content_type, filename)
            return

        try:
            payload = json.loads(self.rfile.read(length))
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
