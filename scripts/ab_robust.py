"""A/B comparison: the robust level estimate, on and off, against lying known cells.

Both arms see exactly the same images from the same seeds. The tear axis is the instrument
because it is the damage the robustness was built for: a torn paper edge whose shadow strip
and curl make a column of known cells measure the wrong brightness (the observed failure is
documented at ROBUST_LEVELS in sampling.py). The stain axis is localized damage of a
different shape, and the contrast axis is the control -- uniform damage produces no outlier
known cells, so the robust arm should behave like the stock arm there. If it loses cases on
the control, the thresholds are wrong.

Usage:
    python scripts/ab_robust.py --samples 16
    python scripts/ab_robust.py --axis tear --levels 0.8 1.0
"""

from __future__ import annotations

import argparse
import time
from dataclasses import replace
from typing import Any

from qrsalvage.core import sampling
from qrsalvage.core.decoding import reencode
from qrsalvage.core.pipeline import solve
from qrsalvage.synth import Damage, render_photo

# Synthetic payload, same shape and length as a real pairing code. See scripts/difficulty.py.
TEXT = "Z:0123456789ABCDEF$I:00112233445566778899AABBCCDDEEFF1234%M:0000$D:0000000000"
BASELINE = Damage(contrast=0.20, curvature=0.30, module_px=8.0, stain=0.0)

AXES: dict[str, tuple[str, tuple[float, ...]]] = {
    "tear": ("tear", (0.60, 0.80, 1.00)),
    "stain": ("stain", (0.35, 0.45, 0.55)),
    "contrast": ("contrast", (0.12, 0.10, 0.09)),
}

# (label, ROBUST_LEVELS)
ARMS = (("stock", False), ("robust", True))


def run(damage: Damage, samples: int, budget: int) -> tuple[int, int]:
    matrix = reencode(TEXT)
    successes = 0
    attempts = 0
    for seed in range(samples):
        photo = render_photo(matrix, damage, seed=seed)
        result = solve(photo, budget=budget)
        successes += int(result.text == TEXT)
        attempts += result.candidates_tried
    return successes, attempts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=16)
    parser.add_argument("--budget", type=int, default=4000)
    parser.add_argument("--axis", choices=sorted(AXES), default=None)
    parser.add_argument("--levels", type=float, nargs="*", default=None)
    args = parser.parse_args()

    axes = [args.axis] if args.axis else sorted(AXES)
    print(f"{args.samples} images per level and arm, budget {args.budget}")

    for axis in axes:
        field, default_levels = AXES[axis]
        print(f"\n--- {axis} ---")
        print(f"{axis:>9} " + " ".join(f"{label:>16}" for label, _ in ARMS))
        for level in args.levels or default_levels:
            changes: dict[str, Any] = {field: level}
            damage = replace(BASELINE, **changes)
            cells = []
            for _, robust in ARMS:
                sampling.ROBUST_LEVELS = robust
                start = time.perf_counter()
                successes, attempts = run(damage, args.samples, args.budget)
                cells.append(
                    f"{successes:3d}/{args.samples:<3d} {time.perf_counter() - start:4.0f}s"
                )
            print(f"{level:9.2f} " + " ".join(f"{c:>16}" for c in cells), flush=True)
    sampling.ROBUST_LEVELS = True
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
