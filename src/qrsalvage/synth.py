"""Artificially degraded QR codes whose answer is known.

Working backwards solves the fundamental problem of development here: a corpus built from a
single photograph measures nothing. If you know the plain text you can generate arbitrarily
many cases whose solution is settled -- and then quantify every change to the method instead
of believing in it.

The four kinds of damage reproduced are the ones from the original photograph: curvature, the
dot raster of a laser engraving, a glare gradient and dirt.
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
    img = 1.0 - damage.contrast * (1.0 - engraved)

    if damage.rotation_deg:
        rotation = cv2.getRotationMatrix2D((w / 2, h / 2), damage.rotation_deg, 1.0)
        img = cv2.warpAffine(img, rotation, (w, h), borderValue=1.0)

    if damage.curvature > 0:
        map_x, map_y = _cylinder_map((h, w), damage.curvature)
        img = cv2.remap(img, map_x, map_y, cv2.INTER_LINEAR, borderValue=1.0)

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

    out = np.clip(img * 255.0 + rng.normal(0, damage.noise, img.shape), 0, 255).astype(np.uint8)
    return cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)


def make_case(text: str, damage: Damage | None = None, seed: int = 0):
    """Encode the text, spoil it, and return (photograph, true matrix)."""
    matrix = reencode(text)
    return render_photo(matrix, damage or Damage(), seed=seed), matrix
