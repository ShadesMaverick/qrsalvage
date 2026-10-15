"""Benchmark v2: varied QR layouts, sealed holdout seeds, and machine-readable evidence.

The original instruments deliberately answer one question at a time, but most of them use one
payload and the same low-numbered seeds. Repeating those seeds while tuning turns them into a
training set. This runner complements, rather than replaces, those diagnostic axes. Both panels
cover versions 1 through 6, every error-correction level and six distinct masks; development and
release evidence use disjoint payloads and renderer seeds; every case is written as JSONL or CSV.

The holdout is intentionally inconvenient. It only runs as one complete, frozen panel when
``--release-candidate`` is explicit, so looking at its first three cases while tuning is not an
option accidentally offered by the CLI.

Usage:
    python -m scripts.benchmark --split dev --samples 4 --out out/benchmark-dev.jsonl
    python -m scripts.benchmark --split holdout --release-candidate --out out/benchmark-rc.jsonl
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Literal, TextIO

from qrsalvage.core.decoding import reencode
from qrsalvage.core.layout import read_format
from qrsalvage.core.pipeline import solve
from qrsalvage.core.structure import version_for_modules
from qrsalvage.synth import Damage, render_photo
from scripts.measurements import classify_recovery

BENCHMARK_SCHEMA = "qrsalvage-benchmark-v2"
DEV_SEEDS = (0, 1, 2, 3, 4, 5, 6, 7)
HOLDOUT_SEEDS = (1009, 2027, 3067, 4099, 5147, 6203, 7283, 8363)
Split = Literal["dev", "holdout"]
Format = Literal["jsonl", "csv"]


@dataclass(frozen=True)
class PayloadCase:
    name: str
    text: str
    ecc: str


# Chosen by measured encoder output, not by assuming length implies layout. The tests independently
# re-encode both panels and hold versions, encoded ECC levels and mask diversity to the declared
# coverage. The release payloads are different module matrices, not new damage on the dev codes.
DEV_PAYLOADS = (
    PayloadCase("short-l", "QRSALVAGE-1", "L"),  # v1, mask 1
    PayloadCase("short-h", "QRSALVAGE-4", "H"),  # v2, mask 2
    PayloadCase("inventory-q", "ASSET:WAREHOUSE-A:RACK-17:SERIAL-3", "Q"),  # v3, mask 6
    PayloadCase(
        "wifi-m", "WIFI:T:WPA;S:Workshop;P:correct-horse-battery-staple;;10", "M"
    ),  # v4, mask 4
    PayloadCase("url-h", "https://example.invalid/recover/device/10", "H"),  # v5, mask 3
    PayloadCase(
        "zigbee-h",
        "Z:0123456789ABCDEF$I:00112233445566778899AABBCCDDEEFF1234%M:0000$D:00000000002",
        "H",
    ),  # v6, mask 0
)

HOLDOUT_PAYLOADS = (
    PayloadCase("holdout-v1-l", "HOLDOUT-ALPHA-9", "L"),  # v1, mask 7
    PayloadCase("holdout-v2-h", "HOLDOUT-ALPHA-1", "H"),  # v2, mask 2
    PayloadCase("holdout-v3-q", "ASSET:SECOND-SITE:BIN-04:UNIT-14", "Q"),  # v3, mask 3
    PayloadCase(
        "holdout-v4-m", "WIFI:T:WPA;S:GuestLab;P:glass-river-copper;;20", "M"
    ),  # v4, mask 4
    PayloadCase("holdout-v5-h", "https://offline.invalid/archive/label/17", "H"),  # v5, mask 6
    PayloadCase(
        "holdout-v6-h",
        "Z:FFEEDDCCBBAA9988$I:FFEEDDCCBBAA99887766554433221100ABCD%M:1234$D:98765432103",
        "H",
    ),  # v6, mask 1
)

DAMAGE_LEVELS = (
    ("mild", Damage(contrast=0.24, curvature=0.25, module_px=8.0)),
    ("faint", Damage(contrast=0.13, curvature=0.40, module_px=7.0)),
    ("stained", Damage(contrast=0.18, curvature=0.35, module_px=8.0, stain=0.45)),
)

RESULT_FIELDS = (
    "schema",
    "commit",
    "dirty",
    "diff_sha256",
    "split",
    "budget",
    "payload",
    "seed",
    "damage",
    "expected_version",
    "expected_ecc",
    "expected_mask",
    "outcome",
    "reported_version",
    "wrong_known",
    "known_total",
    "wrong_sampled",
    "uncertain",
    "attempts",
    "seconds",
)


def selected_seeds(
    split: Split, samples: int | None = None, *, release_candidate: bool = False
) -> tuple[int, ...]:
    """Return development samples, or the complete sealed holdout for a release candidate."""
    if split == "holdout":
        if not release_candidate:
            raise ValueError("the holdout only runs with --release-candidate")
        return HOLDOUT_SEEDS
    if samples is None:
        return DEV_SEEDS
    if not 1 <= samples <= len(DEV_SEEDS):
        raise ValueError(f"development samples must be between 1 and {len(DEV_SEEDS)}")
    return DEV_SEEDS[:samples]


def payloads_for_split(split: Split) -> tuple[PayloadCase, ...]:
    """Use different module matrices for development and release evidence."""
    return HOLDOUT_PAYLOADS if split == "holdout" else DEV_PAYLOADS


class ResultWriter:
    """Append one flat result per case as JSONL or CSV."""

    def __init__(self, path: Path, fmt: Format):
        self.path = path
        self.fmt = fmt
        self.handle: TextIO | None = None
        self.csv_writer: csv.DictWriter[str] | None = None

    def __enter__(self) -> ResultWriter:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("w", encoding="utf-8", newline="")
        if self.fmt == "csv":
            self.csv_writer = csv.DictWriter(self.handle, fieldnames=RESULT_FIELDS)
            self.csv_writer.writeheader()
        return self

    def write(self, row: dict[str, object]) -> None:
        if self.handle is None:
            raise RuntimeError("result writer is not open")
        if self.fmt == "jsonl":
            self.handle.write(json.dumps(row, sort_keys=True) + "\n")
        else:
            if self.csv_writer is None:
                raise RuntimeError("CSV writer is not open")
            self.csv_writer.writerow(row)
        self.handle.flush()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self.handle is not None:
            self.handle.close()


def _git_provenance() -> tuple[str, bool, str]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        diff = subprocess.run(
            ["git", "diff", "HEAD", "--binary"],
            check=True,
            capture_output=True,
        ).stdout
        return commit, bool(status), hashlib.sha256(diff).hexdigest()
    except (OSError, subprocess.CalledProcessError):
        return "unknown", True, "unknown"


def run_cases(
    split: Split,
    seeds: Iterable[int],
    writer: ResultWriter,
    *,
    budget: int,
) -> tuple[int, int, int]:
    """Run the full payload × damage × seed panel and return correct, wrong, failed."""
    commit, dirty, diff_sha256 = _git_provenance()
    totals = {"correct": 0, "wrong": 0, "failed": 0}
    for payload in payloads_for_split(split):
        matrix = reencode(payload.text, payload.ecc)
        header = read_format(matrix)
        assert header is not None
        expected_ecc, expected_mask, _ = header
        expected_version = version_for_modules(matrix.shape[0])
        for damage_name, damage in DAMAGE_LEVELS:
            for seed in seeds:
                started = time.perf_counter()
                result = solve(render_photo(matrix, damage, seed=seed), budget=budget)
                seconds = time.perf_counter() - started
                outcome = classify_recovery(result.text, payload.text)
                totals[outcome] += 1
                writer.write(
                    {
                        "schema": BENCHMARK_SCHEMA,
                        "commit": commit,
                        "dirty": dirty,
                        "diff_sha256": diff_sha256,
                        "split": split,
                        "budget": budget,
                        "payload": payload.name,
                        "seed": seed,
                        "damage": damage_name,
                        "expected_version": expected_version,
                        "expected_ecc": expected_ecc,
                        "expected_mask": expected_mask,
                        "outcome": outcome,
                        "reported_version": result.version,
                        "wrong_known": result.wrong_known,
                        "known_total": result.known_total,
                        "wrong_sampled": result.wrong_sampled,
                        "uncertain": result.uncertain,
                        "attempts": result.candidates_tried,
                        "seconds": round(seconds, 6),
                    }
                )
                print(
                    f"{payload.name:10s} {damage_name:8s} seed {seed:4d}: {outcome}",
                    flush=True,
                )
    return totals["correct"], totals["wrong"], totals["failed"]


def benchmark_exit_code(split: Split, correct: int, wrong: int, failed: int) -> int:
    """A release panel is a gate; development runs remain descriptive unless unsafe."""
    if wrong:
        return 2
    if split == "holdout" and failed:
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("dev", "holdout"), default="dev")
    parser.add_argument(
        "--samples", type=int, default=4, help="development seeds; ignored for holdout"
    )
    parser.add_argument("--release-candidate", action="store_true")
    parser.add_argument("--budget", type=int, default=4000)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--format", choices=("jsonl", "csv"), default=None)
    args = parser.parse_args()

    split: Split = args.split
    try:
        seeds = selected_seeds(split, args.samples, release_candidate=args.release_candidate)
    except ValueError as exc:
        parser.error(str(exc))
    fmt: Format = args.format or ("csv" if args.out.suffix.lower() == ".csv" else "jsonl")
    payloads = payloads_for_split(split)
    print(
        f"{BENCHMARK_SCHEMA}: {split}, {len(payloads)} payloads, {len(DAMAGE_LEVELS)} damage "
        f"levels, {len(seeds)} seeds -> {args.out}"
    )
    with ResultWriter(args.out, fmt) as writer:
        correct, wrong, failed = run_cases(split, seeds, writer, budget=args.budget)
    print(f"\ncorrect {correct}, valid-but-wrong {wrong}, failed {failed}")
    return benchmark_exit_code(split, correct, wrong, failed)


if __name__ == "__main__":
    raise SystemExit(main())
