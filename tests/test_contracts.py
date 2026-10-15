"""API and pipeline contracts shared by every shell."""

import base64
import threading

import cv2
import numpy as np

from qrsalvage import api
from qrsalvage.core import oracle, pipeline
from qrsalvage.core.pipeline import SolveResult


def _image_data_url() -> str:
    image = np.full((20, 20, 3), 255, dtype=np.uint8)
    ok, encoded = cv2.imencode(".png", image)
    assert ok
    return "data:image/png;base64," + base64.b64encode(encoded.tobytes()).decode("ascii")


def _failed_result() -> SolveResult:
    return SolveResult(text=None, failure="test stopped after contract capture")


def test_solve_payload_turns_invalid_base64_into_a_json_failure():
    answer = api.solve_payload({"image": "data:image/png;base64,%%%not-base64%%%"})

    assert answer["ok"] is False
    assert "base64" in answer["failure"].lower()


def test_solve_payload_turns_empty_base64_into_a_json_failure():
    answer = api.solve_payload({"image": "data:image/png;base64,"})

    assert answer["ok"] is False
    assert "image" in answer["failure"].lower()


def test_solve_payload_refuses_unknown_ensemble_without_raising():
    answer = api.solve_payload({"image": _image_data_url(), "ensemble": "invented"})

    assert answer["ok"] is False
    assert "ensemble" in answer["failure"].lower()


def test_solve_payload_refuses_a_non_object_finder_point():
    answer = api.solve_payload(
        {
            "image": _image_data_url(),
            "finder_points": [None, {"x": 3, "y": 4}, {"x": 5, "y": 6}],
        }
    )

    assert answer["ok"] is False
    assert "numeric x and y" in answer["failure"]


def test_solve_many_passes_band_to_single_image(monkeypatch):
    captured = {}

    def fake_solve(image, **kwargs):
        captured.update(kwargs)
        return _failed_result()

    monkeypatch.setattr(pipeline, "solve", fake_solve)
    pipeline.solve_many([np.zeros((1, 1, 3), dtype=np.uint8)], band=0.27)

    assert captured["band"] == 0.27


def test_solve_many_passes_band_to_every_member(monkeypatch):
    seen = []

    def fake_solve(image, **kwargs):
        seen.append(kwargs["band"])
        return _failed_result()

    monkeypatch.setattr(pipeline, "solve", fake_solve)
    pipeline.solve_many(
        [np.zeros((1, 1, 3), dtype=np.uint8), np.zeros((1, 1, 3), dtype=np.uint8)],
        band=0.27,
    )

    assert seen == [0.27, 0.27]


def test_oracle_decode_contains_an_injected_backend_failure():
    def broken(_image):
        raise RuntimeError("backend broke")

    with oracle.using(broken, lambda text, ecc: np.zeros((21, 21), dtype=bool)):
        assert oracle.decode(np.zeros((1, 1), dtype=np.uint8)) is None


def test_oracle_backend_scope_restores_the_previous_backend():
    def first(_image):
        return "first"

    def second(_image):
        return "second"

    def encode(text, ecc):
        return np.zeros((21, 21), dtype=bool)

    with oracle.using(first, encode):
        assert oracle.decode(np.zeros((1, 1), dtype=np.uint8)) == "first"
        with oracle.using(second, encode):
            assert oracle.decode(np.zeros((1, 1), dtype=np.uint8)) == "second"
        assert oracle.decode(np.zeros((1, 1), dtype=np.uint8)) == "first"


def test_oracle_scopes_do_not_leak_between_threads():
    barrier = threading.Barrier(2)
    answers: dict[str, str | None] = {}

    def encode(text, ecc):
        return np.zeros((21, 21), dtype=bool)

    def worker(name: str) -> None:
        def decode(_image):
            return name

        with oracle.using(decode, encode):
            barrier.wait()
            answers[name] = oracle.decode(np.zeros((1, 1), dtype=np.uint8))

    threads = [threading.Thread(target=worker, args=(name,)) for name in ("first", "second")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert answers == {"first": "first", "second": "second"}
