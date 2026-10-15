"""A/B comparison: single measurement against a consensus of several runs.

Both methods see exactly the same images, generated from the same seeds. Compared are the
success rate, the sampling error on the known cells and the effort the solver spends.

The effort belongs in there: a consensus that does not raise the success rate but lowers the
number of probes has still achieved something -- it improved the ordering.

Usage:
    python scripts/ab_ensemble.py --samples 12
    python scripts/ab_ensemble.py --modes off geometry --levels medium hard
"""

from __future__ import annotations

import argparse
import time
from dataclasses import replace

from qrsalvage.core.decoding import reencode
from qrsalvage.core.pipeline import solve
from qrsalvage.synth import Damage, render_photo

if __package__:
    from scripts.measurements import classify_recovery
else:  # direct execution
    from measurements import classify_recovery  # type: ignore[import-not-found,no-redef]

# Synthetic payload, same shape and length as a real pairing code. See scripts/difficulty.py.
TEXT = "Z:0123456789ABCDEF$I:00112233445566778899AABBCCDDEEFF1234%M:0000$D:0000000000"
BASELINE = Damage(contrast=0.20, curvature=0.30, module_px=8.0, stain=0.0)

LEVELS = (
    ("mild", replace(BASELINE, contrast=0.24)),
    ("medium", replace(BASELINE, contrast=0.16, curvature=0.40)),
    ("hard", replace(BASELINE, contrast=0.13, curvature=0.45, module_px=7.0, stain=0.15)),
    ("severe", replace(BASELINE, contrast=0.11, curvature=0.55, module_px=6.5, stain=0.25)),
)


def run(damage: Damage, samples: int, budget: int, ensemble: str):
    matrix = reencode(TEXT)
    correct = wrong_text = 0
    wrong: list[int] = []
    attempts = 0
    start = time.perf_counter()
    for seed in range(samples):
        photo = render_photo(matrix, damage, seed=seed)
        result = solve(photo, budget=budget, ensemble=ensemble)
        outcome = classify_recovery(result.text, TEXT)
        correct += int(outcome == "correct")
        wrong_text += int(outcome == "wrong")
        attempts += result.candidates_tried
        # wrong_sampled, not wrong_known: what is measured is the sampling the search actually
        # ran on. wrong_known scores the grid fit and is identical across all modes.
        wrong.append(result.wrong_sampled if result.wrong_sampled is not None else -1)
    valid = sorted(w for w in wrong if w >= 0)
    median = valid[len(valid) // 2] if valid else float("nan")
    return correct, wrong_text, median, attempts, time.perf_counter() - start


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=12)
    parser.add_argument("--budget", type=int, default=4000)
    parser.add_argument("--modes", nargs="*", default=["off", "geometry"])
    parser.add_argument("--levels", nargs="*", default=None, help="names from LEVELS, else all")
    args = parser.parse_args()

    levels = [level for level in LEVELS if args.levels is None or level[0] in args.levels]
    print(f"{args.samples} images per level, budget {args.budget}, modes {args.modes}\n")
    print(
        f"{'level':>12} {'mode':>10} {'correct':>10} {'wrong':>7} "
        f"{'wrong (median)':>16} {'attempts':>9} {'sec':>6}"
    )
    for name, damage in levels:
        for mode in args.modes:
            correct, wrong_text, median, attempts, seconds = run(
                damage, args.samples, args.budget, mode
            )
            print(
                f"{name:>12} {mode:>10} {correct:5d}/{args.samples:<4d} {wrong_text:7d} "
                f"{median:16.0f} {attempts:9d} {seconds:6.0f}",
                flush=True,  # otherwise everything sits in the buffer when redirected to a file
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
