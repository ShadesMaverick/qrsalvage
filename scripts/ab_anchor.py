"""A/B comparison: one constructed third finder, or the anchor sweep over its scales.

The worn axis is the instrument because it manufactures the anchor sweep's exact situation: the
bottom rows erased whole take the bottom-left finder with them, the grid hangs on the top pair
plus a constructed third, and the side away from the pair has no witness -- the featureless
damping already hands the blank area to Reed-Solomon, so what remains is purely the geometry
question the sweep exists for. Whether the right-angle construction landed in the right descent
basin decides the case, and without the sweep there is exactly one basin on offer.

Wrong texts are counted separately in both arms: the sweep hands several geometries to the
decoder, and a decoder given more chances to be wrong must be watched for taking them.

Usage:
    python scripts/ab_anchor.py --samples 16
    python scripts/ab_anchor.py --levels 0.09 0.12
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
LEVELS = (0.0, 0.09, 0.12, 0.15, 0.18)


def run(damage: Damage, samples: int, budget: int):
    matrix = reencode(TEXT)
    correct = wrong = 0
    start = time.perf_counter()
    for seed in range(samples):
        photo = render_photo(matrix, damage, seed=seed)
        result = pipeline.solve(photo, budget=budget)
        if result.text == TEXT:
            correct += 1
        elif result.text is not None:
            wrong += 1
    return correct, wrong, time.perf_counter() - start


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=16)
    parser.add_argument("--budget", type=int, default=4000)
    parser.add_argument("--levels", type=float, nargs="*", default=None)
    args = parser.parse_args()

    print(f"{args.samples} images per level and arm, budget {args.budget}")
    print(f"{'worn':>10} {'single basin':>26} {'anchor sweep':>26}")

    for level in args.levels or LEVELS:
        damage = replace(BASELINE, worn=level)
        cells = []
        for sweep in (False, True):
            pipeline.ANCHOR_SWEEP = sweep
            correct, wrong, seconds = run(damage, args.samples, args.budget)
            flag = f" {wrong}WRONG" if wrong else "       "
            cells.append(f"{correct:3d}/{args.samples:<3d}{flag} {seconds:4.0f}s")
        print(f"{level:10.2f} " + " ".join(f"{c:>26}" for c in cells), flush=True)

    pipeline.ANCHOR_SWEEP = True
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
