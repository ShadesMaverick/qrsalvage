"""From the rectified image to a probability per module.

Nothing here decides anything for good. Every cell receives a probability of being dark, and
that is what later lets the solver probe exactly where the doubt is instead of guessing blindly.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class LevelFit:
    """The estimated brightness model of a code area."""

    dark: np.ndarray
    light: np.ndarray
    sigma: float

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


def estimate_levels(means: np.ndarray, known_dark: np.ndarray, known_light: np.ndarray) -> LevelFit:
    """Estimate the dark and light levels as separate fields from the known cells.

    Separate, because across a curved surface the two levels drift by different amounts. A
    single threshold cannot express that; two fields can.
    """
    dark = _fit_quadratic(means, known_dark)
    light = _fit_quadratic(means, known_light)
    contrast = np.maximum(light - dark, 1e-6)
    residuals = np.concatenate(
        [
            ((means - dark) / contrast)[known_dark],
            ((means - light) / contrast)[known_light],
        ]
    )
    sigma = float(np.std(residuals)) or 0.1
    return LevelFit(dark=dark, light=light, sigma=max(sigma, 0.02))


def posterior_dark(means: np.ndarray, fit: LevelFit) -> np.ndarray:
    """P(module is dark) from two Gaussians sharing one spread.

    The spread comes from the known cells, so the model calibrates itself on measurements whose
    true answer is settled rather than on a constant somebody picked.
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
