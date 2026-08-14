"""Preprocessing: turn the photograph into an image where modules are areas, not dot clusters.

Two steps carry almost all of the benefit. Flat-fielding removes the glare gradient and the
shading of a curved surface before any threshold is applied. Blurring turns the dot raster of
a laser engraving into grey levels -- without it you threshold the individual raster dots
instead of the modules, and the result is salt-and-pepper noise that no decoder can use.
"""

from __future__ import annotations

import cv2
import numpy as np


def flat_field(channel: np.ndarray) -> np.ndarray:
    """Divide by a heavily blurred copy of the image."""
    background = cv2.GaussianBlur(channel, (0, 0), sigmaX=max(channel.shape) / 12.0)
    return np.clip(cv2.divide(channel, background, scale=192), 0, 255).astype(np.uint8)


def prepare(
    bgr: np.ndarray, channel: int = 0, clip_limit: float = 3.0, blur_sigma: float = 1.5
) -> tuple[np.ndarray, np.ndarray]:
    """Return (grayscale image for sampling, binary image for finder search).

    The blue channel is the default: on a laser engraving in white plastic it carries
    noticeably more contrast than luminance does.
    """
    chan = bgr[:, :, channel] if bgr.ndim == 3 else bgr
    flat = flat_field(chan)
    tonal = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(8, 8)).apply(flat)
    gray = cv2.GaussianBlur(tonal, (0, 0), blur_sigma)
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 41, 2
    )
    return gray, binary
