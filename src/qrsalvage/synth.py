"""Artificially degraded QR codes whose answer is known.

Working backwards solves the fundamental problem of development here: a corpus built from a
single photograph measures nothing. If you know the plain text you can generate arbitrarily
many cases whose solution is settled -- and then quantify every change to the method instead
of believing in it.

The kinds of damage reproduced are the ones from real photographs: curvature, the dot raster
of a laser engraving, a glare gradient, dirt, and the torn paper edge that runs along the
code's flank.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .core.decoding import reencode


@dataclass(frozen=True)
class Damage:
    """How badly a synthetic case is spoiled. Everything in image units."""

    module_px: float = 9.0
    curvature: float = 0.25
    raster_period: float = 3.0
    raster_depth: float = 0.55
    contrast: float = 0.28
    glare: float = 0.35
    stain: float = 0.0
    blur: float = 1.2
    noise: float = 4.0
    rotation_deg: float = 0.0
    # Light modules on a dark ground: etched into dark plastic, lasered onto metal, printed
    # white on black. Common enough on hardware labels, and invisible to a pipeline that
    # assumes dark modules.
    inverted: bool = False
    # The two halves of a torn paper edge along the code's left flank, from a photographed
    # real case. They are separate parameters because they break the pipeline in different
    # places, and a composite axis could not attribute either: measured, `tear` alone takes
    # out finder detection while `curl` alone leaves it intact and displaces the grid. Set
    # both to reproduce the photograph; set one to measure what it does.
    #
    # `tear` is the optical half: the curled edge shades the quiet zone with a soft gray
    # strip about as dark as a module column, offering the geometry a false dark column to
    # lock onto right where the left finders' dark edge belongs.
    tear: float = 0.0
    # `curl` is the geometric half: the lift of the curled edge displaces the modules nearest
    # to it, most at the bottom-left corner and not at all across the rest of the code. That
    # shape is exactly what neither a homography nor the edge-pinned bow can express -- the
    # bow's bumps vanish at the borders, which is where this damage lives.
    curl: float = 0.0


def _cylinder_map(shape: tuple[int, int], curvature: float):
    """Map a flat surface onto a cylinder.

    This is exactly the distortion that pushes a homography to its limit: it is non-linear, it
    compresses towards the edges, and it makes an otherwise perfect grid drift by half a module.
    """
    h, w = shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    u = (xx - w / 2.0) / (w / 2.0)
    # Backward mapping: where in the original does the target pixel come from?
    source_u = np.arcsin(np.clip(u * np.sin(curvature * np.pi / 2), -1, 1)) / (
        curvature * np.pi / 2 + 1e-9
    )
    map_x = (source_u * (w / 2.0) + w / 2.0).astype(np.float32)
    return map_x, yy


def render_photo(matrix: np.ndarray, damage: Damage, seed: int = 0) -> np.ndarray:
    """Turn a module matrix into an image that resembles a real photograph."""
    rng = np.random.default_rng(seed)
    px = int(round(damage.module_px))
    quiet = 5

    cells = np.where(matrix, np.float32(0.0), np.float32(1.0))
    plane = np.kron(cells, np.ones((px, px), dtype=np.float32))
    plane = np.pad(plane, quiet * px, constant_values=1.0)
    h, w = plane.shape

    # Dot raster: an engraving is not a blot but a pattern of individual dots.
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    raster = np.sin(xx * np.pi / damage.raster_period) * np.sin(yy * np.pi / damage.raster_period)
    raster = (raster > 0).astype(np.float32)
    engraved = np.where(plane < 0.5, 1.0 - damage.raster_depth * raster, plane)

    # Contrast: the engraving is only slightly darker than the white plastic around it.
    img: np.ndarray = 1.0 - damage.contrast * (1.0 - engraved)

    if damage.tear > 0:
        # The penumbra of the curled torn edge: a soft, several-module-wide gradient in the
        # quiet zone, peaking *outside* the code and reaching in only with its tail.
        #
        # The first version of this was a narrow triangular bar centred 0.8 modules outside
        # the edge, and it failed as an instrument for a measured reason: its support ran
        # straight over the finder's outer rings, so it destroyed finder detection long
        # before it could mislead any geometry. At tear 1.0 the detector found one finder
        # instead of three. A real torn edge does not cast a bar -- it is out of focus and
        # its shadow spans several modules, which is what lets the finders survive it.
        #
        # Gaussian rather than triangular for the same reason: a hard edge is a feature the
        # binarisation can latch onto in its own right, and the point here is a gradient.
        centre = (quiet - 1.5) * px
        sigma = 1.5 * px
        profile = np.exp(-((xx - centre) ** 2) / (2.0 * sigma**2))
        # Capped below full module darkness: the real strip is a shadow, not ink.
        img = np.clip(img - damage.tear * damage.contrast * 0.85 * profile, 0.0, 1.0)

    if damage.rotation_deg:
        rotation = cv2.getRotationMatrix2D((w / 2, h / 2), damage.rotation_deg, 1.0)
        img = cv2.warpAffine(img, rotation, (w, h), borderValue=1.0)

    if damage.curvature > 0:
        map_x, map_y = _cylinder_map((h, w), damage.curvature)
        img = cv2.remap(img, map_x, map_y, cv2.INTER_LINEAR, borderValue=1.0)

    if damage.curl > 0:
        # The curl of the torn edge: a horizontal displacement that peaks at the
        # bottom-left corner and decays within a few modules of the edge. Zero along the
        # top and the far side -- so no homography can absorb it, and the bow cannot
        # either, because its bumps vanish exactly at the edges where this lives.
        #
        # Applied after the cylinder rather than with it, because the two are different
        # surfaces: the cylinder bends the whole sheet, this lifts one edge of it. Scaled in
        # modules, so the damage means the same thing at any module_px.
        depth = yy / np.float32(max(h - 1, 1))
        reach = np.exp(-np.maximum(xx - quiet * px, 0.0) / np.float32(4.0 * px))
        curl_x = (xx - damage.curl * 1.5 * px * depth * reach).astype(np.float32)
        img = cv2.remap(img, curl_x, yy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)

    # Glare: a broad bright lobe across the image.
    gy, gx = np.mgrid[0:h, 0:w].astype(np.float32)
    glare = np.exp(-(((gx - w * 0.35) ** 2 + (gy - h * 0.2) ** 2) / (2 * (w * 0.6) ** 2)))
    img = np.clip(img * (1.0 - damage.glare * 0.5) + damage.glare * glare * 0.5, 0, 1)

    if damage.stain > 0:
        cy, cx = rng.uniform(0.2, 0.8, size=2) * np.array([h, w])
        radius = rng.uniform(0.12, 0.25) * w
        blob = np.exp(-(((gx - cx) ** 2 + (gy - cy) ** 2) / (2 * radius**2)))
        img = np.clip(img - damage.stain * blob, 0, 1)

    if damage.blur > 0:
        img = cv2.GaussianBlur(img, (0, 0), damage.blur)

    if damage.inverted:
        # Inverted at the end, after glare and stains, so those keep behaving like light
        # falling on a surface rather than like a second, negated illumination.
        img = 1.0 - img

    out = np.clip(img * 255.0 + rng.normal(0, damage.noise, img.shape), 0, 255).astype(np.uint8)
    return cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)


def make_case(text: str, damage: Damage | None = None, seed: int = 0):
    """Encode the text, spoil it, and return (photograph, true matrix)."""
    matrix = reencode(text)
    return render_photo(matrix, damage or Damage(), seed=seed), matrix
