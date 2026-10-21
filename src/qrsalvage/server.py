"""A local web interface, so recovering a code does not require a virtual environment.

Bound to the loopback address and nothing else. The tool exists because the payload of a
damaged code is often a secret -- a device pairing code, a key, a serial number -- and shipping
that to a server would defeat the point. Nothing here reaches out to the network, and the
listening socket is not reachable from another machine.

The page lives in qrsalvage/web/ as three static files -- markup, style, script. No build
step, no package manager, no dependency that can go stale. They sit inside the package rather
than beside it: resolving them against the repository root worked from a source checkout and
would have shipped a wheel with no page in it at all.

The answers themselves are built in api.py, which knows nothing about HTTP. This file is the
socket, the headers and the status codes -- and nothing else. The browser build calls that
same module directly, so both paths answer identically by construction.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import socket
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .api import catalog_payload, export_payload, solve_payload

WEB_ROOT = Path(__file__).resolve().parent / "web"
# Roomy enough for a camera burst of full-resolution frames plus a couple of dropped photos,
# base64 overhead included. Still a hard cap: this is one person's loopback, not an inbox.
MAX_UPLOAD = 64 * 1024 * 1024

# How many recoveries may run at once, and why the number is small rather than generous.
#
# ThreadingHTTPServer starts a thread per connection, so without this every request that
# arrived would begin work immediately. That reads like throughput and measures as the
# opposite: four recoveries in four threads took 0.90x the time of running the same four one
# after another. The descent is Python-level work under the GIL, so concurrent solves contend
# instead of cooperating, and every caller waits longer than if they had queued.
#
# Two, not one, so a page that opens a second tab is not simply blocked -- and a ceiling rather
# than none, because each recovery holds a full-resolution photograph and its warps in memory.
# A queue that answers slowly is a better failure than a machine that runs out of memory.
WORKERS = threading.BoundedSemaphore(2)

# Long enough to sit through the recovery ahead in the queue, short enough that a caller is
# told to come back rather than left holding a socket forever.
WORK_WAIT = 180.0

# The one inline <script> of a served page, hashed, so the policy can name it instead of
# waving through every inline script with 'unsafe-inline'. Keyed by (path, mtime): the page is
# edited during development, and a stale hash would block the page's own script -- loudly, in
# the console, which is the right failure mode, but not one to ship.
_CSP_CACHE: dict[Path, tuple[float, str]] = {}


def _html_csp(path: Path, body: bytes) -> str:
    mtime = path.stat().st_mtime
    cached = _CSP_CACHE.get(path)
    if cached and cached[0] == mtime:
        return cached[1]
    # The browser hashes the script text as parsed, and the HTML parser normalises CR and
    # CRLF to LF before anything else happens. A file that lives with Windows line endings
    # therefore hashes differently on disk than in the browser -- measured the hard way, as a
    # page whose own script the policy refused.
    hashes = " ".join(
        "'sha256-" + base64.b64encode(hashlib.sha256(script).digest()).decode("ascii") + "'"
        for script in re.findall(
            rb"<script>(.*?)</script>", body.replace(b"\r\n", b"\n").replace(b"\r", b"\n"), re.S
        )
    )
    policy = (
        f"default-src 'self'; script-src 'self'{' ' + hashes if hashes else ''}; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
        "connect-src 'self'; object-src 'none'; base-uri 'none'; "
        "form-action 'self'; frame-ancestors 'none'"
    )
    _CSP_CACHE[path] = (mtime, policy)
    return policy


class Handler(BaseHTTPRequestHandler):
    server_version = "qrsalvage"

    # A client that opens a connection and then goes quiet used to hold a worker thread for as
    # long as it liked. Loopback is fast and the largest upload allowed is 64 MB, so a minute is
    # generous for anything honest; nothing here waits on a human.
    timeout = 60

    def log_message(self, *args) -> None:  # noqa: D102 - quiet by default
        pass

    def _host_allowed(self) -> bool:
        """Refuse requests whose Host header is not the loopback the server answers on.

        The socket only listens on 127.0.0.1, but that alone does not stop DNS rebinding: a
        hostile page resolves its own domain to 127.0.0.1 and the browser then talks to this
        server believing it is same-origin -- CORS never enters the picture. The Host header
        still carries the attacker's domain, so it is the one thing to check.
        """
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
        return host in ("127.0.0.1", "localhost", "::1")

    def _origin_allowed(self) -> bool:
        """Refuse a state-changing request that a page on another origin sent for the visitor.

        _host_allowed covers DNS rebinding, where a hostile domain resolves to this address.
        It cannot cover the cheaper attack, which needs no rebinding at all: a page on any
        origin posts straight to 127.0.0.1, and the browser writes the Host header itself, so
        the check above sees exactly what it wants to see.

        What a page cannot forge are the headers the browser writes about the page: Origin on a
        cross-origin POST, Sec-Fetch-Site on every request a browser makes at all. Their absence
        means the caller is not a browser -- curl, the test suite, a script -- and that was
        never the thing being defended against here.
        """
        site = self.headers.get("Sec-Fetch-Site")
        if site is not None and site not in ("same-origin", "none"):
            return False
        origin = self.headers.get("Origin")
        if origin is None:
            return True
        return (urlsplit(origin).hostname or "").lower() in ("127.0.0.1", "localhost", "::1")

    def _refuse_host(self) -> None:
        self._send(403, b"wrong host", "text/plain; charset=utf-8")

    def _refuse_origin(self) -> None:
        self._send(403, b"wrong origin", "text/plain; charset=utf-8")

    def _send(self, status: int, body: bytes, content_type: str, csp: str | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        # Nothing served here should ever be sniffed into something else, framed by another
        # page, or leak its localhost URL to a site someone follows a link to.
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", csp or "default-src 'none'")
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
        "/legal": ("legal.html", "text/html; charset=utf-8"),
        "/legal.html": ("legal.html", "text/html; charset=utf-8"),
        "/robots.txt": ("robots.txt", "text/plain; charset=utf-8"),
        "/sitemap.xml": ("sitemap.xml", "application/xml; charset=utf-8"),
        "/axolotl.png": ("axolotl.png", "image/png"),
        "/axolotl-companion.png": ("axolotl-companion.png", "image/png"),
        "/style.css": ("style.css", "text/css; charset=utf-8"),
        "/outline-editor.js": ("outline-editor.js", "text/javascript; charset=utf-8"),
        "/studio-state.js": ("studio-state.js", "text/javascript; charset=utf-8"),
        "/locale.js": ("locale.js", "text/javascript; charset=utf-8"),
        "/companion.js": ("companion.js", "text/javascript; charset=utf-8"),
        "/app.js": ("app.js", "text/javascript; charset=utf-8"),
        # The half of the page that knows where the work happens. This server serves the HTTP
        # one; the static build puts backend-worker.js in the same slot, and worker.js with it.
        # Neither of those belongs here -- there is no worker to boot when a server is running.
        "/backend.js": ("backend-server.js", "text/javascript; charset=utf-8"),
        "/fig-known.svg": ("fig-known.svg", "image/svg+xml"),
        "/fig-levels.svg": ("fig-levels.svg", "image/svg+xml"),
        "/fig-posterior.svg": ("fig-posterior.svg", "image/svg+xml"),
        "/fig-objective.svg": ("fig-objective.svg", "image/svg+xml"),
        "/fig-probe.svg": ("fig-probe.svg", "image/svg+xml"),
        "/fig-rs.svg": ("fig-rs.svg", "image/svg+xml"),
    }

    def do_GET(self) -> None:  # noqa: N802 - name fixed by BaseHTTPRequestHandler
        if not self._host_allowed():
            self._refuse_host()
            return
        entry = self.STATIC.get(self.path)
        if entry is None:
            self._send(404, b"not found", "text/plain; charset=utf-8")
            return
        name, content_type = entry
        path = WEB_ROOT / name
        if not path.is_file():
            self._send(500, f"{name} is missing".encode(), "text/plain; charset=utf-8")
            return
        body = path.read_bytes()
        csp = _html_csp(path, body) if content_type.startswith("text/html") else None
        self._send(200, body, content_type, csp=csp)

    def _send_file(self, body: bytes, content_type: str, filename: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'none'")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802 - name fixed by BaseHTTPRequestHandler
        if not self._host_allowed():
            self._refuse_host()
            return
        if not self._origin_allowed():
            self._refuse_origin()
            return
        if self.path not in ("/api/solve", "/api/export", "/api/catalog"):
            self._send(404, b"not found", "text/plain; charset=utf-8")
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            # A header that is not a number is not a size to compare against. int() would raise
            # here, outside every handler below, and take the worker thread with it -- silently,
            # because log_message is stubbed out. One bad header must not cost a thread.
            self._send(400, b'{"ok":false,"failure":"bad Content-Length"}', "application/json")
            return
        if length <= 0 or length > MAX_UPLOAD:
            self._send(413, b'{"ok":false,"failure":"image too large"}', "application/json")
            return

        # One thread per connection is the server's own doing; how many of them may be *working*
        # at once is this file's to decide, and the answer is measured. See WORKERS.
        if not WORKERS.acquire(timeout=WORK_WAIT):
            self._send(
                503, b'{"ok":false,"failure":"busy with another recovery"}', "application/json"
            )
            return
        try:
            self._serve_api(length)
        finally:
            WORKERS.release()

    def _serve_api(self, length: int) -> None:
        """Read the body, do the work, write the answer -- the half that costs something."""
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

        if not isinstance(payload, dict):
            # `[1,2]` is valid JSON and survives the decode above, but every reader from here on
            # asks the body for keys. The .get one line down would raise outside any handler --
            # the same lost thread as a bad Content-Length, one layer further in.
            answer = {"ok": False, "failure": "the request body must be a JSON object"}
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
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'none'")
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


class _LoopbackServer(ThreadingHTTPServer):
    """The listening socket, owned exclusively wherever the platform lets it be owned.

    On POSIX, reusing the address only skips the TIME_WAIT delay after a restart -- which is
    the whole reason the flag is usually set. Windows spells something else with the same
    constant: it lets a second process bind a port this one already holds, and the kernel then
    hands new connections to one of the two. On the platform this tool is used on most, the
    convenience flag is a way for another local process to be given the photographs. What
    Windows calls "this port is mine" is SO_EXCLUSIVEADDRUSE, and that is what it gets.
    """

    allow_reuse_address = sys.platform != "win32"

    def server_bind(self) -> None:
        exclusive = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
        if exclusive is not None:
            self.socket.setsockopt(socket.SOL_SOCKET, exclusive, 1)
        super().server_bind()


def serve(port: int = 8765, open_browser: bool = True) -> int:
    """Start the local interface. Listens on the loopback address only."""
    with _LoopbackServer(("127.0.0.1", port), Handler) as httpd:
        url = f"http://127.0.0.1:{port}/"
        print(f"qrsalvage is listening on {url}  (loopback only, press Ctrl+C to stop)")
        if open_browser:
            webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")
    return 0
