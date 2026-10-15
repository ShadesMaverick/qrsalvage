"""How many outlier rounds should the level fit get -- and does the cap protect or truncate?

The loop in `estimate_levels` drops known cells that lie, refits, and repeats, up to
`ROBUST_ROUNDS`. A profile made it look like a performance question: 85 % of calls on a hard
photograph use every round they are given, so rounds two through four are roughly three
quarters of the most expensive function in a solve.

Replaying the loop on 400 captured real inputs said something else. It cannot oscillate -- each
round only ever removes cells -- so it does not thrash; it *spirals*. Dropping outliers shrinks
the residual scatter, a smaller scatter puts more cells outside the threshold, and those get
dropped in turn. Given twelve rounds, 98.2 % of calls do eventually stop, but the median takes
six or seven, and the support drops from 203 known cells to around 120 on the way.

Which makes the cap the question this script exists for. Four rounds is not "enough rounds to
converge" -- convergence needs six or seven. It is a stop partway down a spiral, and the number
that matters is not how long the loop takes but whether the cells it has already eaten were
lying or merely inconvenient. Two outcomes are possible and they point opposite ways:

  - More rounds read better. Then the shipped estimate is truncated, the fix costs time rather
    than saving it, and the profile was pointing at the wrong thing entirely.
  - More rounds read worse. Then the spiral is eating good cells, four rounds is accidentally
    protective, and the real repair is a criterion that stops for a reason instead of a counter
    that stops at a number.

Measured on `wrong_known` as well as the success rate, because the cell count moves first --
the level fit sets the threshold every cell is read against, so a worse fit shows up as wrong
cells long before it costs a recovery.

Usage:
    python scripts/ab_rounds.py
    python scripts/ab_rounds.py --samples 30 --rounds 4 8 12
"""

from __future__ import annotations

import argparse
import math
import time

from qrsalvage.core import sampling
from qrsalvage.core.decoding import reencode
from qrsalvage.core.pipeline import solve
from qrsalvage.synth import Damage, render_photo

if __package__:
    from scripts.measurements import classify_recovery
else:  # direct execution
    from measurements import classify_recovery  # type: ignore[import-not-found,no-redef]

# Same shape as a real Zigbee pairing payload, entirely made up. See difficulty.py.
TEXT = "Z:0123456789ABCDEF$I:00112233445566778899AABBCCDDEEFF1234%M:0000$D:0000000000"

# The damage the robust loop was built for: known cells that lie. A stain crosses a finder and
# a tear runs through the border, so some of the cells the standard fixes are simply wrong --
# which is the only situation where dropping any of them can help.
#
# Set near the knee of each axis, and the first attempt was not. At stain 0.35 and tear 0.60
# over the difficulty baseline, every arm recovered every image and the median wrong-cell count
# was zero across the board: a test with nothing to separate. A level fit only decides anything
# where the threshold it sets is close to the cells it is read against, so the contrast comes
# down with the damage until the arms have room to disagree.
CASES: dict[str, Damage] = {
    "stain": Damage(contrast=0.13, curvature=0.50, module_px=6.0, stain=0.50),
    "tear": Damage(contrast=0.13, curvature=0.50, module_px=6.0, tear=1.00),
    "clean": Damage(contrast=0.13, curvature=0.50, module_px=6.0),
}


def wilson(successes: int, total: int) -> tuple[float, float]:
    """95 % interval, so a rate over few samples cannot pretend to be a measurement."""
    if total == 0:
        return 0.0, 0.0
    z = 1.96
    rate = successes / total
    centre = rate + z * z / (2 * total)
    spread = z * math.sqrt((rate * (1 - rate) + z * z / (4 * total)) / total)
    return (
        max(0.0, (centre - spread) / (1 + z * z / total)),
        min(1.0, (centre + spread) / (1 + z * z / total)),
    )


def measure(
    damage: Damage, rounds: int, samples: int, budget: int
) -> tuple[int, int, float, float]:
    matrix = reencode(TEXT)
    previous = sampling.ROBUST_ROUNDS
    sampling.ROBUST_ROUNDS = rounds
    try:
        correct = wrong_text = 0
        wrong: list[int] = []
        start = time.perf_counter()
        for seed in range(samples):
            result = solve(render_photo(matrix, damage, seed=seed), budget=budget)
            outcome = classify_recovery(result.text, TEXT)
            correct += int(outcome == "correct")
            wrong_text += int(outcome == "wrong")
            if result.wrong_known is not None:
                wrong.append(result.wrong_known)
        seconds = time.perf_counter() - start
    finally:
        sampling.ROBUST_ROUNDS = previous
    ordered = sorted(wrong)
    median = float(ordered[len(ordered) // 2]) if ordered else float("nan")
    return correct, wrong_text, median, seconds


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--budget", type=int, default=2000)
    parser.add_argument("--rounds", type=int, nargs="+", default=[1, 4, 8, 12])
    parser.add_argument("--case", choices=sorted(CASES), default=None, help="one axis only")
    args = parser.parse_args()

    chosen = {args.case: CASES[args.case]} if args.case else CASES
    print(f"{args.samples} images per cell, budget {args.budget}, shipped ROBUST_ROUNDS = 4")
    for name, damage in chosen.items():
        print(f"\n--- {name} ---")
        print(
            f"{'rounds':>7} {'correct':>10} {'bad text':>8} {'rate':>7} "
            f"{'95% interval':>16} {'cells':>7} {'sec':>7}"
        )
        for rounds in args.rounds:
            correct, wrong_text, median, seconds = measure(
                damage, rounds, args.samples, args.budget
            )
            low, high = wilson(correct, args.samples)
            print(
                f"{rounds:7d} {correct:5d}/{args.samples:<4d} {wrong_text:8d} "
                f"{correct / args.samples:7.0%} "
                f"{f'[{low:.0%}, {high:.0%}]':>16} {median:7.0f} {seconds:7.0f}",
                flush=True,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
