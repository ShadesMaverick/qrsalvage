"""A/B comparison: flat homography against the bowed grid, on curved surfaces.

Both arms see exactly the same images from the same seeds. The curvature axis is the
instrument, because the bow was built for exactly the error a cylinder forces on a homography;
the flat axis (curvature near zero) is the control, where the bow has nothing to correct and
must not invent one.

Alongside the success rate the wrongly sampled known cells are reported, because that is the
number the bow acts on directly. A bow that halves the sampling error without yet flipping a
failure into a success has still moved the method's frontier -- the probe budget starts closer.

Usage:
    python scripts/ab_bow.py --samples 16
    python scripts/ab_bow.py --levels 0.6 0.8
"""

from __future__ import annotations

import argparse
import time
from dataclasses import replace

from qrsalvage.core import pipeline
from qrsalvage.core.decoding import reencode
from qrsalvage.synth import Damage, render_photo

# Synthetic payload, same shape and length as a real pairing code. See scripts/difficulty.py.
TEXT = "Z:0123456789ABCDEF$I:00112233445566778899AABBCCDDEEFF1234%M:0000$D:0000000000"
BASELINE = Damage(contrast=0.20, curvature=0.30, module_px=8.0, stain=0.0)
LEVELS = (0.05, 0.50, 0.70, 0.90)


def run(damage: Damage, samples: int, budget: int):
    matrix = reencode(TEXT)
    successes = 0
    wrong: list[int] = []
    start = time.perf_counter()
    for seed in range(samples):
        photo = render_photo(matrix, damage, seed=seed)
        result = pipeline.solve(photo, budget=budget)
        successes += int(result.text == TEXT)
        if result.wrong_sampled is not None:
            wrong.append(result.wrong_sampled)
    ordered = sorted(wrong)
    median = ordered[len(ordered) // 2] if ordered else float("nan")
    return successes, median, time.perf_counter() - start


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=16)
    parser.add_argument("--budget", type=int, default=4000)
    parser.add_argument("--levels", type=float, nargs="*", default=None)
    args = parser.parse_args()

    print(f"{args.samples} images per level and arm, budget {args.budget}")
    print(f"{'curvature':>10} {'flat':>22} {'bowed':>22}")

    for level in args.levels or LEVELS:
        damage = replace(BASELINE, curvature=level)
        cells = []
        for bow in (False, True):
            pipeline.BOW_REFINE = bow
            successes, median, seconds = run(damage, args.samples, args.budget)
            cells.append(f"{successes:3d}/{args.samples:<3d} wrong~{median:3.0f} {seconds:4.0f}s")
        print(f"{level:10.2f} {cells[0]:>22} {cells[1]:>22}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
