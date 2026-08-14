"""From the rectified image to a probability per module.

Nothing here decides anything for good. Every cell receives a probability of being dark, and
that is what later lets the solver probe exactly where the doubt is instead of guessing blindly.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

# How strongly a cell's own internal disagreement widens its uncertainty, relative to the
# scatter estimated from the known cells. Chosen by measurement, not by taste; see
# scripts/difficulty.py.
SPREAD_WEIGHT = 1.5


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


def sample_cells(warped: np.ndarray, modules: int, scale: int, inset_frac: float = 0.3):
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


def _fit_quadratic(means: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Fit a quadratic field to the marked cells and evaluate it everywhere."""
    n = means.shape[0]
    rr, cc = np.mgrid[0:n, 0:n].astype(np.float64)
    terms = np.stack([np.ones_like(rr), rr, cc, rr * rr, cc * cc, rr * cc], axis=-1)
    coefficients, *_ = np.linalg.lstsq(terms[mask], means[mask], rcond=None)
    return terms @ coefficients


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
    """
    dark = _fit_quadratic(means, known_dark)
    light = _fit_quadratic(means, known_light)
    contrast = np.maximum(light - dark, 1e-6)
    known = known_dark | known_light

    residuals = np.concatenate(
        [
            ((means - dark) / contrast)[known_dark],
            ((means - light) / contrast)[known_light],
        ]
    )
    base_sigma = max(float(np.std(residuals)) or 0.1, 0.02)

    baseline = float(np.median(spread[known])) if known.any() else 0.0
    excess = np.maximum(spread - baseline, 0.0) / contrast
    sigma = np.sqrt(base_sigma**2 + (SPREAD_WEIGHT * excess) ** 2)

    return LevelFit(dark=dark, light=light, sigma=sigma)


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
