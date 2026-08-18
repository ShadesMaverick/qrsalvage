"""A/B/C comparison: no bow, the tied bow, and the per-edge bow, on domed surfaces.

The dome axis exists because the cylinder axis cannot ask this question. A cylinder displaces
the top and bottom module rows identically, which is exactly what the original bow -- one
shared vector per sweep direction -- could express, so on that axis untying the edges has
nothing to add. A domed sheet bows opposite edges in opposite directions; a homography cannot
say it, and the tied bow cannot either at any parameter value. Whether that shape occurs is
not hypothetical: a photographed code whose four sides are visibly opposite arcs needed
hand-drawn boundary curves before the edges were untied.

Three arms, same images, same seeds: the flat grid (control -- if the axis is easy for it, the
level measures nothing), the tied bow reconstructed from the shipped per-edge one (top equal to
bottom, left to right -- the exact pre-untying model), and the shipped per-edge bow.

Usage:
    python scripts/ab_dome.py --samples 16
    python scripts/ab_dome.py --levels 0.08 0.12
"""

from __future__ import annotations

import argparse
import time
from dataclasses import replace

import numpy as np

from qrsalvage.core import pipeline
from qrsalvage.core.decoding import reencode
from qrsalvage.core.geometry import GridFit, _bowed_warp, _score
from qrsalvage.synth import Damage, render_photo

# Synthetic payload, same shape and length as a real pairing code. See scripts/difficulty.py.
TEXT = "Z:0123456789ABCDEF$I:00112233445566778899AABBCCDDEEFF1234%M:0000$D:0000000000"
BASELINE = Damage(contrast=0.20, curvature=0.30, module_px=8.0, stain=0.0)
LEVELS = (0.0, 0.05, 0.08, 0.10, 0.12, 0.15)


def tied_refine_bow(
    gray: np.ndarray,
    fit: GridFit,
    known_dark: np.ndarray,
    known_light: np.ndarray,
    scale: int = 12,
    start_delta: float = 3.0,
    min_delta: float = 0.1,
    on_step=None,
) -> GridFit:
    """The bow as it was before the edges were untied: one shared vector per sweep.

    Not kept in the library -- the shipped model contains it as the tied subspace -- but
    reconstructed here so the comparison is against the real previous behaviour rather than
    against memory. Descends over the four shared scalars and expands each candidate into the
    per-edge parametrisation, which is exactly the old warp.
    """
    shared = np.zeros(4, dtype=np.float64)

    def expand(s: np.ndarray) -> np.ndarray:
        return np.array([s[0], s[1], s[0], s[1], s[2], s[3], s[2], s[3]])

    def score(candidate: np.ndarray) -> GridFit:
        warped = _bowed_warp(gray, fit.corners, expand(candidate), fit.modules, scale)
        return _score(warped, fit.corners, fit.modules, scale, known_dark, known_light)

    best = score(shared)
    if best.quality < fit.quality:
        best = fit
    delta = start_delta
    while delta > min_delta:
        improved = False
        for axis in range(4):
            for step in (delta, -delta):
                candidate = shared.copy()
                candidate[axis] += step
                trial = score(candidate)
                if trial.quality > best.quality:
                    best, shared, improved = trial, candidate, True
        if not improved:
            delta /= 2.0
    return best


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

    shipped_refine = pipeline.refine_bow
    print(f"{args.samples} images per level and arm, budget {args.budget}")
    print(f"{'dome':>10} {'flat':>26} {'tied bow':>26} {'per-edge bow':>26}")

    for level in args.levels or LEVELS:
        damage = replace(BASELINE, dome=level)
        cells = []
        for arm in ("flat", "tied", "per-edge"):
            pipeline.BOW_REFINE = arm != "flat"
            pipeline.refine_bow = tied_refine_bow if arm == "tied" else shipped_refine
            successes, median, seconds = run(damage, args.samples, args.budget)
            cells.append(f"{successes:3d}/{args.samples:<3d} wrong~{median:3.0f} {seconds:4.0f}s")
        print(f"{level:10.2f} " + " ".join(f"{c:>26}" for c in cells), flush=True)

    pipeline.BOW_REFINE = True
    pipeline.refine_bow = shipped_refine
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
