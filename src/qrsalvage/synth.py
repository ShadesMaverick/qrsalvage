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

# Where the surviving strip of the neighbouring label sits, in modules: how wide it prints and
# how much clear paper separates it from the code. The gap is not cosmetic -- see the note at
# its use in render_photo.
REMNANT_WIDTH = 2
REMNANT_GAP = 1


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
    # How dark the surviving strip of the neighbouring label prints, as a fraction of a full
    # module. Unlike the two above it is not part of the torn edge itself but of what the tear
    # left behind, and it exists for one purpose: to put module-pitch structure where a
    # displaced grid's outermost column would otherwise find blank paper.
    remnant: float = 0.0
    # Radial barrel distortion around the code's centre: a sheet bulging toward the camera, or
    # a lens that was never corrected. Deliberately the damage a cylinder axis cannot stand in
    # for -- it bows opposite edges in opposite directions, which is invisible to a homography
    # *and* to any bow that displaces both edges identically. Positive values compress the
    # borders; the corners move most, so the flat corner fit absorbs part but not the arcs.
    dome: float = 0.0
    # The print simply ends: the bottom rows of the code never made it onto the surface, or
    # were rubbed off whole -- a photographed sticker lost its lower fifth this way, wall paint
    # showing where modules belong. As a fraction of the code's module rows. What makes it its
    # own axis rather than a stain at the edge: the lost area is *featureless*, so every cell
    # in it reads as a clean, confident light module unless something downstream knows better.
    worn: float = 0.0
    # Coloured strokes drawn across the code -- a highlighter, a ballpoint circle, printed
    # guide lines. The number of strokes. The only damage on the colour axis: through the blue
    # channel a red stroke is a row of fake dark modules, so what this measures is whether the
    # pipeline knows that colour is never ink.
    marker: float = 0.0


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

    # Padded in cell units and only then expanded to pixels, which is the same image as
    # expanding first and padding by quiet*px -- but it leaves the quiet zone addressable in
    # modules, which the remnant strip below needs in order to print on the code's own pitch.
    cells = np.pad(np.where(matrix, np.float32(0.0), np.float32(1.0)), quiet, constant_values=1.0)

    if damage.remnant > 0:
        # A strip of the neighbouring label left standing by the tear: same press, same pitch,
        # sitting in the quiet zone. Tear a sheet of labels apart and this is what stays.
        #
        # REMNANT_GAP is the whole design question. Butted against the code the strip merges
        # with the finders' outer ring in the binarisation, thickens it, breaks the 1:1:3:1:1
        # proportion the scan detector needs, and destroys detection -- the same way the old
        # shadow bar did. One clear module keeps the finders intact.
        #
        # Its own generator, so a case with no remnant renders bit-identical to before: the
        # shared `rng` also draws the sensor noise, and consuming from it here would shift
        # every existing synthetic image and silently invalidate measurements taken on them.
        strip = np.random.default_rng(seed + 9973)
        end = quiet - REMNANT_GAP
        start = max(end - REMNANT_WIDTH, 0)
        if end > start:
            dark = strip.integers(0, 2, size=(cells.shape[0], end - start)).astype(bool)
            cells[:, start:end] = np.where(dark, 1.0 - damage.remnant, 1.0)

    if damage.worn > 0:
        # In cell units, before optics: the print ends, it is not covered up. Everything the
        # camera later does -- blur, glare, noise -- happens to blank surface exactly as it
        # happens to the surviving modules.
        rows = int(round(damage.worn * matrix.shape[0]))
        if rows > 0:
            cells[cells.shape[0] - quiet - rows :, :] = 1.0

    plane = np.kron(cells, np.ones((px, px), dtype=np.float32))
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

    if damage.dome != 0:
        # Backward mapping: the target pixel at normalised radius r reads from radius
        # r*(1 + dome*r^2) in the flat original, so content is squeezed toward the centre as
        # the radius grows -- barrel distortion, centred on the code because the code sits
        # centred in its quiet zone. Composed after the cylinder for the same reason curl is:
        # they are different surfaces, and each keeps its own meaning when measured alone.
        cx, cy = (w - 1) / 2.0, (h - 1) / 2.0
        rx = (xx - cx) / cx
        ry = (yy - cy) / cy
        swell = 1.0 + damage.dome * (rx * rx + ry * ry)
        dome_x = (cx + (xx - cx) * swell).astype(np.float32)
        dome_y = (cy + (yy - cy) * swell).astype(np.float32)
        img = cv2.remap(img, dome_x, dome_y, cv2.INTER_LINEAR, borderValue=1.0)

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
    bgr = cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)

    if damage.marker > 0:
        # After the greyscale camera model on purpose: a stroke sits on top of the print, so
        # it is not blurred, curved or stained with it. Saturated red at roughly a module's
        # width, endpoints drawn from its own generator so every existing case stays
        # bit-identical -- the same isolation the remnant strip documents above.
        strokes = np.random.default_rng(seed + 4241)
        h2, w2 = bgr.shape[:2]
        for _ in range(int(round(damage.marker))):
            x0, x1 = strokes.uniform(0.05, 0.95, 2) * w2
            y0, y1 = strokes.uniform(0.05, 0.95, 2) * h2
            thickness = max(2, int(round(damage.module_px * strokes.uniform(0.7, 1.3))))
            cv2.line(bgr, (int(x0), int(y0)), (int(x1), int(y1)), (40, 40, 220), thickness)

    return bgr


def make_case(text: str, damage: Damage | None = None, seed: int = 0):
    """Encode the text, spoil it, and return (photograph, true matrix)."""
    matrix = reencode(text)
    return render_photo(matrix, damage or Damage(), seed=seed), matrix
