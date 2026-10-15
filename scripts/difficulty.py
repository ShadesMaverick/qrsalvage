"""Measure the success rate against the degree of damage -- with error bars.

Why the error bars are necessary: with four images per level, the confidence interval around an
observed rate of 4/4 reaches down to roughly 40 percent. Numbers like that look decisive and
carry no statement. So each level is measured over many images, and the interval is printed
alongside so it stays visible what the number can support.

Only one kind of damage is varied at a time; otherwise a threshold cannot be attributed.

Usage:
    python scripts/difficulty.py
    python scripts/difficulty.py --axis contrast --samples 24
"""

from __future__ import annotations

import argparse
import math
import time
from dataclasses import replace
from typing import Any

from qrsalvage.core.decoding import reencode
from qrsalvage.core.pipeline import solve
from qrsalvage.synth import Damage, render_photo

if __package__:
    from scripts.measurements import classify_recovery
else:  # direct execution: ``python scripts/difficulty.py``
    from measurements import classify_recovery  # type: ignore[import-not-found,no-redef]

# Same length, same character set and same field structure as a real Zigbee pairing payload,
# so the measurements stay comparable -- but entirely made up. A real one would put a device
# secret into a public repository.
TEXT = "Z:0123456789ABCDEF$I:00112233445566778899AABBCCDDEEFF1234%M:0000$D:0000000000"

BASELINE = Damage(contrast=0.20, curvature=0.30, module_px=8.0, stain=0.0)

AXES: dict[str, tuple[str, tuple[float, ...]]] = {
    "contrast": ("contrast", (0.30, 0.24, 0.20, 0.16, 0.13, 0.11, 0.09)),
    "curvature": ("curvature", (0.20, 0.35, 0.50, 0.65, 0.80, 0.95)),
    "resolution": ("module_px", (9.0, 8.0, 7.0, 6.0, 5.0, 4.0)),
    "stain": ("stain", (0.0, 0.10, 0.20, 0.30, 0.40, 0.50)),
    "tear": ("tear", (0.0, 0.20, 0.40, 0.60, 0.80, 1.00)),
    # Every level here has been measured; the axis deliberately stops at 3.0 rather than
    # running on into ground nobody has looked at. Expect it to stay flat: a corner-local
    # displacement is largely absorbable by a homography, which has four corners to move,
    # and up to 3.0 it costs about 4 percent of the known cells and no recoveries at all.
    # A flat axis is a statement about the damage, not a broken instrument.
    "curl": ("curl", (0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0)),
    "remnant": ("remnant", (0.0, 0.25, 0.5, 0.75, 1.0)),
    # Radial distortion: bows opposite edges in opposite directions, which no homography and
    # no tied bow can express. The per-edge bow was built against this axis; scripts/ab_dome.py
    # holds the three-arm measurement.
    "dome": ("dome", (0.0, 0.05, 0.08, 0.10, 0.12, 0.15)),
    # The print ends: bottom rows erased whole, blank surface where modules belong. Breaks
    # through two mechanisms at once -- the lost bottom-left finder and the featureless area
    # read as confident light cells; scripts/ab_worn.py separates what the patch handling buys.
    "worn": ("worn", (0.0, 0.06, 0.09, 0.12, 0.15, 0.18)),
    # Coloured strokes across the code -- the one axis that needs colour. Measures whether the
    # pipeline knows that colour is never ink; scripts/ab_marker.py holds the A/B.
    "marker": ("marker", (0.0, 1.0, 2.0, 3.0, 4.0)),
}


def wilson(successes: int, trials: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson interval for a binomial rate.

    The textbook p +/- z*sqrt(p(1-p)/n) fails exactly where we spend most of our time: near
    zero or one it produces intervals that run outside the valid range, and at 0/n or n/n it
    produces a width of zero.
    """
    if trials == 0:
        return (0.0, 1.0)
    p = successes / trials
    denominator = 1 + z**2 / trials
    centre = (p + z**2 / (2 * trials)) / denominator
    margin = z * math.sqrt(p * (1 - p) / trials + z**2 / (4 * trials**2)) / denominator
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def measure(damage: Damage, samples: int, budget: int):
    """Solve `samples` independent images of the same damage level."""
    matrix = reencode(TEXT)
    correct = wrong = 0
    wrong_cells: list[int] = []
    attempts = 0
    start = time.perf_counter()
    for seed in range(samples):
        photo = render_photo(matrix, damage, seed=seed)
        result = solve(photo, budget=budget)
        outcome = classify_recovery(result.text, TEXT)
        correct += int(outcome == "correct")
        wrong += int(outcome == "wrong")
        attempts += result.candidates_tried
        if result.wrong_sampled is not None:
            wrong_cells.append(result.wrong_sampled)
    ordered = sorted(wrong_cells)
    median = ordered[len(ordered) // 2] if ordered else float("nan")
    return correct, wrong, median, attempts, time.perf_counter() - start


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--axis", choices=sorted(AXES), default=None)
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--budget", type=int, default=4000)
    args = parser.parse_args()

    axes = [args.axis] if args.axis else sorted(AXES)
    print(f"payload {len(TEXT)} characters, {args.samples} images per level, budget {args.budget}")

    for name in axes:
        field, values = AXES[name]
        print(f"\n--- {name} (all other damage held at the baseline) ---")
        print(
            f"{name:>12} {'correct':>10} {'wrong':>7} {'rate':>7} {'95% interval':>16} "
            f"{'wrong (median)':>16} {'attempts':>9} {'sec':>6}"
        )
        for value in values:
            changes: dict[str, Any] = {field: value}
            damage = replace(BASELINE, **changes)
            correct, wrong, median, attempts, seconds = measure(damage, args.samples, args.budget)
            low, high = wilson(correct, args.samples)
            rate = correct / args.samples
            print(
                f"{value:12.2f} {correct:5d}/{args.samples:<4d} {wrong:7d} {rate:7.0%} "
                f"{f'[{low:.0%}, {high:.0%}]':>16} {median:16.0f} {attempts:9d} {seconds:6.0f}",
                flush=True,  # otherwise everything sits in the buffer when redirected to a file
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
