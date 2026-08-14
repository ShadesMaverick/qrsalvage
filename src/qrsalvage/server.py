"""A local web interface, so recovering a code does not require a virtual environment.

Bound to the loopback address and nothing else. The tool exists because the payload of a
damaged code is often a secret -- a device pairing code, a key, a serial number -- and shipping
that to a server would defeat the point. Nothing here reaches out to the network, and the
listening socket is not reachable from another machine.

The page itself lives in web/index.html and is served as a single static file. No build step,
no package manager, no dependency that can go stale.
"""

from __future__ import annotations

import base64
import json
import socketserver
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import cv2
import numpy as np

from .core.decoding import reencode, render
from .core.pipeline import solve

WEB_ROOT = Path(__file__).resolve().parents[2] / "web"
MAX_UPLOAD = 24 * 1024 * 1024


def _png_data_url(matrix: np.ndarray, scale: int = 8) -> str:
    ok, buffer = cv2.imencode(".png", render(matrix, scale=scale))
    if not ok:
        return ""
    return "data:image/png;base64," + base64.b64encode(buffer.tobytes()).decode("ascii")


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
    return out


class Handler(BaseHTTPRequestHandler):
    server_version = "qrsalvage"

    def log_message(self, *args) -> None:  # noqa: D102 - quiet by default
        pass

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        # The page never loads anything from elsewhere, so forbid it outright.
        self.send_header("Content-Security-Policy", "default-src 'self' data: 'unsafe-inline'")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - name fixed by BaseHTTPRequestHandler
        if self.path not in ("/", "/index.html"):
            self._send(404, b"not found", "text/plain; charset=utf-8")
            return
        page = WEB_ROOT / "index.html"
        if not page.is_file():
            self._send(500, b"web/index.html is missing", "text/plain; charset=utf-8")
            return
        self._send(200, page.read_bytes(), "text/html; charset=utf-8")

    def do_POST(self) -> None:  # noqa: N802 - name fixed by BaseHTTPRequestHandler
        if self.path != "/api/solve":
            self._send(404, b"not found", "text/plain; charset=utf-8")
            return
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0 or length > MAX_UPLOAD:
            self._send(413, b'{"ok":false,"failure":"image too large"}', "application/json")
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
