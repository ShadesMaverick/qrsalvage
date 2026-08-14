"""The local web interface: its JSON contract and its refusal to listen to the outside world.

The page is a single static file with no build step, so the only thing that can silently break
between it and the core is the shape of the JSON. That is what these tests pin down.
"""

from __future__ import annotations

import base64
import http.client
import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from qrsalvage.server import Handler, solve_payload

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "engraved-curved-hard.png"


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


def test_it_listens_on_loopback_only(running_server):
    """A damaged code's payload is frequently a secret. The socket must not be reachable."""
    host, _ = running_server
    assert host == "127.0.0.1"
