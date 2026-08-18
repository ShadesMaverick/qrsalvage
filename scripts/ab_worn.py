"""A/B comparison: featureless patches read as confident cells, or handed over as unknowns.

The worn axis erases the bottom rows of the print entirely -- blank surface where modules
belong. Without the patch test every erased cell reaches the decoder as a clean, confident
light module, and Reed-Solomon is told the damage is anywhere but where it is.

Three counts per arm, not two, and the middle one is the point. A repair fed wrong erasure
positions does not merely fail -- with enough freedom it produces a *valid wrong* text, observed
on the real photograph that motivated this: the truth needed 10 erasures, the half-informed
ladder found presentable garbage at 18. A recovery instrument that only counted successes
would book that garbage as one.

Usage:
    python scripts/ab_worn.py --samples 16
    python scripts/ab_worn.py --levels 0.10 0.15
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
LEVELS = (0.0, 0.06, 0.09, 0.12, 0.15, 0.18)


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
    print(f"{'worn':>10} {'confident blanks':>28} {'blanks as unknowns':>28}")

    for level in args.levels or LEVELS:
        damage = replace(BASELINE, worn=level)
        cells = []
        for blank in (False, True):
            pipeline.BLANK_FEATURELESS = blank
            correct, wrong, seconds = run(damage, args.samples, args.budget)
            flag = f" {wrong}WRONG" if wrong else "       "
            cells.append(f"{correct:3d}/{args.samples:<3d}{flag} {seconds:4.0f}s")
        print(f"{level:10.2f} " + " ".join(f"{c:>28}" for c in cells), flush=True)

    pipeline.BLANK_FEATURELESS = True
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
