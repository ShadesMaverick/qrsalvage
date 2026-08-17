"""Measuring each cell several times instead of once.

A single preprocessing pass gives you a probability per module but no indication of how much
that probability is worth. One pass can be very confident and very wrong -- for instance when
a blur radius happens to average across a stain.

So the same cell is measured under several conditions: different colour channel, different
contrast stretch, different blur, different cell inset, slightly displaced corners. Where the
runs agree the cell is safe. Where they argue it is not -- and that disagreement is exactly
what the solver needs in order to probe the right cell first.

MEASURED RESULT, and it is a negative one: fixing the grid before the ensemble makes the whole
thing useless. In an A/B comparison across four damage levels with twelve images each, the
consensus solved not a single additional image (12/12, 10/12, 9/12, 1/12 -- identical to the
single run). The reason: the dominant error source is the grid, because a homography cannot
represent the cylindrical curvature. All conditions share it, so they share its error too --
ten correlated measurements of the same systematic error reproduce it, only with false
confidence. The 0.5 px jitter was meant to cover that but is far too small at roughly 9 px per
module.

The second attempt, over geometries rather than preprocessings (see geometry_consensus below),
does hit the right variance: nine independently fitted grids give one to three wrong known
cells on the real photograph instead of the same number nine times over, and on the hardest
synthetic level the median of wrongly sampled known cells drops from 7 to 4. The sampling
demonstrably improves.

It still solves no additional image, at twice the runtime. The bottleneck has moved past the
sampling: the ordered probe flips at most 22 cells and cannot repair, even with perfectly
calibrated uncertainty, the number of real errors present at that level.

Both ensembles are therefore off by default but kept. geometry_consensus is precisely the
stage an erasure decoder wants in front of it.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .geometry import GridFit, refine_corners
from .preprocess import prepare
from .sampling import estimate_levels, posterior_dark, sample_cells, warp
from .structure import timing_score


@dataclass(frozen=True)
class SamplingConfig:
    """One measurement condition. Deliberately spread coarsely, not tuned."""

    channel: int = 0
    clip_limit: float = 3.0
    blur_sigma: float = 1.5
    inset: float = 0.30
    jitter: float = 0.0
    jitter_seed: int = 0


DEFAULT_CONFIGS: tuple[SamplingConfig, ...] = (
    SamplingConfig(channel=0, clip_limit=3.0, blur_sigma=1.5, inset=0.30),
    SamplingConfig(channel=0, clip_limit=2.0, blur_sigma=1.2, inset=0.25),
    SamplingConfig(channel=0, clip_limit=4.0, blur_sigma=2.0, inset=0.35),
    SamplingConfig(channel=1, clip_limit=3.0, blur_sigma=1.5, inset=0.30),
    SamplingConfig(channel=2, clip_limit=3.0, blur_sigma=1.5, inset=0.30),
    SamplingConfig(channel=0, clip_limit=3.0, blur_sigma=1.5, jitter=0.5, jitter_seed=1),
    SamplingConfig(channel=0, clip_limit=3.0, blur_sigma=1.5, jitter=0.5, jitter_seed=2),
    SamplingConfig(channel=0, clip_limit=3.0, blur_sigma=1.5, jitter=0.5, jitter_seed=3),
    SamplingConfig(channel=0, clip_limit=2.5, blur_sigma=1.8, jitter=0.5, jitter_seed=4),
    SamplingConfig(
        channel=1, clip_limit=4.0, blur_sigma=1.2, inset=0.35, jitter=0.5, jitter_seed=5
    ),
)


@dataclass
class Consensus:
    """Result of merging several measurement conditions."""

    posterior: np.ndarray
    disagreement: np.ndarray
    votes_dark: np.ndarray
    runs: int
    wrong_per_run: list[int]

    @property
    def contested(self) -> np.ndarray:
        """Cells the runs do not agree on.

        Disagreement is counted by sign, not by the spread of the log-odds: those reach into
        the tens, so almost every cell would count as contested. The runs only truly disagree
        when they cannot settle on dark or light.
        """
        return (self.votes_dark > 0) & (self.votes_dark < self.runs)


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-12, 1 - 1e-12)
    return np.log(p / (1 - p))


def _pool(
    stack: np.ndarray, weights: np.ndarray | None = None
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Merge log-odds and shrink the result by how much the runs disagree.

    Averaging happens in log-odds, not in probabilities. The difference is not cosmetic: the
    mean of 0.99 and 0.01 is 0.5, which would present a cell that two runs consider entirely
    unambiguous -- in opposite directions -- as merely undecided. In log-odds the cancellation
    happens too, but the spread survives and makes the argument visible.

    The shrinkage then walks the averaged verdict back wherever the runs disagree. Without it
    the consensus would be more confident than any of its parts, which is the classic mistake
    when averaging correlated measurements.
    """
    if weights is None:
        mean = stack.mean(axis=0)
        spread = stack.std(axis=0)
    else:
        mean = np.tensordot(weights, stack, axes=(0, 0))
        spread = np.sqrt(np.tensordot(weights, (stack - mean) ** 2, axes=(0, 0)))
    damped = mean / np.sqrt(1.0 + (spread / 2.0) ** 2)
    posterior = 1.0 / (1.0 + np.exp(-np.clip(damped, -60.0, 60.0)))
    return posterior, spread, (stack > 0).sum(axis=0)


# --------------------------------------------------------------------------------------
# Several photographs of one code.
#
# This is the one ensemble that reaches the error source the two below cannot. Both of those
# vary the measurement inside a single image, and the dominant error -- a homography standing
# in for a curved surface -- is a property of that image, so every member inherits it. Separate
# photographs do not share it: different angle, different light, different grit, so their
# mistakes fall on different cells and disagreement finally means something.
#
# MEASURED RESULT, and the first positive one in this file. Three photographs per trial, each
# with its own angle, curvature, light and resolution, fourteen trials per level, single images
# scored at the same budget as the fusion (scripts/multi_image.py):
#
#                    one photograph          fused, averaging probabilities
#   contrast 0.10    34/42 = 81 %            14/14 = 100 %
#   contrast 0.09    26/42 = 62 %            13/14 =  93 %
#   contrast 0.08    14/42 = 33 %             9/14 =  64 %
#   stain    0.40    27/42 = 64 %            14/14 = 100 %
#   stain    0.50    22/42 = 52 %            14/14 = 100 %
#   stain    0.60    15/42 = 36 %            12/14 =  86 %
#
# That is the win the two ensembles below never delivered, and for the reason stated above: the
# grid error is finally uncorrelated between members.
#
# The two axes are not interchangeable, and the difference is the more useful half of the
# result. Low contrast spoils every cell of every photograph alike, so three photographs carry
# three copies of one handicap -- searched across three contrast levels and twelve groups, not
# one case turned up where fusing three rescued what three could not do individually. A stain
# lands somewhere else each time, so what one photograph loses the others still hold. Advice to
# a user follows directly: re-photograph from a different angle and in different light, and do
# not bother with a burst from the same position.
#
# The rule: at the mild levels all of them tie. They separate exactly where the fusion has to
# work hardest, at stain 0.60 -- probabilities 12/14, pooled 10/14, log-odds 9/14. Those
# intervals overlap, so that alone would not settle it; what settles it is that the same order
# appeared on four photographs of one real engraved code, where averaging probabilities was the
# only rule to solve within the shipped defaults (22 probe cells, budget 4000, 2018 attempts)
# and the others needed the budget raised fivefold. The reason is measurable on that code: its
# posterior is overconfident -- cells it calls certain beyond 0.999 are wrong 1.7 % of the time
# -- and averaging log-odds compounds exactly that, leaving 4 cells inside the uncertainty band
# where averaging probabilities leaves 20. A probe can only visit doubt it has been shown. So
# the conservative rule is the default and the others stay available.


@dataclass(frozen=True)
class ImageConsensus:
    """What several photographs of one code agreed and disagreed on."""

    posterior: np.ndarray
    members: int
    agreement: tuple[float, ...]
    mirrored: tuple[int, ...]
    rejected: tuple[int, ...]
    disagreeing: int

    @property
    def fused(self) -> bool:
        return self.members > 1


FUSION_RULES = ("probability", "log-odds", "pooled", "median")
DEFAULT_FUSION = "probability"


def _combine(stack: np.ndarray, rule: str) -> np.ndarray:
    """Reduce several posteriors of the same cell to one."""
    if rule == "probability":
        return stack.mean(axis=0)
    if rule == "median":
        return np.median(stack, axis=0)
    if rule == "pooled":
        return _pool(np.stack([_logit(p) for p in stack]))[0]
    if rule == "log-odds":
        mean = np.stack([_logit(p) for p in stack]).mean(axis=0)
        return 1.0 / (1.0 + np.exp(-np.clip(mean, -60.0, 60.0)))
    raise ValueError(f"unknown fusion rule: {rule!r}")


def fuse_images(
    posteriors: list[np.ndarray],
    known_dark: np.ndarray,
    known_light: np.ndarray,
    rule: str = DEFAULT_FUSION,
    min_agreement: float = 0.75,
) -> ImageConsensus:
    """Fuse the posteriors of several photographs, after checking they show the same code.

    The first posterior is the reference and should be the best-fitting one; the rest are
    accepted only if they agree with it well enough to be the same code. Chance agreement is
    50 %, a second photograph of the same code sits well above 90 %, so the default threshold
    separates the two cleanly and refuses to average in a picture of something else.

    A mirrored photograph is checked for explicitly, because nothing upstream can catch it. The
    structure mask is symmetric about the main diagonal apart from the single always-dark
    module: a code photographed in a mirror therefore fits its grid, scores one wrong known
    cell out of a few hundred, and arrives here transposed. Averaged in unchecked it would
    corrupt every cell it touched.
    """
    free = ~(known_dark | known_light)
    reference = posteriors[0] >= 0.5

    accepted = [posteriors[0]]
    agreement: list[float] = [1.0]
    mirrored: list[int] = []
    rejected: list[int] = []

    for index, posterior in enumerate(posteriors[1:], start=1):
        if posterior.shape != reference.shape:
            rejected.append(index)
            continue
        straight = float(((posterior >= 0.5)[free] == reference[free]).mean())
        flipped = float(((posterior.T >= 0.5)[free] == reference[free]).mean())
        if max(straight, flipped) < min_agreement:
            rejected.append(index)
            continue
        if flipped > straight:
            posterior = posterior.T
            mirrored.append(index)
        accepted.append(posterior)
        agreement.append(max(straight, flipped))

    stack = np.stack(accepted)
    votes = (stack >= 0.5).sum(axis=0)
    disagreeing = int(((votes > 0) & (votes < len(accepted)) & free).sum())

    return ImageConsensus(
        posterior=_combine(stack, rule) if len(accepted) > 1 else accepted[0],
        members=len(accepted),
        agreement=tuple(agreement),
        mirrored=tuple(mirrored),
        rejected=tuple(rejected),
        disagreeing=disagreeing,
    )


def consensus_posterior(
    bgr: np.ndarray,
    corners: np.ndarray,
    modules: int,
    scale: int,
    known_dark: np.ndarray,
    known_light: np.ndarray,
    configs: tuple[SamplingConfig, ...] = DEFAULT_CONFIGS,
) -> Consensus:
    """Measure every cell under all conditions and merge the verdicts."""
    log_odds: list[np.ndarray] = []
    wrong_per_run: list[int] = []
    known = known_dark | known_light

    for config in configs:
        gray, _ = prepare(
            bgr,
            channel=config.channel,
            clip_limit=config.clip_limit,
            blur_sigma=config.blur_sigma,
        )
        points = np.array(corners, dtype=np.float64)
        if config.jitter:
            rng = np.random.default_rng(config.jitter_seed)
            points = points + rng.normal(0.0, config.jitter, points.shape)

        warped = warp(gray, points, modules, scale)
        means, spread = sample_cells(warped, modules, scale, inset_frac=config.inset)
        fit = estimate_levels(means, spread, known_dark, known_light)
        posterior = posterior_dark(means, fit)

        log_odds.append(_logit(posterior))
        hard = posterior >= 0.5
        wrong_per_run.append(int((hard[known] != known_dark[known]).sum()))

    posterior, spread, votes = _pool(np.stack(log_odds))
    return Consensus(
        posterior=posterior,
        disagreement=spread,
        votes_dark=votes,
        runs=len(configs),
        wrong_per_run=wrong_per_run,
    )


# --------------------------------------------------------------------------------------
# The harder route: average over geometries rather than over preprocessings.
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class GeometryConfig:
    """An independent attempt at the grid.

    The starting point is disturbed substantially -- far more than in the sampling ensemble,
    where 0.5 px amounted to a sixth of a module. Coordinate descent then runs freely and ends
    in its own optimum. Only that independence makes the spread meaningful.
    """

    channel: int = 0
    clip_limit: float = 3.0
    blur_sigma: float = 1.5
    corner_jitter: float = 2.0
    scale: int = 12
    seed: int = 0


DEFAULT_GEOMETRIES: tuple[GeometryConfig, ...] = (
    GeometryConfig(corner_jitter=0.0, seed=0),
    GeometryConfig(corner_jitter=2.0, seed=1),
    GeometryConfig(corner_jitter=2.0, seed=2),
    GeometryConfig(corner_jitter=3.5, seed=3),
    GeometryConfig(corner_jitter=3.5, seed=4),
    GeometryConfig(channel=1, corner_jitter=2.0, seed=5),
    GeometryConfig(channel=2, corner_jitter=2.0, seed=6),
    GeometryConfig(clip_limit=2.0, blur_sigma=1.2, corner_jitter=2.0, seed=7),
    GeometryConfig(clip_limit=4.0, blur_sigma=2.0, corner_jitter=2.0, seed=8),
)


@dataclass
class GeometryConsensus:
    """Merge of several independently fitted grids."""

    posterior: np.ndarray
    disagreement: np.ndarray
    votes_dark: np.ndarray
    kept: int
    discarded: int
    wrong_per_member: list[int]
    weights: list[float]

    @property
    def contested(self) -> np.ndarray:
        return (self.votes_dark > 0) & (self.votes_dark < self.kept)


def geometry_consensus(
    bgr: np.ndarray,
    base_corners: np.ndarray,
    modules: int,
    known_dark: np.ndarray,
    known_light: np.ndarray,
    configs: tuple[GeometryConfig, ...] = DEFAULT_GEOMETRIES,
    max_extra_wrong: int = 6,
) -> GeometryConsensus | None:
    """Fit several grids independently and merge their cell verdicts by weight.

    Two safeguards, without which averaging hurts rather than helps.

    Rejection. An attempt can converge to an optimum that is off by a whole module. Such a grid
    is not less accurate, it is wrong -- it points at different cells, and averaging it in
    corrupts all the others. It is detectable through the known cells and the timing pattern,
    and both are checked before a member counts.

    Weighting. An attempt with two wrong known cells knows more than one with twelve. Equal
    weights would be the silent assumption that all attempts are equally good; they demonstrably
    are not, and we can measure the difference.
    """
    fits: list[GridFit] = []

    for config in configs:
        gray, _ = prepare(
            bgr,
            channel=config.channel,
            clip_limit=config.clip_limit,
            blur_sigma=config.blur_sigma,
        )
        start = np.array(base_corners, dtype=np.float64)
        if config.corner_jitter:
            rng = np.random.default_rng(config.seed)
            start = start + rng.normal(0.0, config.corner_jitter, start.shape)
        fits.append(refine_corners(gray, start, modules, config.scale, known_dark, known_light))

    best = min(f.wrong_known for f in fits)
    usable = [
        f
        for f in fits
        if f.wrong_known <= best + max_extra_wrong and timing_score(f.posterior >= 0.5) == 1.0
    ]
    if not usable:
        return None

    # Weight decays exponentially with the number of wrong known cells. The scale of two cells
    # is chosen so that a clearly worse grid may still speak, but quietly.
    weights = np.array([np.exp(-(f.wrong_known - best) / 2.0) for f in usable])
    weights = weights / weights.sum()

    posterior, spread, votes = _pool(np.stack([_logit(f.posterior) for f in usable]), weights)
    return GeometryConsensus(
        posterior=posterior,
        disagreement=spread,
        votes_dark=votes,
        kept=len(usable),
        discarded=len(fits) - len(usable),
        wrong_per_member=[int(f.wrong_known) for f in usable],
        weights=[float(w) for w in weights],
    )
