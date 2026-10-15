"""What several photographs of one code buy over a single one -- and by which fusion rule.

The two ensembles inside ensemble.py both vary the measurement within one image, and both were
measured to solve no additional case: every member inherits the one grid, so they reproduce its
error together. Separate photographs are the variation that applies. This script quantifies
that claim instead of asserting it, and settles the fusion rule on the same evidence.

The comparison is paired: every rule sees the identical set of member solves within a trial, so
a difference between rules is a difference between rules and not between random draws.

Each photograph of a trial gets its own angle, curvature and light, because that is what makes
two real photographs independent. Varying only the noise seed would reproduce exactly the
correlated-members failure this whole path exists to escape.

Usage:
    python scripts/multi_image.py
    python scripts/multi_image.py --axis stain --images 4 --samples 16
"""

from __future__ import annotations

import argparse
import math
import time
from dataclasses import replace
from typing import Any

import numpy as np

from qrsalvage.core.decoding import reencode
from qrsalvage.core.ensemble import fuse_images
from qrsalvage.core.matrix import ModuleMatrix
from qrsalvage.core.pipeline import MEMBER_BUDGET, SolveResult, _decode_chain, solve
from qrsalvage.core.structure import structure_mask
from qrsalvage.synth import Damage, render_photo

if __package__:
    from scripts.measurements import classify_recovery
else:  # direct execution
    from measurements import classify_recovery  # type: ignore[import-not-found,no-redef]

# Same shape and length as a real Zigbee pairing payload, and entirely made up.
TEXT = "Z:0123456789ABCDEF$I:00112233445566778899AABBCCDDEEFF1234%M:0000$D:0000000000"

BASELINE = Damage(contrast=0.20, curvature=0.30, module_px=8.0)
RULES = ("probability", "log-odds", "pooled")

# Two damage axes, because they ask different questions of the fusion. Low contrast spoils every
# cell of every photograph alike, so three photographs carry three copies of the same handicap.
# A stain lands somewhere else each time, so what one photograph loses the others still hold --
# that is the shape of damage this path is for, and the difference between the two axes is worth
# seeing rather than averaging away.
AXES: dict[str, tuple[str, tuple[float, ...]]] = {
    "contrast": ("contrast", (0.10, 0.09, 0.08)),
    "stain": ("stain", (0.40, 0.50, 0.60)),
}
STAIN_BASELINE = Damage(contrast=0.18, curvature=0.30, module_px=8.0)


def wilson(successes: int, trials: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson interval for a binomial rate.

    See scripts/difficulty.py for why not the textbook one.
    """
    if trials == 0:
        return (0.0, 1.0)
    p = successes / trials
    denominator = 1 + z**2 / trials
    centre = (p + z**2 / (2 * trials)) / denominator
    margin = z * math.sqrt(p * (1 - p) / trials + z**2 / (4 * trials**2)) / denominator
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def photograph(damage: Damage, rng: np.random.Generator, seed: int) -> np.ndarray:
    """One more photograph of the same code: another angle, another light, another day."""
    varied = replace(
        damage,
        rotation_deg=float(rng.uniform(-8.0, 8.0)),
        curvature=float(np.clip(damage.curvature * rng.uniform(0.7, 1.3), 0.05, 1.1)),
        glare=float(np.clip(damage.glare * rng.uniform(0.5, 1.5), 0.0, 0.9)),
        module_px=float(damage.module_px * rng.uniform(0.9, 1.15)),
    )
    return render_photo(reencode(TEXT), varied, seed=seed)


def trial(damage: Damage, count: int, budget: int, seed: int) -> tuple[int, int, dict[str, bool]]:
    """One trial: `count` photographs, solved alone and then fused by every rule.

    Every photograph is solved once, at the full budget. That is the fair baseline -- what the
    tool gives someone who hands it one photo -- and it costs nothing extra, because the budget
    only governs how long the probe runs. The posterior it leaves behind, which is all the
    fusion consumes, is the same whatever the budget was.
    """
    rng = np.random.default_rng(seed)
    members = [solve(photograph(damage, rng, seed * 100 + i), budget=budget) for i in range(count)]
    outcomes_alone = [classify_recovery(m.text, TEXT) for m in members]
    alone = sum(outcome == "correct" for outcome in outcomes_alone)
    alone_wrong = sum(outcome == "wrong" for outcome in outcomes_alone)

    usable = [m for m in members if m.matrix is not None]

    def reliability(member: SolveResult) -> tuple[int, float]:
        assert member.wrong_known is not None and member.timing is not None
        return member.wrong_known, -member.timing

    usable.sort(key=reliability)
    outcomes: dict[str, bool] = dict.fromkeys(RULES, False)
    if len(usable) < 2:
        return alone, alone_wrong, outcomes

    modules = usable[0].modules
    same = [m for m in usable if m.modules == modules]
    known_dark, known_light = structure_mask(modules)
    posteriors = [m.matrix.posterior for m in same if m.matrix is not None]

    for rule in RULES:
        consensus = fuse_images(posteriors, known_dark, known_light, rule=rule)
        mm = ModuleMatrix(consensus.posterior, known_dark, known_light)
        search, _ = _decode_chain(mm, budget)
        outcomes[rule] = search.text == TEXT
    return alone, alone_wrong, outcomes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", type=int, default=3, help="photographs per trial")
    parser.add_argument("--samples", type=int, default=12, help="trials per damage level")
    parser.add_argument("--budget", type=int, default=4000, help="probe budget for the fusion")
    parser.add_argument("--axis", choices=sorted(AXES), default=None)
    parser.add_argument("--levels", type=float, nargs="*", default=None)
    args = parser.parse_args()

    axes = [args.axis] if args.axis else sorted(AXES)
    print(
        f"{args.images} photographs per trial, {args.samples} trials per level, "
        f"budget {args.budget} (members {MEMBER_BUDGET})"
    )
    print("each photograph gets its own angle, curvature, light and resolution\n")

    header = " ".join(f"{r:>22}" for r in RULES)

    for axis in axes:
        field, default_levels = AXES[axis]
        base = STAIN_BASELINE if axis == "stain" else BASELINE
        print(f"\n--- {axis} (all other damage held at the baseline) ---")
        print(f"{axis:>9} {'single image':>22} {header}")
        for level in args.levels or default_levels:
            changes: dict[str, Any] = {field: level}
            damage = replace(base, **changes)
            alone_total = 0
            alone_wrong_total = 0
            wins = dict.fromkeys(RULES, 0)
            start = time.perf_counter()
            for sample in range(args.samples):
                alone, alone_wrong, outcomes = trial(
                    damage, args.images, args.budget, seed=sample + 1
                )
                alone_total += alone
                alone_wrong_total += alone_wrong
                for rule, ok in outcomes.items():
                    wins[rule] += int(ok)

            images = args.samples * args.images
            low, high = wilson(alone_total, images)
            rate = alone_total / images
            wrong_note = f" !{alone_wrong_total}" if alone_wrong_total else ""
            cells = [
                f"{alone_total:3d}/{images:<3d} {rate:4.0%} [{low:.0%},{high:.0%}]{wrong_note}"
            ]
            for rule in RULES:
                low, high = wilson(wins[rule], args.samples)
                cells.append(
                    f"{wins[rule]:3d}/{args.samples:<3d} {wins[rule] / args.samples:4.0%} "
                    f"[{low:.0%},{high:.0%}]"
                )
            print(
                f"{level:9.2f} "
                + " ".join(f"{c:>22}" for c in cells)
                + f"   {time.perf_counter() - start:5.0f} s",
                flush=True,
            )

    print("\nsingle-image rate counts every photograph; fusion rate counts every trial")
    print("!N marks N valid decodes with the wrong known payload")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
