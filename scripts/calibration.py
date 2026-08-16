"""Where the posterior's confidence is honest and where it is not.

Everything downstream consumes the posterior as if it meant something: the uncertainty band
decides what counts as doubtful, the flip cost orders the probe, the codeword reliability picks
the erasures. On four real photographs of one code this was measured to be a shaky foundation:
cells the model called certain beyond 0.999 were wrong 1.7 % of the time, and most actual errors
ranked far outside anything the probe would ever visit.

This script makes that measurable on demand, on the synthetic corpus where the truth is known
for every cell -- not just for the few hundred the standard fixes. The split into border (the
known cells) and middle (the data cells) is the point of the exercise: the model is *fitted* on
the border, so it can be honest there and blind in the middle, and a single pooled number would
hide exactly that.

Usage:
    python scripts/calibration.py
    python scripts/calibration.py --samples 24 --budget 1
"""

from __future__ import annotations

import argparse
from dataclasses import replace

import numpy as np

from qrsalvage.core import sampling
from qrsalvage.core.decoding import reencode
from qrsalvage.core.pipeline import solve
from qrsalvage.synth import Damage, render_photo

# Synthetic payload, same shape and length as a real pairing code. See scripts/difficulty.py.
TEXT = "Z:0123456789ABCDEF$I:00112233445566778899AABBCCDDEEFF1234%M:0000$D:0000000000"
BASELINE = Damage(contrast=0.20, curvature=0.30, module_px=8.0, stain=0.0)

LEVELS = (
    ("mild", BASELINE),
    ("faint", replace(BASELINE, contrast=0.12)),
    ("stained", replace(BASELINE, stain=0.5)),
)

BINS = ((0.5, 0.7), (0.7, 0.9), (0.9, 0.99), (0.99, 0.999), (0.999, 1.001))


def align(truth: np.ndarray, hard: np.ndarray) -> np.ndarray | None:
    """Bring the true matrix into the orientation the solver happened to read.

    The synthetic camera rotates the code a little, and the solver orients by the finders, so
    the two agree up to one of the eight square symmetries. Picking the best-agreeing one is
    safe here because the payload fills the code: a wrong orientation agrees near chance while
    the right one agrees near perfectly, and anything without a clear winner is dropped rather
    than scored.
    """
    candidates = []
    for k in range(4):
        candidates.append(np.rot90(truth, k))
        candidates.append(np.rot90(truth.T, k))
    scored = sorted((float((c == hard).mean()), i) for i, c in enumerate(candidates))
    if scored[-1][0] < 0.75:
        return None
    return candidates[scored[-1][1]]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=16)
    parser.add_argument(
        "--budget",
        type=int,
        default=1,
        help="probe budget. 1 by default: the posterior under test does not depend on it",
    )
    parser.add_argument(
        "--spatial",
        choices=["on", "off"],
        default="on",
        help="the two neighbourhood terms in sampling.py; 'off' restores the island model",
    )
    args = parser.parse_args()

    if args.spatial == "off":
        sampling.BEACON_WEIGHT = 0.0
        sampling.NEIGHBOR_WEIGHT = 0.0

    matrix = reencode(TEXT)
    print(f"payload {len(TEXT)} characters, {matrix.shape[0]} modules, {args.samples} images/level")

    for name, damage in LEVELS:
        pooled: dict[str, list[tuple[float, bool]]] = {"border": [], "middle": []}
        used = 0
        for seed in range(args.samples):
            photo = render_photo(matrix, damage, seed=seed)
            result = solve(photo, budget=args.budget)
            if result.matrix is None or result.modules != matrix.shape[0]:
                continue
            truth = align(matrix, result.matrix.hard())
            if truth is None:
                continue
            used += 1
            posterior = result.matrix.posterior
            locked = result.matrix.locked
            claimed = np.maximum(posterior, 1 - posterior)
            correct = (posterior >= 0.5) == truth
            for region, mask in (("border", locked), ("middle", ~locked)):
                pooled[region].extend(
                    zip(claimed[mask].tolist(), correct[mask].tolist(), strict=True)
                )

        print(f"\n--- {name} ({used} of {args.samples} images usable) ---")
        print(f"{'claimed':>16} {'border n':>9} {'right':>7} {'middle n':>9} {'right':>7}")
        expected_error = {}
        for lo, hi in BINS:
            row = [f"{lo:.3f}-{hi:.3f}".rjust(16)]
            for region in ("border", "middle"):
                values = [(c, r) for c, r in pooled[region] if lo <= c < hi]
                if values:
                    accuracy = sum(r for _, r in values) / len(values)
                    row.append(f"{len(values):>9} {accuracy:>6.1%}")
                else:
                    row.append(f"{'-':>9} {'-':>7}")
            print(" ".join(row))
        for region in ("border", "middle"):
            values = pooled[region]
            if not values:
                continue
            # Expected calibration error: how far claimed confidence and measured accuracy
            # diverge, weighted by how many cells make each claim.
            total = len(values)
            ece = 0.0
            for lo, hi in BINS:
                inside = [(c, r) for c, r in values if lo <= c < hi]
                if inside:
                    claimed_mean = sum(c for c, _ in inside) / len(inside)
                    accuracy = sum(r for _, r in inside) / len(inside)
                    ece += abs(claimed_mean - accuracy) * len(inside) / total
            overall = sum(r for _, r in values) / total
            expected_error[region] = ece
            print(f"{region}: {total} cells, {overall:.2%} right overall, ECE {ece:.4f}")
        if "border" in expected_error and "middle" in expected_error:
            ratio = expected_error["middle"] / max(expected_error["border"], 1e-9)
            print(f"middle miscalibration is {ratio:.1f}x the border's")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
