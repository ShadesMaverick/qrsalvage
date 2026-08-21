"""Measure how long a recovery takes, with the noise floor printed next to it.

The question: did a change make the solver faster, or did the machine happen to be quieter?
Wall-clock time is the least trustworthy number this project measures. A success rate is a
property of the code; a duration is a property of the code *and* whatever else the machine was
doing, and the second term is invisible unless it is measured. Every optimisation claim made
without it is a guess wearing a number.

So this instrument does three things a plain timer does not:

  - It repeats, and reports the spread as well as the median. A run whose fastest and slowest
    repetitions differ by a fifth has not measured the solver, and the output says so instead
    of leaving it to be inferred.
  - It clears the level-fit cache before every repetition. That cache is keyed on the grid mask,
    so a second solve of the same photograph would find its own entries still warm and finish
    faster than any solve a user will ever run. Timing the second repetition of a warm process
    measures a situation that does not occur.
  - It compares against a saved baseline and refuses to call a difference real when it is
    smaller than the noise it was measured through.

It also prints `solved` and `candidates`, because the fastest way to speed up this solver is
to make it worse, and a change that trades an accepted candidate for an earlier exit shows up
here before it shows up in the corpus.

A baseline belongs to one machine in one state. Do not commit one -- the number it holds is
meaningless on any other computer, and a stale baseline is worse than none.

Usage:
    python scripts/runtime.py
    python scripts/runtime.py --repeats 7
    python scripts/runtime.py --save before.json
    python scripts/runtime.py --against before.json
    python scripts/runtime.py --images fixtures-local --repeats 3
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

import cv2

from qrsalvage.core import sampling
from qrsalvage.core.pipeline import solve

ROOT = Path(__file__).resolve().parents[1]

# Above this, the repetitions disagree enough that a change smaller than the disagreement
# cannot be attributed to the code. Chosen to be loose rather than strict: the point is to
# catch a machine under load, not to demand laboratory conditions.
NOISY_SPREAD = 0.10


def measure_one(path: Path, repeats: int) -> dict:
    """Time one photograph `repeats` times from a cold level-fit cache."""
    image = cv2.imread(str(path))
    if image is None:
        raise SystemExit(f"cannot read {path}")

    times: list[float] = []
    solved = False
    candidates = 0
    for _ in range(repeats):
        # Cold every time: see the module docstring. Without this, repetition two onwards
        # measures a cache no real recovery starts with.
        sampling._fit_operator.cache_clear()
        start = time.perf_counter()
        result = solve(image)
        times.append((time.perf_counter() - start) * 1000.0)
        solved = result.solved
        candidates = result.candidates_tried

    median = statistics.median(times)
    return {
        "image": path.name,
        "median_ms": median,
        "min_ms": min(times),
        "max_ms": max(times),
        "spread": (max(times) - min(times)) / median if median else 0.0,
        "solved": solved,
        "candidates": candidates,
    }


def report(rows: list[dict], repeats: int) -> None:
    print(
        f"\n{'image':32s} {'median':>9s} {'min':>9s} {'max':>9s} {'spread':>7s} "
        f"{'solved':>7s} {'cand':>5s}"
    )
    for row in rows:
        print(
            f"{row['image']:32s} {row['median_ms']:8.0f}  {row['min_ms']:8.0f}  "
            f"{row['max_ms']:8.0f}  {row['spread']:6.1%} {str(row['solved']):>7s} "
            f"{row['candidates']:5d}",
            flush=True,
        )

    total = sum(row["median_ms"] for row in rows)
    print(f"\n{'total of medians':32s} {total:8.0f} ms over {len(rows)} images, {repeats} repeats")

    unsolved = [row["image"] for row in rows if not row["solved"]]
    if unsolved:
        print(f"NOT SOLVED: {', '.join(unsolved)} -- a timing here measures a failure, not a solve")

    noisy = [row for row in rows if row["spread"] > NOISY_SPREAD]
    if noisy:
        worst = max(row["spread"] for row in noisy)
        print(
            f"\nspread above {NOISY_SPREAD:.0%} on {len(noisy)} of {len(rows)} images "
            f"(worst {worst:.0%}). The machine was not quiet. These numbers are an upper "
            f"bound; re-run with nothing else going on before comparing them to anything."
        )
    else:
        print(f"\nevery image within {NOISY_SPREAD:.0%} across repetitions -- a usable baseline")


def compare(rows: list[dict], baseline_path: Path) -> None:
    """Print the change per image, and say which changes the noise cannot support."""
    saved = json.loads(baseline_path.read_text(encoding="utf-8"))
    before = {row["image"]: row for row in saved["rows"]}

    print(f"\nagainst {baseline_path} ({saved['repeats']} repeats)\n")
    print(f"{'image':32s} {'before':>9s} {'after':>9s} {'change':>9s}  verdict")
    for row in rows:
        old = before.get(row["image"])
        if old is None:
            print(f"{row['image']:32s} {'-':>9s} {row['median_ms']:8.0f}  {'new':>9s}")
            continue
        change = (row["median_ms"] - old["median_ms"]) / old["median_ms"]
        # A difference is only a difference if it is bigger than the disagreement between
        # repetitions on either side of the comparison.
        floor = max(old["spread"], row["spread"])
        verdict = "within noise" if abs(change) <= floor else "real"
        if old["solved"] != row["solved"]:
            verdict = "SOLVED CHANGED -- the timing is beside the point"
        print(
            f"{row['image']:32s} {old['median_ms']:8.0f}  {row['median_ms']:8.0f}  "
            f"{change:+8.1%}  {verdict}",
            flush=True,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", default="fixtures", help="directory of .png photographs")
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--save", type=Path, default=None, help="write this run as a baseline")
    parser.add_argument("--against", type=Path, default=None, help="compare with a saved baseline")
    args = parser.parse_args()

    directory = Path(args.images)
    if not directory.is_absolute():
        directory = ROOT / directory
    paths = sorted(directory.glob("*.png"))
    if not paths:
        raise SystemExit(f"no .png images in {directory}")
    if args.repeats < 1:
        raise SystemExit("--repeats must be at least 1")
    if args.repeats < 3:
        print("warning: fewer than three repeats cannot show a spread worth reading")

    print(f"{directory}, {len(paths)} images, {args.repeats} repeats, cache cleared before each")
    rows = [measure_one(path, args.repeats) for path in paths]
    report(rows, args.repeats)

    if args.against is not None:
        compare(rows, args.against)
    if args.save is not None:
        args.save.write_text(
            json.dumps({"repeats": args.repeats, "rows": rows}, indent=2) + "\n", encoding="utf-8"
        )
        print(f"\nbaseline -> {args.save}  (machine-specific; do not commit)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
