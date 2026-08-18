"""A/B comparison: letting the grid objective listen to the unknown cells, or not.

The known cells ring the code, so the objective has always been deaf to the several hundred
data cells in its middle -- and those are where a half-module phase error shows up most
plainly, because every one of them straddles two modules at once. The term under test adds
their mean posterior confidence to the quality; the weight is what this script measures.

Two things have to come out of it, and they pull against each other. The term has to widen the
basin of attraction enough that the fine descent stops settling next to the right answer --
that is what motivated it, on a photograph of a torn printout. And it must not start choosing
grids that merely look tidy: coherence alone is maximised by any placement that lands wholly
inside a uniform patch, and only the known cells rule that out. A weight too high will show up
here as a wrong version chosen, or as recoveries lost on the axes that were fine before.

Usage:
    python scripts/ab_coherence.py --samples 12
    python scripts/ab_coherence.py --axis curvature --weights 0 0.4 0.8
"""

from __future__ import annotations

import argparse
import time
from dataclasses import replace
from typing import Any

from qrsalvage.core import geometry
from qrsalvage.core.decoding import reencode
from qrsalvage.core.pipeline import solve
from qrsalvage.synth import Damage, render_photo

# Synthetic payload, same shape and length as a real pairing code. See scripts/difficulty.py.
TEXT = "Z:0123456789ABCDEF$I:00112233445566778899AABBCCDDEEFF1234%M:0000$D:0000000000"
BASELINE = Damage(contrast=0.20, curvature=0.30, module_px=8.0, stain=0.0)

AXES: dict[str, tuple[str, tuple[float, ...]]] = {
    "contrast": ("contrast", (0.13, 0.11, 0.09)),
    "curvature": ("curvature", (0.50, 0.70, 0.85)),
    "resolution": ("module_px", (6.0, 5.0, 4.5)),
    "stain": ("stain", (0.35, 0.45, 0.55)),
}

WEIGHTS = (0.0, 0.4, 0.8)


def run(damage: Damage, samples: int, budget: int) -> tuple[int, int]:
    """Solve `samples` images; report (recoveries, times a wrong module count was chosen)."""
    matrix = reencode(TEXT)
    successes = 0
    wrong_size = 0
    for seed in range(samples):
        photo = render_photo(matrix, damage, seed=seed)
        result = solve(photo, budget=budget)
        successes += int(result.text == TEXT)
        # The failure mode a too-eager coherence term would produce: a tidy-looking grid at
        # the wrong size. Worth counting separately -- it is silent in the recovery rate
        # whenever the image was going to fail anyway.
        if result.modules is not None and result.modules != matrix.shape[0]:
            wrong_size += 1
    return successes, wrong_size


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=12)
    parser.add_argument("--budget", type=int, default=2000)
    parser.add_argument("--axis", choices=sorted(AXES), default=None)
    parser.add_argument("--weights", type=float, nargs="*", default=None)
    args = parser.parse_args()

    weights = args.weights if args.weights is not None else list(WEIGHTS)
    axes = [args.axis] if args.axis else sorted(AXES)
    shipped = geometry.COHERENCE_WEIGHT
    print(f"{args.samples} images per level and weight, budget {args.budget}")

    for axis in axes:
        field, levels = AXES[axis]
        print(f"\n--- {axis} ---")
        print(f"{axis:>10} " + " ".join(f"{'w=' + format(w, '.1f'):>20}" for w in weights))
        for level in levels:
            changes: dict[str, Any] = {field: level}
            damage = replace(BASELINE, **changes)
            cells = []
            for weight in weights:
                geometry.COHERENCE_WEIGHT = weight
                start = time.perf_counter()
                successes, wrong_size = run(damage, args.samples, args.budget)
                cells.append(
                    f"{successes:3d}/{args.samples:<3d} {wrong_size:2d}badsize "
                    f"{time.perf_counter() - start:4.0f}s"
                )
            print(f"{level:10.2f} " + " ".join(f"{c:>20}" for c in cells), flush=True)
    geometry.COHERENCE_WEIGHT = shipped
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
