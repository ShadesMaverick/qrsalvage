"""A/B comparison: the coarse restart of a badly fitted grid, on and off.

Both arms see exactly the same images from the same seeds. The axes are the ones that
actually produce badly seated grids, and which those are was measured rather than assumed:
at the baseline, strong curvature puts every image over the 5 percent trigger, the smallest
module size and the strongest tear put some over, while contrast and stain -- damage that
destroys cells without displacing the grid -- never fire at all. Those two are therefore not
axes here; there is nothing for this escalation to do on them.

The `fired` column is the point of the control: an escalation that never triggers cannot
help, and one that triggers on healthy images is buying its rescues with everyone else's
runtime.

The rescue is gated on the same objective the descent optimises, so it cannot return a worse
*grid*. That is not the same as not returning a worse *result*: quality is a proxy for the
grid being right, and this measurement is what says whether the proxy holds.

Usage:
    python scripts/ab_restart.py --samples 16
    python scripts/ab_restart.py --axis curvature --levels 0.8 0.95
"""

from __future__ import annotations

import argparse
import time
from dataclasses import replace
from typing import Any

from qrsalvage.core import pipeline
from qrsalvage.core.decoding import reencode
from qrsalvage.core.pipeline import solve
from qrsalvage.synth import Damage, render_photo

# Synthetic payload, same shape and length as a real pairing code. See scripts/difficulty.py.
TEXT = "Z:0123456789ABCDEF$I:00112233445566778899AABBCCDDEEFF1234%M:0000$D:0000000000"
BASELINE = Damage(contrast=0.20, curvature=0.30, module_px=8.0, stain=0.0)

AXES: dict[str, tuple[str, tuple[float, ...]]] = {
    "curvature": ("curvature", (0.70, 0.85, 0.95)),
    "resolution": ("module_px", (5.0, 4.5, 4.0)),
    "tear": ("tear", (0.80, 1.00)),
}

# (label, COARSE_RESTART)
ARMS = (("off", False), ("restart", True))


def run(damage: Damage, samples: int, budget: int) -> tuple[int, int]:
    """Solve `samples` images and report (successes, times the escalation fired)."""
    matrix = reencode(TEXT)
    successes = 0
    fired = 0
    for seed in range(samples):
        photo = render_photo(matrix, damage, seed=seed)
        result = solve(photo, budget=budget)
        successes += int(result.text == TEXT)
        # The escalation fires on the fit handed to it, which is what per_size holds; the
        # reported wrong_known is what came back out, so the two differ exactly when it ran.
        if result.per_size and result.wrong_known is not None:
            handed = min(
                (f for f in result.per_size if f.modules == result.modules),
                key=lambda f: f.wrong_known,
                default=None,
            )
            if handed is not None and handed.wrong_known > pipeline.COARSE_RESTART_THRESHOLD * max(
                handed.known_total, 1
            ):
                fired += 1
    return successes, fired


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
        print(f"{axis:>10} " + " ".join(f"{label:>22}" for label, _ in ARMS))
        for level in args.levels or default_levels:
            changes: dict[str, Any] = {field: level}
            damage = replace(BASELINE, **changes)
            cells = []
            for _, restart in ARMS:
                pipeline.COARSE_RESTART = restart
                start = time.perf_counter()
                successes, fired = run(damage, args.samples, args.budget)
                cells.append(
                    f"{successes:3d}/{args.samples:<3d} {fired:2d}fired "
                    f"{time.perf_counter() - start:4.0f}s"
                )
            print(f"{level:10.2f} " + " ".join(f"{c:>22}" for c in cells), flush=True)
    pipeline.COARSE_RESTART = True
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
