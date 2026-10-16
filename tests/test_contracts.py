"""API and pipeline contracts shared by every shell."""

import base64
import threading
from collections import defaultdict

import cv2
import numpy as np

from qrsalvage import api
from qrsalvage.core import oracle, pipeline
from qrsalvage.core.decoding import decode_matrix, reencode
from qrsalvage.core.layout import (
    deinterleave,
    extract_codewords,
    format_positions,
    read_format,
    write_format,
)
from qrsalvage.core.pipeline import SolveResult
from qrsalvage.core.qrspec import format_bits


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


def test_repair_evidence_rejects_more_unknown_codewords_than_redundancy_covers():
    modules = 21
    posterior = np.full((modules, modules), 0.99)
    known_dark, known_light = pipeline.structure_mask(modules)
    matrix = pipeline.ModuleMatrix(posterior, known_dark, known_light)
    positions = pipeline.codeword_positions(modules, 1, "L")[0]
    plan = pipeline.block_plan(1, "L")
    for word in positions[: plan.ec_per_block + 1]:
        matrix.posterior.flat[word[0]] = 0.5
    repair = pipeline.RepairResult(
        matrix=matrix.hard(),
        ecc="L",
        format_distance=0,
        blocks=1,
        erasures_used=plan.ec_per_block,
    )

    assert not pipeline.repair_has_sufficient_evidence(matrix, repair)


def test_repair_evidence_accepts_the_unique_decoding_boundary():
    modules = 29
    posterior = np.full((modules, modules), 0.99)
    known_dark, known_light = pipeline.structure_mask(modules)
    matrix = pipeline.ModuleMatrix(posterior, known_dark, known_light)
    write_format(matrix.posterior, "L", 0)
    positions = pipeline.codeword_positions(modules, 3, "L")[0]
    plan = pipeline.block_plan(3, "L")
    for word in positions[: plan.ec_per_block]:
        matrix.posterior.flat[word[0]] = 0.5
    repair = pipeline.RepairResult(
        matrix=matrix.hard(),
        ecc="L",
        mask=0,
        format_distance=0,
        blocks=1,
        erasures_used=plan.ec_per_block - 2,
        errors_corrected=1,
    )

    assert pipeline.repair_has_sufficient_evidence(matrix, repair)


def test_repair_evidence_rejects_a_corrected_format_header():
    modules = 21
    posterior = np.full((modules, modules), 0.99)
    known_dark, known_light = pipeline.structure_mask(modules)
    matrix = pipeline.ModuleMatrix(posterior, known_dark, known_light)
    repair = pipeline.RepairResult(
        matrix=matrix.hard(),
        ecc="L",
        format_distance=1,
        blocks=1,
    )

    assert not pipeline.repair_has_sufficient_evidence(matrix, repair)


def test_rejected_repair_evidence_cannot_be_bypassed_by_cell_probing():
    """Every decoder route must honour the same underdetermination gate."""
    encoded = []
    for index in range(2000):
        text = f"T{index:05d}"
        candidate = reencode(text, ecc="L")
        header = read_format(candidate)
        assert header is not None and pipeline.version_for_modules(candidate.shape[0]) == 1
        words = deinterleave(extract_codewords(candidate, header[1]), 1, header[0])[0]
        encoded.append((text, candidate, header, words))

    by_mask = defaultdict(list)
    for encoded_candidate in encoded:
        by_mask[encoded_candidate[2][1]].append(encoded_candidate)

    pair = None
    for candidates in by_mask.values():
        for left_index, left in enumerate(candidates):
            for right in candidates[left_index + 1 :]:
                differing = [
                    index
                    for index, (a, b) in enumerate(zip(left[3], right[3], strict=True))
                    if a != b
                ]
                one_bit = [
                    index
                    for index in differing
                    if (left[3][index] ^ right[3][index]).bit_count() == 1
                ]
                if len(differing) == 8 and one_bit:
                    pair = left, right, differing, one_bit[0]
                    break
            if pair is not None:
                break
        if pair is not None:
            break
    assert pair is not None

    (true_text, true_matrix, header, _), (wrong_text, wrong_matrix, _, _), differing, target = pair
    positions = pipeline.codeword_positions(true_matrix.shape[0], 1, header[0])[0]
    plan = pipeline.block_plan(1, header[0])
    assert len(differing) == plan.ec_per_block + 1

    hard = wrong_matrix.copy()
    true_side = [target] + [word for word in differing if word != target][:3]
    for word_index in true_side:
        for position in positions[word_index]:
            hard.flat[position] = true_matrix.flat[position]

    posterior = np.where(hard, 0.99, 0.01).astype(float)
    target_position = None
    for word_index in differing:
        for position in positions[word_index]:
            if true_matrix.flat[position] == wrong_matrix.flat[position]:
                continue
            distance = 0.005
            if word_index == target:
                target_position = position
                distance = 0.000001
            posterior.flat[position] = 0.5 + distance if hard.flat[position] else 0.5 - distance
    assert target_position is not None

    known_dark, known_light = pipeline.structure_mask(hard.shape[0])
    matrix = pipeline.ModuleMatrix(posterior, known_dark, known_light)
    search, repair = pipeline._decode_chain(matrix, budget=1)

    assert repair is not None and repair.ok
    assert not pipeline.repair_has_sufficient_evidence(matrix, repair)
    assert search.text is None


def test_probe_evidence_uses_the_candidate_format_not_the_original_format():
    """A probe that changes ECC must be judged against its own block plan."""
    text = "PAIRING-PAYLOAD-TEST"
    candidate = reencode(text, ecc="L")
    base = candidate.copy()
    write_format(base, "H", 0)
    assert read_format(base) == ("H", 0, 0)
    assert read_format(candidate) == ("L", 0, 0)

    posterior = np.where(base, 0.99, 0.01).astype(float)
    for positions in format_positions(base.shape[0]):
        for row, col in positions:
            if base[row, col] != candidate[row, col]:
                posterior[row, col] = 0.500001 if base[row, col] else 0.499999

    codeword_locations = pipeline.codeword_positions(base.shape[0], 1, "L")[0]
    for word in codeword_locations[: pipeline.block_plan(1, "L").ec_per_block + 1]:
        posterior.flat[word[0]] = 0.505 if base.flat[word[0]] else 0.495

    known_dark, known_light = pipeline.structure_mask(base.shape[0])
    matrix = pipeline.ModuleMatrix(posterior, known_dark, known_light)
    search, _ = pipeline._decode_chain(matrix, budget=256)

    assert search.text is None


def test_direct_decode_accepts_bch_corrected_format_copies():
    """Format BCH correction is valid evidence when no payload repair is involved."""
    text = "PAIRING-PAYLOAD-TEST"
    candidate = reencode(text, ecc="L")
    for positions in format_positions(candidate.shape[0]):
        row, col = positions[0]
        candidate[row, col] = not candidate[row, col]
    assert read_format(candidate) == ("L", 0, 1)

    posterior = np.where(candidate, 0.99, 0.01).astype(float)
    known_dark, known_light = pipeline.structure_mask(candidate.shape[0])
    matrix = pipeline.ModuleMatrix(posterior, known_dark, known_light)
    search, repair = pipeline._decode_chain(matrix, budget=1)

    assert search.text == text
    assert repair is None


def test_conflicting_valid_format_copies_cannot_choose_the_looser_ecc_gate():
    """Two exact but contradictory format copies provide no unique ECC evidence."""
    text = "VMDU"
    candidate = reencode(text, ecc="L")
    header = read_format(candidate)
    assert header is not None

    first, _second = format_positions(candidate.shape[0])
    conflicting = format_bits("M", header[1])
    for bit, (row, col) in enumerate(first):
        candidate[row, col] = bool(conflicting & (1 << bit))
    assert read_format(candidate) == ("M", header[1], 0)
    assert decode_matrix(candidate) != text

    posterior = np.where(candidate, 0.99, 0.01).astype(float)
    positions = pipeline.codeword_positions(candidate.shape[0], 1, "L")[0]
    for word in positions[: pipeline.block_plan(1, "L").ec_per_block + 1]:
        position = word[0]
        posterior.flat[position] = 0.505 if candidate.flat[position] else 0.495

    known_dark, known_light = pipeline.structure_mask(candidate.shape[0])
    matrix = pipeline.ModuleMatrix(posterior, known_dark, known_light)
    assert not pipeline.matrix_has_sufficient_evidence(matrix, "L")
    assert pipeline.matrix_has_sufficient_evidence(matrix, "M")

    search, _ = pipeline._decode_chain(matrix, budget=1)
    assert search.text is None


def test_repair_evidence_accepts_one_exact_and_one_correctable_format_copy():
    """One exact copy fixes the layout; its agreeing BCH copy remains independent evidence."""
    text = "REPAIR-FORMAT-EVIDENCE"
    candidate = reencode(text, ecc="L")
    header = read_format(candidate)
    assert header is not None
    first, _second = format_positions(candidate.shape[0])
    for row, col in first[:3]:
        candidate[row, col] = not candidate[row, col]

    copies = pipeline.read_format_copies(candidate)
    assert copies[0] is not None and copies[0][2] == 3
    assert copies[1] is not None and copies[1][2] == 0

    posterior = np.where(candidate, 0.99, 0.01).astype(float)
    known_dark, known_light = pipeline.structure_mask(candidate.shape[0])
    matrix = pipeline.ModuleMatrix(posterior, known_dark, known_light)
    repair = pipeline.RepairResult(
        matrix=candidate.copy(),
        ecc=header[0],
        mask=header[1],
        format_distance=0,
        blocks=1,
    )

    assert pipeline.repair_has_sufficient_evidence(matrix, repair)


def test_repair_evidence_requires_an_exact_format_witness():
    """Two corrected copies may agree only because two uncertain layers certify each other."""
    candidate = reencode("REPAIR-FORMAT-NO-EXACT-WITNESS", ecc="L")
    header = read_format(candidate)
    assert header is not None
    for copy_index, positions in enumerate(format_positions(candidate.shape[0])):
        row, col = positions[copy_index]
        candidate[row, col] = not candidate[row, col]

    copies = pipeline.read_format_copies(candidate)
    assert all(copy is not None and copy[2] == 1 for copy in copies)

    posterior = np.where(candidate, 0.99, 0.01).astype(float)
    known_dark, known_light = pipeline.structure_mask(candidate.shape[0])
    matrix = pipeline.ModuleMatrix(posterior, known_dark, known_light)
    repair = pipeline.RepairResult(
        matrix=candidate.copy(),
        ecc=header[0],
        mask=header[1],
        format_distance=1,
        blocks=1,
    )

    assert not pipeline.repair_has_sufficient_evidence(matrix, repair)
