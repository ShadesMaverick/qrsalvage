"""From the rectified image to a probability per module.

Nothing here decides anything for good. Every cell receives a probability of being dark, and
that is what later lets the solver probe exactly where the doubt is instead of guessing blindly.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import cv2
import numpy as np

# How strongly a cell's own internal disagreement widens its uncertainty, relative to the
# scatter estimated from the known cells. Chosen by measurement, not by taste; see
# scripts/difficulty.py.
SPREAD_WEIGHT = 1.5

# Damage is spatially contiguous -- a stain, a scratch, a worn patch -- while the two terms
# above treat every cell as its own island. Two neighbourhood terms can carry that structure:
# a known cell that reads wrong is ground truth that damage crosses that exact spot, so its
# blurred indicator marks the surroundings (BEACON_WEIGHT); and a stain's interior cells are
# covered whole -- uniform inside, confidently wrong, invisible to their own spread -- so only
# the blurred spread of the ring around them reaches them (NEIGHBOR_WEIGHT).
#
# MEASURED RESULT, and a negative one: both default to zero. On the stain axis (16 images per
# level, scripts/ab_sigma.py) the success rate did not move by a single image in any arm --
# 14/16 and 11/16 at stain 0.35 and 0.45, identical for off/off, beacon, neighbour and both --
# and the middle-of-the-code calibration error barely twitched (ECE 0.0238 -> 0.0233 at stain
# 0.5, scripts/calibration.py). The plausible reason: the blur radius reaches one or two cells,
# but a synthetic stain is many cells wide, so the interior stays dark to both terms. The terms
# and the measurement stay, so the next idea starts from numbers instead of from scratch.
BEACON_WEIGHT = 0.0
NEIGHBOR_WEIGHT = 0.0
SPATIAL_BLUR = 1.2  # in cells; roughly the scale at which stains outgrow single modules

# The robust level estimate, and the failure that forced it. On a photograph of a torn
# printout, the fitted grid overhung the torn paper edge, so a column of known-dark cells
# measured bright paper. Those outliers dragged the two quadratic fields until they crossed;
# the contrast clamp then bottomed out at 1e-6, the contrast-normalised residuals exploded,
# and base_sigma came out at 2.9 million -- which flattened the posterior of 555 of 841 cells
# to a coin toss on an image whose actual contrast was fine (dark median 102, light median
# 197). Three defences, together: known cells whose residual is an extreme outlier are
# excluded from the field fit, the contrast floor is a fraction of the median contrast
# instead of an absolute epsilon, and the scatter is estimated by MAD, which a handful of
# outliers cannot inflate.
#
# MEASURED RESULT (scripts/ab_robust.py, 16 images per level and arm), and it is not a
# success-rate story. Control axis contrast: 16/16, 16/16, 15/16 -- identical in both arms,
# which is what a control has to show. Stain: 14/14, 11 -> 12, 8 -> 9; one image in sixteen
# at two levels, well inside the noise. Tear: 14/14, 14/14, 6/6 -- identical, and that axis
# breaks through lost finder detection rather than through this term anyway. (That run
# predates both the split of the torn edge into an optical and a geometric half and the
# reshaping of its shadow from a bar into a penumbra, so it does not describe today's tear
# axis. It is kept rather than rerun because the finding it carries -- that the axis was
# breaking through finder detection -- is exactly what motivated both changes.)
#
# What the term does buy is the honesty of the numbers the escalation reads. On the
# photograph above it cut the uncertain cells from 555 to 37 while the image's actual
# contrast was never in doubt; a posterior flattened to 0.5 also destroys the flip-cost
# ordering, so the probe spends its whole budget ranking cells at random. The constructed
# case in test_lying_known_cells_cannot_flatten_the_posterior goes from 775 of 841 cells
# uncertain to none. And one concrete recovery: the fusion suite's hard case (stain 0.50,
# group 7) had all three photographs failing alone before and now solves from a single one,
# which is why that test needed a harder case (0.55, group 2).
#
# THE COST, measured: 2.4x the level fits on a clean image, 2.9x on a stained one, for 40 to
# 50 percent more wall clock. The rejection loop runs inside the grid search, where most
# candidate placements are legitimately wrong and therefore look full of outliers. The
# obvious repair -- reject robustly only once the grid is settled -- needs the search path
# and the final sampling separated first; today both run through geometry._score.
ROBUST_LEVELS = True
CONTRAST_FLOOR = 0.15  # of the median contrast
OUTLIER_SIGMAS = 3.5
MIN_KNOWN_PER_CLASS = 12  # never thin a field's support below this; 6 parameters need slack

# How many times the level fit may drop outliers and fit again. Was a bare 4 in the loop, named
# here so it could be measured rather than argued about, and then measured: it stays 4. Below
# that costs accuracy on the damage it exists for and does not reliably save time; above it
# buys one wrong cell for fifteen percent more work. See estimate_levels for the numbers and
# scripts/ab_rounds.py for the instrument.
ROBUST_ROUNDS = 4


# The window of the featureless-patch test, in cells, and the data cells a window must contain
# before it may testify. After masking, data modules are close to balanced and only weakly
# correlated, so a window of w*w data cells that is entirely one colour has probability around
# 2^(1-w*w): at w=5 that is six in a hundred million, against a few hundred window positions
# per code. Such a window is therefore not data. It is something lying on top of the code --
# overpaint, a worn-off print, blank paper past a cut -- and pixels measured off it are
# perfectly sharp and perfectly meaningless.
#
# This is the failure the two spatial terms above (BEACON_WEIGHT, NEIGHBOR_WEIGHT) were built
# for and measurably could not reach: their blur spans one or two cells, a covered patch spans
# many, so its interior stays uniform, confidently wrong, and invisible to its own spread. The
# window test is scale-free where the blur is not -- a patch is uniform at every size.
#
# The minimum-data floor keeps the structure cells from testifying against themselves: the
# finders and their quiet rings are large single-colour patches by design, and every cell the
# standard fixes is excluded from both the count and the verdict.
#
# The tolerance exists because real blank areas are not clean: the photograph that motivated
# this test carries specks of grit on its worn-off patch, each read as one confident dark
# module in a sea of light ones. A speck breaks its window's uniformity, its codeword then
# never ranks for erasure, and it enters Reed-Solomon as an error -- which costs double. One
# deviating cell still leaves the accident probability near 25 * 2^-24 per window; the
# argument survives the allowance.
BLANK_WINDOW = 5
BLANK_MIN_DATA = 12
BLANK_TOLERANCE = 1

# Past this featureless depth a cell counts as buried -- there is no print under it. The value
# sits below the core depth of the thinnest damage worth catching (a three-row strip cores
# near 0.4 under the area-normalised depth) and above the brush a strip leaves on its live
# neighbours (about 0.2).
BURIED_DEPTH = 0.35

# A cell that dodged the depth but is surrounded by buried ones on at least this many of its
# eight sides is grit lying *on* the damage, not a surviving module -- a survivor would have
# living neighbours. Without this closing, every speck on a worn patch reaches Reed-Solomon
# as a confident error, and errors cost double what erasures do; measured on the motivating
# photograph, the specks alone pushed the repair past its budget at every rung of the ladder.
BURIED_NEIGHBOURS = 5


def featureless_depth(
    posterior: np.ndarray,
    known: np.ndarray,
    window: int = BLANK_WINDOW,
    min_data: int = BLANK_MIN_DATA,
    tolerance: int = BLANK_TOLERANCE,
) -> np.ndarray:
    """Per cell, how deep it stands in featureless ground: 0 structured, towards 1 buried.

    Only data cells testify (the finders are uniform by design), but the verdict covers the
    known cells inside a marked window too: a finder ring standing in a featureless plain is
    exactly as gone as the data around it, and it matters twice -- once as a lying witness in
    the grid objective, once as a cell the decoder must not trust.

    A *depth* rather than a mask, and that is the load-bearing choice. The depth is the
    fraction of a cell's covering windows that are uniform, so a cell in the middle of a blank
    plain scores 1 and a cell its rim brushes scores a sliver. Damping confidence by depth
    hands the erasure ladder an *ordering*: it spends its first erasures in the middle of the
    damage, the rim costs only what is left over, and a patch larger than the erasure budget
    degrades into "erase the worst of it" instead of scattering the budget at random across
    cells that all claimed exactly half. Both binary variants were tried and measured on the
    photograph with the worn-off bottom edge: marking window centres left the rim confidently
    wrong and Reed-Solomon produced a *valid wrong* text; marking every touched cell blanked
    twice the damage area, overran the per-block budget, and the ladder -- choosing at random
    among equals -- never picked the right set.
    """
    hard = posterior >= 0.5
    size = (window, window)
    data = (~known).astype(np.float32)
    dark = (hard & ~known).astype(np.float32)
    total = cv2.boxFilter(data, -1, size, normalize=False, borderType=cv2.BORDER_ISOLATED)
    count = cv2.boxFilter(dark, -1, size, normalize=False, borderType=cv2.BORDER_ISOLATED)
    uniform = (total >= min_data) & ((count <= tolerance) | (count >= total - tolerance))
    covering = cv2.boxFilter(
        uniform.astype(np.float32), -1, size, normalize=False, borderType=cv2.BORDER_ISOLATED
    )
    # Normalised by the window area, and deliberately never reaching 1 on thin damage: a
    # strip a few rows tall yields only a few rows of uniform centres, so its core sits near
    # 0.5 while the live row its windows brush stays near 0.2. That *gap* is the product.
    # An edge-normalised variant that saturated to 1 was tried and measured worse than the
    # problem it addressed: core and rim tied at 1.0, the erasure ladder was back to choosing
    # among equals, and a photograph whose hand-derived grid was pixel-perfect still failed.
    return covering / float(window * window)


def buried_cells(depth: np.ndarray) -> np.ndarray:
    """The cells with no print under them: deep ones, plus grit encircled by deep ones."""
    core = depth >= BURIED_DEPTH
    around = cv2.boxFilter(
        core.astype(np.float32), -1, (3, 3), normalize=False, borderType=cv2.BORDER_ISOLATED
    )
    # `around` counts the cell itself, which for the cells in question is not buried.
    return core | (around >= BURIED_NEIGHBOURS)


@dataclass(frozen=True)
class LevelFit:
    """The estimated brightness model of a code area.

    `sigma` is a field, not a number. It has to be: the known cells all sit around the edges of
    the code, so a scatter estimated from them alone says little about the data cells in the
    middle. When the edges happen to be clean the model turns confident about the centre with
    no grounds for it -- observed on a synthetic case that seated the grid perfectly, reported
    zero wrong known cells and zero uncertain cells, and still would not decode.
    """

    dark: np.ndarray
    light: np.ndarray
    sigma: np.ndarray

    @property
    def threshold(self) -> np.ndarray:
        return (self.dark + self.light) / 2.0

    @property
    def contrast(self) -> np.ndarray:
        return np.maximum(self.light - self.dark, 1e-6)


def sample_cells(
    warped: np.ndarray, modules: int, scale: int, inset_frac: float = 0.3
) -> tuple[np.ndarray, np.ndarray]:
    """Mean and spread per module cell.

    Only the core of each cell is measured. The borders carry the bleed from neighbouring
    modules that the blur needed for raster fusion inevitably introduced.
    """
    inset = max(1, int(scale * inset_frac))
    # The grid is regular, so the loop can be replaced by an exactly equivalent reshape. This
    # is not polish: grid fitting calls this function a few hundred times per image.
    grid = warped.reshape(modules, scale, modules, scale).transpose(0, 2, 1, 3)
    core = grid[:, :, inset : scale - inset, inset : scale - inset].astype(np.float64)
    return core.mean(axis=(2, 3)), core.std(axis=(2, 3))


@lru_cache(maxsize=16)
def _quadratic_terms(n: int) -> np.ndarray:
    """The design matrix of the quadratic fit -- a pure function of the grid size.

    Cached because the grid refinement evaluates hundreds of candidate placements per solve
    and every one of them fits two fields; rebuilding the identical matrix each time was pure
    overhead. Frozen for the same reason every cached array here is.
    """
    rr, cc = np.mgrid[0:n, 0:n].astype(np.float64)
    terms = np.stack([np.ones_like(rr), rr, cc, rr * rr, cc * cc, rr * cc], axis=-1)
    terms.setflags(write=False)
    return terms


@lru_cache(maxsize=128)
def _fit_operator(n: int, mask_bytes: bytes) -> np.ndarray:
    """The pseudoinverse of the design matrix restricted to the marked cells.

    The least-squares fit runs twice per grid evaluation and hundreds of evaluations per
    solve, always against the same design matrix and the same mask -- only the measured means
    change. So the solve collapses to one cached pseudoinverse and a matrix product, which is
    the identical minimum-norm solution lstsq would compute, without the SVD every time.

    The mask is not as constant as that reads, though, and the size is measured rather than
    guessed. The robust loop in estimate_levels drops outlying known cells and fits again, so
    a mask is a function of the measurements too, and one solve of the hardest fixture asks
    for 45094 fits across 14855 distinct masks. At 32 entries the cache was full and evicting:
    53.7 % hits. At 128 it reaches 65.8 %, and after that it plateaus -- 512, 2048 and an
    unbounded cache all land on 67.0 %, because the remaining masks genuinely occur once. So
    128 is where the curve flattens, and holding thousands of pseudoinverses to buy the last
    1.2 points would be paying memory for nothing.
    """
    mask = np.frombuffer(mask_bytes, dtype=bool).reshape(n, n)
    return np.linalg.pinv(_quadratic_terms(n)[mask])


def _fit_quadratic(means: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Fit a quadratic field to the marked cells and evaluate it everywhere."""
    n = means.shape[0]
    coefficients = _fit_operator(n, mask.tobytes()) @ means[mask]
    return _quadratic_terms(n) @ coefficients


def estimate_levels(
    means: np.ndarray,
    spread: np.ndarray,
    known_dark: np.ndarray,
    known_light: np.ndarray,
) -> LevelFit:
    """Estimate the dark and light levels as separate fields, plus a per-cell uncertainty.

    The levels are separate fields because across a curved surface the two drift by different
    amounts; a single threshold cannot express that.

    The uncertainty comes from two independent sources, which is the point of this function.
    The first is the scatter of the known cells around their own fitted level -- that measures
    how well the model describes the code, but only where the known cells are, which is the
    border. The second is each cell's own internal disagreement: a module whose interior is
    uniform is trustworthy, one that is half dark and half light is not, and that holds in the
    middle of the code where no known cell reaches.

    Only the *excess* spread counts. A dot-raster engraving gives every cell a baseline of
    internal variation, and charging every module for it would flatten the signal instead of
    sharpening it. The baseline is taken from the known cells, where it can be measured.

    The estimate must also survive known cells that lie. A least-squares fit hands a few
    grossly wrong known cells -- a grid column overhanging a torn paper edge, a stain across
    a finder -- enough leverage to bend the fields until they cross, and a scatter taken as a
    standard deviation is inflated by exactly the outliers it should have flagged. See the
    note at :data:`ROBUST_LEVELS` for the observed failure and the three defences.

    What the loop below actually does, measured, because the sentence that stood here before
    described something else. It cannot oscillate -- every round only removes cells, never puts
    one back -- so it does not thrash. It spirals: dropping outliers shrinks the residual
    scatter, a smaller scatter puts more cells outside the threshold, and those go next.
    Replayed on 400 real inputs with the cap lifted to twelve, 98.2 % of calls do come to a
    stop, but the median takes six or seven rounds and the support falls from 203 known cells
    to around 120 on the way. Under the shipped cap, 85 % of calls on a hard photograph use
    every round they are given. So this is a stop partway down a spiral, not a convergence.

    That is not the fault it looks like. On the stained axis, where known cells genuinely lie,
    the median wrong-cell count runs 16, 9, 7, 7, 6 for one through six rounds: the whole
    benefit arrives by round three and four is where it flattens. Cutting the cap does not even
    buy time on the images it exists for -- one round measured *slower* than two (370 s against
    346 s over thirty images), because a worse level fit hands the probe more uncertain cells
    to work through. Four is where the curve turns; the argument for it is
    scripts/ab_rounds.py.
    """
    use_dark, use_light = known_dark, known_light
    for _ in range(ROBUST_ROUNDS):
        dark = _fit_quadratic(means, use_dark)
        light = _fit_quadratic(means, use_light)
        if ROBUST_LEVELS:
            floor = CONTRAST_FLOOR * max(float(np.median(light - dark)), 1.0)
        else:
            floor = 1e-6
        contrast = np.maximum(light - dark, floor)
        residual_dark = (means - dark) / contrast
        residual_light = (means - light) / contrast
        residuals = np.concatenate([residual_dark[use_dark], residual_light[use_light]])
        if not ROBUST_LEVELS:
            base_sigma = max(float(np.std(residuals)) or 0.1, 0.02)
            break
        centred = np.abs(residuals - np.median(residuals))
        base_sigma = max(
            1.4826 * float(np.median(centred)) or float(np.std(residuals)) or 0.1, 0.02
        )
        drop_dark = use_dark & (np.abs(residual_dark) > OUTLIER_SIGMAS * base_sigma)
        drop_light = use_light & (np.abs(residual_light) > OUTLIER_SIGMAS * base_sigma)
        if not (drop_dark.any() or drop_light.any()):
            break
        if (
            int((use_dark & ~drop_dark).sum()) < MIN_KNOWN_PER_CLASS
            or int((use_light & ~drop_light).sum()) < MIN_KNOWN_PER_CLASS
        ):
            break
        use_dark = use_dark & ~drop_dark
        use_light = use_light & ~drop_light

    known = use_dark | use_light
    baseline = float(np.median(spread[known])) if known.any() else 0.0
    excess = np.maximum(spread - baseline, 0.0) / contrast
    variance = base_sigma**2 + (SPREAD_WEIGHT * excess) ** 2

    # The neighbourhood terms; both weights default to zero, see the measurement above them.
    if BEACON_WEIGHT > 0.0:
        threshold = (dark + light) / 2.0
        mismatch = (known_dark & (means > threshold)) | (known_light & (means < threshold))
        beacon = cv2.GaussianBlur(mismatch.astype(np.float64), (0, 0), SPATIAL_BLUR)
        variance = variance + (BEACON_WEIGHT * beacon) ** 2
    if NEIGHBOR_WEIGHT > 0.0:
        neighborhood = cv2.GaussianBlur(excess, (0, 0), SPATIAL_BLUR)
        variance = variance + (NEIGHBOR_WEIGHT * neighborhood) ** 2

    return LevelFit(dark=dark, light=light, sigma=np.sqrt(variance))


def posterior_dark(means: np.ndarray, fit: LevelFit) -> np.ndarray:
    """P(module is dark) from two Gaussians, each cell with its own spread.

    The spread is a field rather than a constant, so a cell that disagrees with itself ends up
    closer to undecided than a clean one at the same distance from the threshold. See
    :func:`estimate_levels` for where the two contributions come from.
    """
    contrast = fit.contrast
    x = means / contrast
    dark = fit.dark / contrast
    light = fit.light / contrast
    log_odds = ((x - light) ** 2 - (x - dark) ** 2) / (2.0 * fit.sigma**2)
    return 1.0 / (1.0 + np.exp(-np.clip(log_odds, -60.0, 60.0)))


def warp(gray: np.ndarray, corners: np.ndarray, modules: int, scale: int) -> np.ndarray:
    """Rectify the four corner points onto a square module grid."""
    destination = np.array(
        [
            [0, 0],
            [modules * scale, 0],
            [0, modules * scale],
            [modules * scale, modules * scale],
        ],
        dtype=np.float32,
    )
    homography = cv2.getPerspectiveTransform(np.asarray(corners, dtype=np.float32), destination)
    return cv2.warpPerspective(
        gray,
        homography,
        (modules * scale, modules * scale),
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=255,
    )
