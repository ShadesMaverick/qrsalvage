"""Benchmark v2 spans QR layouts and keeps development separate from release evidence."""

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

from qrsalvage.core.decoding import reencode
from qrsalvage.core.layout import read_format
from qrsalvage.core.structure import version_for_modules
from scripts.benchmark import (
    BENCHMARK_SCHEMA,
    DEV_PAYLOADS,
    DEV_SEEDS,
    HOLDOUT_PAYLOADS,
    HOLDOUT_SEEDS,
    RESULT_FIELDS,
    ResultWriter,
    benchmark_exit_code,
    payloads_for_split,
    selected_seeds,
)


def test_payload_panel_spans_versions_ecc_levels_and_masks():
    for panel in (DEV_PAYLOADS, HOLDOUT_PAYLOADS):
        layouts = []
        for case in panel:
            matrix = reencode(case.text, case.ecc)
            header = read_format(matrix)
            assert header is not None
            layouts.append((version_for_modules(matrix.shape[0]), header[0], header[1]))

        assert {version for version, _, _ in layouts} == {1, 2, 3, 4, 5, 6}
        assert {ecc for _, ecc, _ in layouts} == {"L", "M", "Q", "H"}
        assert len({mask for _, _, mask in layouts}) >= 6

    assert {case.text for case in DEV_PAYLOADS}.isdisjoint({case.text for case in HOLDOUT_PAYLOADS})
    assert payloads_for_split("dev") == DEV_PAYLOADS
    assert payloads_for_split("holdout") == HOLDOUT_PAYLOADS


def test_development_and_release_seeds_are_disjoint_and_declared():
    assert DEV_SEEDS == (0, 1, 2, 3, 4, 5, 6, 7)
    assert HOLDOUT_SEEDS == (1009, 2027, 3067, 4099, 5147, 6203, 7283, 8363)
    assert not set(DEV_SEEDS) & set(HOLDOUT_SEEDS)
    assert selected_seeds("dev", samples=3) == DEV_SEEDS[:3]
    with pytest.raises(ValueError, match="holdout"):
        selected_seeds("holdout", samples=3)
    assert selected_seeds("holdout", release_candidate=True) == HOLDOUT_SEEDS


def test_release_benchmark_fails_on_any_failure_or_wrong_decode():
    assert benchmark_exit_code("holdout", correct=0, wrong=0, failed=144) != 0
    assert benchmark_exit_code("holdout", correct=143, wrong=0, failed=1) != 0
    assert benchmark_exit_code("holdout", correct=143, wrong=1, failed=0) != 0
    assert benchmark_exit_code("holdout", correct=144, wrong=0, failed=0) == 0


def test_rows_carry_the_parameters_and_worktree_provenance():
    assert {"budget", "dirty", "diff_sha256"} <= set(RESULT_FIELDS)


def test_result_writer_emits_equivalent_jsonl_and_csv(tmp_path):
    row = {
        "schema": BENCHMARK_SCHEMA,
        "split": "dev",
        "payload": "short-l",
        "seed": 0,
        "outcome": "correct",
    }
    json_path = tmp_path / "run.jsonl"
    csv_path = tmp_path / "run.csv"

    with ResultWriter(json_path, "jsonl") as writer:
        writer.write(row)
    with ResultWriter(csv_path, "csv") as writer:
        writer.write(row)

    assert json.loads(json_path.read_text(encoding="utf-8")) == row
    with csv_path.open(newline="", encoding="utf-8") as handle:
        parsed = next(csv.DictReader(handle))
    assert {key: parsed[key] for key in row} == {key: str(value) for key, value in row.items()}
    assert all(not value for key, value in parsed.items() if key not in row)


def test_benchmark_runs_through_the_documented_script_path():
    root = Path(__file__).resolve().parents[1]

    completed = subprocess.run(
        [sys.executable, "-m", "scripts.benchmark", "--help"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "--release-candidate" in completed.stdout
