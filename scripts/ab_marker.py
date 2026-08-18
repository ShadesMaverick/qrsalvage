"""A/B comparison: coloured strokes read as ink, or neutralised before the channel is read.

The marker axis draws saturated strokes across the code -- a highlighter, a guide line, a
stamp. Through the blue channel a red stroke is a row of fake dark modules; the neutralisation
in preprocess.py replaces strongly saturated pixels with mid-grey before any channel is read,
so the stroke turns from false ink into honest uncertainty.

The control level is zero strokes, where the two arms must be identical -- the neutralisation
gate must not fire on a photograph that has no colour to neutralise.

Usage:
    python scripts/ab_marker.py --samples 16
    python scripts/ab_marker.py --levels 1 3
"""

from __future__ import annotations

import argparse
import time
from dataclasses import replace

from qrsalvage.core import preprocess
from qrsalvage.core.decoding import reencode
from qrsalvage.core.pipeline import solve
from qrsalvage.synth import Damage, render_photo

# Synthetic payload, same shape and length as a real pairing code. See scripts/difficulty.py.
TEXT = "Z:0123456789ABCDEF$I:00112233445566778899AABBCCDDEEFF1234%M:0000$D:0000000000"
BASELINE = Damage(contrast=0.20, curvature=0.30, module_px=8.0, stain=0.0)
LEVELS = (0.0, 1.0, 2.0, 3.0, 4.0)


def run(damage: Damage, samples: int, budget: int):
    matrix = reencode(TEXT)
    correct = wrong = 0
    start = time.perf_counter()
    for seed in range(samples):
        photo = render_photo(matrix, damage, seed=seed)
        result = solve(photo, budget=budget)
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

    # The step ships off (cap zero, see preprocess.py) -- the instrument turns it on itself,
    # otherwise both arms would measure the shipped state twice.
    shipped_cap = preprocess.NEUTRAL_SATURATION_CAP
    print(f"{args.samples} images per level and arm, budget {args.budget}")
    print(f"{'strokes':>10} {'colour as ink':>26} {'colour neutralised':>26}")

    for level in args.levels or LEVELS:
        damage = replace(BASELINE, marker=level)
        cells = []
        for neutralise in (False, True):
            preprocess.NEUTRAL_SATURATION_CAP = 0.25 if neutralise else 0.0
            correct, wrong, seconds = run(damage, args.samples, args.budget)
            flag = f" {wrong}WRONG" if wrong else "       "
            cells.append(f"{correct:3d}/{args.samples:<3d}{flag} {seconds:4.0f}s")
        print(f"{level:10.1f} " + " ".join(f"{c:>26}" for c in cells), flush=True)

    preprocess.NEUTRAL_SATURATION_CAP = shipped_cap
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
