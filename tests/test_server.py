"""The local web interface: its JSON contract and its refusal to listen to the outside world.

The page is a single static file with no build step, so the only thing that can silently break
between it and the core is the shape of the JSON. That is what these tests pin down.
"""

from __future__ import annotations

import base64
import http.client
import json
import re
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import cv2
import pytest

from qrsalvage.server import Handler, catalog_payload, export_payload, solve_payload

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "engraved-curved-hard.png"
ROOT = Path(__file__).resolve().parents[1]


def _data_url(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def test_payload_carries_everything_the_page_shows():
    answer = solve_payload({"image": _data_url(FIXTURE)})

    assert answer["ok"] is True
    assert answer["text"].startswith("QRSALVAGE-SYNTHETIC")
    # Every field the page renders has to be present, or a metric silently disappears.
    for key in (
        "version",
        "modules",
        "wrong_known",
        "known_total",
        "timing",
        "uncertain",
        "candidates_tried",
        "finders",
        "grid",
        "clean_png",
        "reconstructed_png",
    ):
        assert key in answer, f"missing from the response: {key}"
    assert answer["clean_png"].startswith("data:image/png;base64,")
    assert set(answer["grid"].replace("\n", "")) <= {"#", ".", "?"}
    assert json.dumps(answer)  # must survive serialisation, i.e. no numpy types leaked through


def test_a_broken_upload_is_reported_not_raised():
    answer = solve_payload({"image": "data:image/png;base64,bm90YW5pbWFnZQ=="})
    assert answer["ok"] is False
    assert answer["failure"]


def test_several_photographs_are_fused_when_none_reads_alone():
    """The strongest measured capability of the tool, reachable from the page.

    Three synthetic photographs of one code, each with its own stain, none of which the solver
    reads alone -- exactly the constructed case test_fusion.py pins down -- handed to the
    server as one request. The response must carry the fusion evidence, because whoever reads
    it decides whether to trust an install code on its strength.
    """
    from test_fusion import HARD_GROUP, HARD_STAIN, photographs
    from test_fusion import TEXT as FUSION_TEXT

    encoded = []
    for photo in photographs(HARD_STAIN, HARD_GROUP):
        ok, buffer = cv2.imencode(".png", photo)
        assert ok
        encoded.append(
            "data:image/png;base64," + base64.b64encode(buffer.tobytes()).decode("ascii")
        )

    answer = solve_payload({"images": encoded})

    assert answer["ok"] is True
    assert answer["text"] == FUSION_TEXT
    assert answer["images_given"] == 3
    assert answer["fusion"]["photographs"] == 3
    assert answer["fusion"]["rejected"] == []
    assert answer["fusion"]["disagreeing"] > 0
    assert json.dumps(answer)


def test_a_single_image_may_still_arrive_under_the_old_key():
    """The page sends `images` now; the old `image` contract stays honoured."""
    single = solve_payload({"image": _data_url(FIXTURE)})
    listed = solve_payload({"images": [_data_url(FIXTURE)]})
    assert single["ok"] is True and listed["ok"] is True
    assert single["text"] == listed["text"]
    assert "fusion" not in listed, "one photograph is not a fusion"


def test_a_matter_code_arrives_with_its_manual_pairing_code():
    """From photograph to the number a person types into Home Assistant, in one answer.

    The whole audience of this tool is someone whose code cannot be scanned; for Matter the
    derived manual pairing code is what they actually need, so the answer carries it."""
    from qrsalvage.core.decoding import reencode
    from qrsalvage.synth import Damage, render_photo

    photo = render_photo(
        reencode("MT:Y.K9042C00KA0648G00"), Damage(contrast=0.30, curvature=0.15), seed=2
    )
    ok, buffer = cv2.imencode(".png", photo)
    assert ok
    answer = solve_payload(
        {"image": "data:image/png;base64," + base64.b64encode(buffer.tobytes()).decode("ascii")}
    )

    assert answer["ok"] is True
    info = answer["payload_info"]
    assert info["kind"] == "matter"
    assert info["fields"]["manual_pairing_code"] == "3497-011-2332"
    assert info["fields"]["setup_passcode"] == "20202021"
    assert "Home Assistant" in info["hint"]
    assert json.dumps(answer)


def test_hand_placed_finders_are_accepted():
    """The escape hatch: three rough clicks instead of the automatic search."""
    automatic = solve_payload({"image": _data_url(FIXTURE)})
    assert len(automatic["finders"]) >= 3

    # Displace every click by 20 px, which is far more than anyone misses by.
    points = [{"x": f["x"] + 20, "y": f["y"] - 20} for f in automatic["finders"][:3]]
    manual = solve_payload({"image": _data_url(FIXTURE), "finder_points": points})

    assert manual["ok"] is True
    assert manual["text"] == automatic["text"]
    assert manual["wrong_known"] == automatic["wrong_known"], (
        "a hand-placed click must land on the same grid as the automatic search"
    )


def test_exports_are_built_from_the_remembered_result():
    """The page exports without recovering a second time.

    Rebuilding the result for each export would mean waiting the whole recovery again -- four
    seconds on an easy image, twenty on one that needs the fallbacks -- for a file the server
    already has everything to produce.
    """
    answer = solve_payload({"image": _data_url(FIXTURE)})
    assert answer["exportable"] is True

    expected = {
        "svg": (b"<svg", "image/svg+xml"),
        "pdf": (b"%PDF", "application/pdf"),
        "json": (b"{", "application/json"),
        "html": (b"<!doctype html>", "text/html"),
    }
    for fmt, (prefix, content_type) in expected.items():
        body, kind, filename = export_payload(
            {"token": answer["token"], "format": fmt, "size_mm": 30}
        )
        assert body.startswith(prefix), fmt
        assert kind == content_type
        assert filename.endswith(fmt)

    # The size the page asks for has to reach the file, or the millimetres are decoration.
    svg, _, _ = export_payload({"token": answer["token"], "format": "svg", "size_mm": 30})
    assert b'width="30.0mm"' in svg


def test_export_refuses_an_unknown_result_and_an_absurd_size():
    answer = solve_payload({"image": _data_url(FIXTURE)})
    with pytest.raises(KeyError):
        export_payload({"token": "not-a-token", "format": "svg"})
    with pytest.raises(ValueError):
        export_payload({"token": answer["token"], "format": "svg", "size_mm": 5000})
    with pytest.raises(ValueError):
        export_payload({"token": answer["token"], "format": "docx"})


def test_the_pairing_secret_is_not_split_out_by_default():
    answer = solve_payload({"image": _data_url(FIXTURE)})
    plain, _, _ = export_payload({"token": answer["token"], "format": "json"})
    assert b"zigbee" not in plain


@pytest.fixture
def running_server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd.server_address
    httpd.shutdown()
    httpd.server_close()


def test_it_serves_the_page_and_nothing_else(running_server):
    host, port = running_server
    connection = http.client.HTTPConnection(host, port, timeout=10)

    connection.request("GET", "/")
    response = connection.getresponse()
    body = response.read()
    assert response.status == 200
    assert b"qrsalvage" in body

    # No directory traversal, no serving of anything but the one page.
    connection.request("GET", "/../pyproject.toml")
    assert connection.getresponse().status == 404
    connection.close()


def test_the_legal_page_is_reachable_and_still_has_blanks_to_fill(running_server):
    """A page nobody links to does not satisfy an obligation to be reachable.

    German law requires an operator to be identifiable from the published site, and a donation
    button removes any argument about whether that applies here. So the front page has to link
    it, the page has to answer, and -- until someone fills in a name and a postal address that
    can receive mail -- the placeholders have to be loud enough that publishing with them still
    in place would be a decision rather than an oversight.
    """
    host, port = running_server
    connection = http.client.HTTPConnection(host, port, timeout=10)

    connection.request("GET", "/")
    front = connection.getresponse().read()
    assert b'href="legal.html"' in front, "the front page does not link the legal page"

    connection.request("GET", "/legal.html")
    response = connection.getresponse()
    page = response.read().decode("utf-8")
    assert response.status == 200
    assert response.getheader("Content-Type", "").startswith("text/html")
    assert "Impressum" in page and "Datenschutz" in page

    # The claim the whole project rests on belongs here in plain words, not only in a README.
    assert "verlassen Ihr Gerät nicht" in page

    # Turned around in September 2026, the day the operator's details went in. From here on a
    # placeholder reappearing -- a template refactor, a revert, an overeager merge -- is the
    # failure, because publishing with one would break a legal obligation, not a preference.
    assert "TODO" not in page, "a placeholder came back into the legal page"
    assert "Fabian Marius Freitag" in page, "the imprint lost the operator's name"
    connection.close()


def test_the_success_card_points_at_the_live_kofi_page():
    script = (ROOT / "src" / "qrsalvage" / "web" / "app.js").read_text(encoding="utf-8")

    assert 'url: "https://ko-fi.com/shadesmaverick"' in script
    assert "ko-fi.com/yourname" not in script


def test_every_figure_the_method_page_asks_for_is_served(running_server):
    """A missing figure is invisible from the outside: the page still renders, just emptier.

    The alt text carries the argument for readers who cannot see the picture, so a silently
    broken image loses the statement as well as the illustration.
    """
    host, port = running_server
    connection = http.client.HTTPConnection(host, port, timeout=10)

    connection.request("GET", "/method")
    page = connection.getresponse().read().decode("utf-8")
    # References are relative so that one build serves from a root, a subpath or a filesystem.
    # From /method the browser resolves them against the root, which is what this asks for.
    referenced = re.findall(r'<img src="([^":]+)"', page)
    assert referenced, "the method page references no figures at all"

    for path in referenced:
        connection.request("GET", "/" + path.lstrip("/"))
        response = connection.getresponse()
        body = response.read()
        assert response.status == 200, f"{path} is referenced but not served"
        assert body, f"{path} is served empty"

    # Inside a <figure> the alt text is not decoration, it is the only version of the picture a
    # screen reader gets, so it has to carry the argument. Elsewhere -- the header axolotl --
    # an empty alt is the correct answer and this must not push anyone into writing "logo".
    figures = re.findall(r"<figure>.*?</figure>", page, re.S)
    assert len(figures) >= 6, f"only {len(figures)} figures on the method page"
    for figure in figures:
        alt = re.search(r'alt="([^"]*)"', figure)
        assert alt and len(alt.group(1)) > 60, figure[:200]
    connection.close()


def test_it_listens_on_loopback_only(running_server):
    """A damaged code's payload is frequently a secret. The socket must not be reachable."""
    host, _ = running_server
    assert host == "127.0.0.1"


def test_the_catalogue_is_built_from_titles_and_texts_alone():
    """Stateless: the page sends what it knows, the server re-encodes and lays out.

    No token, no cache: a catalogue can span more recoveries than the export cache holds, and
    the entries survive a server restart because there is nothing to survive.
    """
    body, content_type, filename = catalog_payload(
        {
            "entries": [
                {"title": "LED Lampe Badezimmer", "text": "CATALOG-A-0001", "ecc": "L"},
                {"title": "Heizung Keller", "text": "CATALOG-B-0002"},
                {"title": "", "text": "CATALOG-C-0003"},
                {"title": "leer", "text": "   "},
            ],
            "size_mm": 45,
        }
    )
    assert body.startswith(b"%PDF-")
    assert content_type == "application/pdf"
    assert filename == "catalog.pdf"
    assert b"(LED Lampe Badezimmer)" in body
    assert b"(untitled)" in body, "an empty title falls back rather than vanishing"
    assert b"CATALOG-C-0003" in body
    assert body.count(b"/Type /Page ") == 1, "three usable entries fit one page"


def test_the_catalogue_refuses_nothing_and_nonsense_sizes():
    with pytest.raises(ValueError):
        catalog_payload({"entries": [{"title": "x", "text": "  "}]})
    with pytest.raises(ValueError):
        catalog_payload({"entries": [{"title": "x", "text": "OK"}], "size_mm": 400})


def test_the_solve_can_stream_its_progress(running_server):
    """Newline-delimited JSON: the recovery narrated live, the result as the last line."""
    host, port = running_server
    connection = http.client.HTTPConnection(host, port, timeout=120)
    body = json.dumps({"image": _data_url(FIXTURE), "stream": True})
    connection.request(
        "POST", "/api/solve", body=body, headers={"Content-Type": "application/json"}
    )
    response = connection.getresponse()
    assert response.status == 200
    assert response.getheader("Content-Type", "").startswith("application/x-ndjson")

    lines = [json.loads(line) for line in response.read().splitlines() if line.strip()]
    connection.close()

    assert len(lines) > 5, "a recovery has more steps than that"
    assert lines[-1]["type"] == "result"
    assert lines[-1]["ok"] is True
    kinds = {line["type"] for line in lines}
    assert {"image", "finders", "grid", "sampled"} <= kinds
    # Coordinates in the events land on the photograph the page shows.
    grid = next(line for line in lines if line["type"] == "grid")
    assert all(0 <= x <= 4000 and 0 <= y <= 4000 for x, y in grid["corners"])


def test_a_foreign_host_header_is_refused(running_server):
    """DNS rebinding is the one road a hostile page has to a loopback server.

    The socket only listens on 127.0.0.1, and CORS never fires because the browser believes
    the attacker's rebound domain IS this origin. What survives the rebinding is the Host
    header, so the server refuses anything that does not name the loopback."""
    host, port = running_server
    connection = http.client.HTTPConnection(host, port, timeout=10)

    connection.request("GET", "/", headers={"Host": "attacker.example"})
    assert connection.getresponse().status == 403

    connection.request(
        "POST",
        "/api/solve",
        body=json.dumps({"image": "data:,x"}),
        headers={"Host": "attacker.example:8765", "Content-Type": "application/json"},
    )
    assert connection.getresponse().status == 403

    # The loopback names keep working, with and without a port.
    connection.request("GET", "/", headers={"Host": f"localhost:{port}"})
    assert connection.getresponse().status == 200
    connection.close()


def test_a_cross_origin_post_is_refused(running_server):
    """The attack the Host check cannot see, and the callers that must not be caught with it.

    Rebinding is not needed to reach a loopback server: a page on any origin can post straight
    at it, and the browser writes the Host header itself, so the check above sees exactly what
    it wants to see. What the page cannot write is the browser's own account of where the
    request came from -- and a caller that sends no such account is not a browser at all."""
    host, port = running_server
    body = json.dumps({"image": "data:,x"})

    for headers in (
        {"Origin": "https://evil.example"},
        {"Sec-Fetch-Site": "cross-site"},
        {"Origin": f"http://127.0.0.1:{port}", "Sec-Fetch-Site": "cross-site"},
    ):
        connection = http.client.HTTPConnection(host, port, timeout=10)
        connection.request(
            "POST", "/api/solve", body=body, headers={"Content-Type": "application/json", **headers}
        )
        assert connection.getresponse().status == 403, headers
        connection.close()

    # The page's own fetch, and curl or the CLI, which never had an Origin to send. Both reach
    # the recovery -- "data:,x" is simply not an image, which is a different answer entirely.
    for headers in (
        {"Origin": f"http://localhost:{port}", "Sec-Fetch-Site": "same-origin"},
        {},
    ):
        connection = http.client.HTTPConnection(host, port, timeout=10)
        connection.request(
            "POST", "/api/solve", body=body, headers={"Content-Type": "application/json", **headers}
        )
        response = connection.getresponse()
        assert response.status == 200, headers
        assert json.loads(response.read())["ok"] is False
        connection.close()


def test_the_caller_cannot_name_its_own_workload():
    """Every number the caller chooses is bounded, and the ones that are not numbers say so.

    These all used to travel straight into the recovery: a burst of any length, a frame of any
    size, a budget of any magnitude, and finder points that were neither three nor finite.
    NaN in particular survives every comparison the geometry makes, so it produced a grid that
    was neither placed nor refused."""
    one = _data_url(FIXTURE)

    assert solve_payload({"images": [one] * 13})["failure"].startswith("at most 12")
    assert solve_payload({})["failure"] == "no photograph was given"

    for points, expected in (
        ([{"x": 1, "y": 2}], "three finder points"),
        ([{"x": 1, "y": 2}] * 4, "three finder points"),
        ([{"x": "a", "y": 2}] * 3, "needs a numeric"),
        ([{"x": float("nan"), "y": 2.0}] * 3, "finite"),
        ([{"x": float("inf"), "y": 2.0}] * 3, "finite"),
    ):
        answer = solve_payload({"image": one, "finder_points": points})
        assert answer["ok"] is False
        assert expected in answer["failure"], points

    assert solve_payload({"image": one, "budget": "lots"})["failure"] == "budget must be a number"


def test_a_malformed_request_costs_an_answer_but_never_a_thread(running_server):
    """Two bodies that decode fine and then fall over on the way in.

    Both used to raise outside every handler in do_POST: a Content-Length that is not a number
    at the int(), and a JSON body that is not an object at the first .get(). The handler runs
    on a worker thread whose log_message is stubbed out, so the traceback went nowhere and the
    caller waited on a connection nobody was still holding. What each one must cost now is one
    refusal -- and the server must still be answering afterwards."""
    host, port = running_server

    connection = http.client.HTTPConnection(host, port, timeout=10)
    connection.putrequest("POST", "/api/solve")
    connection.putheader("Content-Type", "application/json")
    connection.putheader("Content-Length", "not-a-number")
    connection.endheaders()
    assert connection.getresponse().status == 400
    connection.close()

    for body in ("[1, 2]", '"a string"', "17"):
        connection = http.client.HTTPConnection(host, port, timeout=10)
        connection.request(
            "POST", "/api/solve", body=body, headers={"Content-Type": "application/json"}
        )
        response = connection.getresponse()
        assert response.status == 200
        assert json.loads(response.read())["ok"] is False
        connection.close()

    # The point of all of the above: the server is still there.
    connection = http.client.HTTPConnection(host, port, timeout=10)
    connection.request("GET", "/")
    assert connection.getresponse().status == 200
    connection.close()


def test_the_page_ships_hardened_headers(running_server):
    """No sniffing, no framing, no referrer -- and no inline script to allow at all."""
    host, port = running_server
    connection = http.client.HTTPConnection(host, port, timeout=10)
    connection.request("GET", "/")
    response = connection.getresponse()
    body = response.read()
    policy = response.getheader("Content-Security-Policy", "")
    assert response.getheader("X-Content-Type-Options") == "nosniff"
    assert response.getheader("Referrer-Policy") == "no-referrer"
    assert "frame-ancestors 'none'" in policy
    assert "'unsafe-inline'" not in policy.split("style-src")[0], (
        "scripts must never be allowed by blanket"
    )

    # The page carries no inline script at all -- its script is an external file under
    # script-src 'self'. That is the strongest position: nothing to hash, nothing an injected
    # <script> tag could ever satisfy. (The hash machinery in the server still exists for any
    # HTML that does carry an inline script, and it once cost a page its life to a CRLF-vs-LF
    # mismatch: the browser hashes after the parser normalises line endings.)
    import re as regex

    assert not regex.findall(rb"<script>", body), "the page grew an inline script"
    assert b'<script src="app.js">' in body

    # The page speaks to whichever backend.js is in place and never learns which one it got.
    # It has to be loaded first: app.js reads window.qrBackend while it is being parsed.
    assert b'<script src="backend.js">' in body
    assert body.index(b'<script src="backend.js">') < body.index(b'<script src="app.js">'), (
        "backend.js must be in place before app.js runs"
    )

    # Every reference is relative, which is what lets one build serve from a domain root, from
    # a project subpath and off a filesystem. A leading slash would work here and break there,
    # which is the kind of difference that is only ever discovered after publishing.
    for absolute in (rb'src="/', rb'href="/'):
        assert absolute not in body, f"the page grew a root-relative reference: {absolute!r}"

    served = {}
    for script in ("/app.js", "/backend.js"):
        connection.request("GET", script)
        response = connection.getresponse()
        served[script] = response.read()
        assert response.status == 200, script
        assert response.getheader("Content-Type", "").startswith("text/javascript"), script
        assert b"use strict" in served[script], script

    # This server hands out the HTTP backend; the worker one belongs to the static build, and
    # its worker.js is not served here at all.
    assert b"/api/solve" in served["/backend.js"]
    connection.request("GET", "/worker.js")
    assert connection.getresponse().status == 404

    # API answers and figures carry a policy that allows nothing at all.
    connection.request("GET", "/fig-known.svg")
    assert connection.getresponse().getheader("Content-Security-Policy") == "default-src 'none'"
    connection.close()
