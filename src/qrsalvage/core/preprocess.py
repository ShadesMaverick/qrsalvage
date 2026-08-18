"""Preprocessing: turn the photograph into an image where modules are areas, not dot clusters.

Two steps carry almost all of the benefit. Flat-fielding removes the glare gradient and the
shading of a curved surface before any threshold is applied. Blurring turns the dot raster of
a laser engraving into grey levels -- without it you threshold the individual raster dots
instead of the modules, and the result is salt-and-pepper noise that no decoder can use.
"""

from __future__ import annotations

import cv2
import numpy as np

# Colour is never ink. QR modules are printed black on white (or the reverse) -- a strongly
# saturated pixel is an overlay: a marker stroke, a coloured guide, a stamp across the label.
# Read through the blue channel a red stroke is indistinguishable from a module, so past the
# threshold it is neutralised to mid-grey: bright enough that the binarisation ignores it,
# ambiguous enough that the sampling reads the cells under it as undecided rather than as
# either colour. Mid-grey rather than white by measurement -- on a photograph with coloured
# guide lines drawn across the code, grey read 1.9 percent of known cells wrong where white
# read 3.5 and reading the colour as ink read 5.0.
#
# The cap guards the other kind of colour: a code on tinted plastic or under a warm lamp is
# saturated *everywhere*, and neutralising it would erase the photograph. Measured across the
# real corpus, codes with overlays sit at a few percent saturated and plain photographs at
# zero to two, while images that are mostly colour are mostly not codes; past a quarter the
# saturation is the surface, not an overlay, and nothing is touched.
#
# MEASURED RESULT, and it ships OFF -- the cap at zero disables the whole step, the same way
# the two spatial uncertainty terms in sampling.py ship at zero with the instrument that
# measured them. On the marker axis (scripts/ab_marker.py, 16 images per level and arm,
# strokes drawn across the code) neutralising converts nothing: 16/16, 7/16, 2/16, 0/16,
# 0/16 against 16/16, 7/16, 1/16, 0/16, 0/16, five wrong texts in either arm. A stroke
# through the middle clips one or two bits from *many* codewords, which no erasure budget
# covers -- and handing Reed-Solomon that many half-erasures buys it the freedom to
# manufacture presentable garbage as readily as the confident misreads did. What the step
# demonstrably improves is the geometry under overlay (the guide-line photograph above),
# and that photograph reads today through the stage-one escape hatch of masking the overlay
# by hand. To try the step on a photograph, raise the cap to 0.25; the constants stay
# because the instrument and the failure analysis are worth more than the flag.
NEUTRAL_SATURATION = 90
NEUTRAL_SATURATION_CAP = 0.0


def flat_field(channel: np.ndarray) -> np.ndarray:
    """Divide by a heavily blurred copy of the image."""
    background = cv2.GaussianBlur(channel, (0, 0), sigmaX=max(channel.shape) / 12.0)
    return np.clip(cv2.divide(channel, background, scale=192), 0, 255).astype(np.uint8)


def prepare(
    bgr: np.ndarray,
    channel: int = 0,
    clip_limit: float = 3.0,
    blur_sigma: float = 1.5,
    invert: bool = False,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (grayscale image for sampling, binary image for finder search).

    The blue channel is the default: on a laser engraving in white plastic it carries
    noticeably more contrast than luminance does.

    `invert` handles codes that are light on a dark ground -- etched into dark plastic, lasered
    onto metal, printed white on black. Everything downstream assumes dark modules, so the
    inversion happens here, once, and the rest of the pipeline never learns about it.
    """
    chan = bgr[:, :, channel] if bgr.ndim == 3 else bgr
    if bgr.ndim == 3:
        spread = bgr.max(axis=2).astype(np.int16) - bgr.min(axis=2).astype(np.int16)
        coloured = (spread > NEUTRAL_SATURATION).astype(np.uint8)
        fraction = float(coloured.mean())
        if 0.0 < fraction <= NEUTRAL_SATURATION_CAP:
            # Grown by a couple of pixels: a stroke's anti-aliased fringe is only half
            # saturated, and through the blue channel that fringe survives as a thin dark
            # contour tracing exactly where the stroke was.
            coloured = cv2.dilate(coloured, np.ones((5, 5), dtype=np.uint8))
            chan = chan.copy()
            chan[coloured > 0] = 128
    if invert:
        chan = 255 - chan
    flat = flat_field(chan)
    tonal = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(8, 8)).apply(flat)
    gray = cv2.GaussianBlur(tonal, (0, 0), blur_sigma)
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 41, 2
    )
    return gray, binary
