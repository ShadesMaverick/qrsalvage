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


@lru_cache(maxsize=32)
def _fit_operator(n: int, mask_bytes: bytes) -> np.ndarray:
    """The pseudoinverse of the design matrix restricted to the marked cells.

    The least-squares fit runs twice per grid evaluation and hundreds of evaluations per
    solve, always against the same design matrix and the same mask -- only the measured means
    change. So the solve collapses to one cached pseudoinverse and a matrix product, which is
    the identical minimum-norm solution lstsq would compute, without the SVD every time.
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
    note at :data:`ROBUST_LEVELS` for the observed failure and the three defences. The loop
    below converges in two or three rounds on damaged images and runs exactly once on clean
    ones, where no residual crosses the threshold.
    """
    use_dark, use_light = known_dark, known_light
    for _ in range(4):
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
