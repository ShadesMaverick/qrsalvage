"""A/B comparison: the two spatial uncertainty terms, on and off, against localized damage.

Both arms see exactly the same images from the same seeds. The stain axis is the instrument
because it is the damage the terms were built for: contiguous, locally destructive, invisible
from inside a fully covered cell. The contrast axis is measured too, as the control -- uniform
damage has no spatial structure to exploit, so the terms should neither help nor hurt there.
If they hurt, the weights are wrong.

Usage:
    python scripts/ab_sigma.py --samples 16
    python scripts/ab_sigma.py --axis stain --levels 0.4 0.5
"""

from __future__ import annotations

import argparse
import time
from dataclasses import replace

from qrsalvage.core import sampling
from qrsalvage.core.decoding import reencode
from qrsalvage.core.pipeline import solve
from qrsalvage.synth import Damage, render_photo

# Synthetic payload, same shape and length as a real pairing code. See scripts/difficulty.py.
TEXT = "Z:0123456789ABCDEF$I:00112233445566778899AABBCCDDEEFF1234%M:0000$D:0000000000"
BASELINE = Damage(contrast=0.20, curvature=0.30, module_px=8.0, stain=0.0)

AXES: dict[str, tuple[str, tuple[float, ...]]] = {
    "stain": ("stain", (0.35, 0.45, 0.55)),
    "contrast": ("contrast", (0.12, 0.10, 0.09)),
}

# (label, beacon weight, neighbourhood weight)
ARMS = (
    ("off/off", 0.0, 0.0),
    ("beacon", 2.0, 0.0),
    ("neighbor", 0.0, 1.0),
    ("both", 2.0, 1.0),
)


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
        print(f"{axis:>9} " + " ".join(f"{label:>16}" for label, *_ in ARMS))
        for level in args.levels or default_levels:
            damage = replace(BASELINE, **{field: level})
            cells = []
            for _, beacon, neighbor in ARMS:
                sampling.BEACON_WEIGHT = beacon
                sampling.NEIGHBOR_WEIGHT = neighbor
                start = time.perf_counter()
                successes, attempts = run(damage, args.samples, args.budget)
                cells.append(
                    f"{successes:3d}/{args.samples:<3d} {time.perf_counter() - start:4.0f}s"
                )
            print(f"{level:9.2f} " + " ".join(f"{c:>16}" for c in cells), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
