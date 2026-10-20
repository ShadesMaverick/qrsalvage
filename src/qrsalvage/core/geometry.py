"""Find the finders, build the grid, then nudge the grid until it fits.

This is where the real search of the method happens. The space is continuous (eight corner
coordinates) and the signal from the known cells is dense, which is why hill climbing works
here -- whereas on the bit level there is nothing to climb.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import cast

import cv2
import numpy as np

from .sampling import (
    buried_cells,
    estimate_levels,
    featureless_depth,
    posterior_dark,
    sample_cells,
    warp,
)
from .structure import is_valid_size, structure_mask

# The witness floor: a candidate grid is only judgeable while at least this fraction of its
# known cells stands on readable surface. Below it the wrong-cell count is a statement about
# the damage, not the placement, and the candidate is scored as unjudgeable rather than as
# accidentally clean -- otherwise the grid that buries most of its witnesses wins by silencing
# them.
ALIVE_KNOWN_FLOOR = 0.5

# How much the grid objective listens to the cells the standard does not fix. Zero reproduces
# the known-cell-only objective exactly. See the note at its use in _score for what it
# measures and why it can only ever be an addition; scripts/ab_coherence.py for what it buys.
#
# The value comes from the photograph that motivated the term -- a torn printout whose grid
# settled half a module into the shadow of the paper edge. Measured on it, sweeping the
# weight with the coarse restart disabled so the fine descent has to do the work alone: at 0
# and 0.2 the descent stays stuck (21 and 16 of 244 known cells wrong, no recovery); from 0.4
# it escapes and decodes on the first attempt; at 0.6 it does so with no uncertain cell left
# at all. 0.6 is the first value with margin above the threshold rather than sitting on it.
#
# Note what this replaces rather than adds to: COARSE_RESTART rescued the same photograph by
# searching harder, this one by making the wrong placement stop being a local optimum. The
# restart stays because it costs nothing when it does not fire, but it is no longer what
# carries this case.
#
# MEASURED ON THE SYNTHETIC AXES (scripts/ab_coherence.py, w=0.0 against w=0.6): level within
# noise everywhere. Contrast 8/8, 7/8, 7/8 in both arms; curvature 8/8, 8/8, 0/8 in both (the
# 0.85 failures pick a wrong size in both arms -- that level is unfittable, not misled);
# stain 6/8, 5/8, 4/8 in both. Resolution first looked like a regression (6/8 to 4/8 at
# 5 px, n=8) and dissolved on re-measurement with n=16: 9/16 without, 11/16 with. The term
# converts no synthetic case and spoils none; what it is for is the trapped-descent geometry
# above, which the synthetic corpus cannot reproduce (see restart_coarse on why).
COHERENCE_WEIGHT = 0.6


@dataclass(frozen=True)
class GridFit:
    """Result of fitting a grid for one assumed code size."""

    modules: int
    corners: np.ndarray
    quality: float
    wrong_known: int
    known_total: int
    means: np.ndarray
    posterior: np.ndarray
    bow: np.ndarray | None = None


@dataclass(frozen=True)
class CurvedOutline:
    """Four clockwise QR corners and the top/right/bottom/left curve midpoints."""

    corners: np.ndarray
    edge_midpoints: np.ndarray

    def __post_init__(self) -> None:
        if self.corners.shape != (4, 2):
            raise ValueError("corners must have shape (4, 2)")
        if self.edge_midpoints.shape != (4, 2):
            raise ValueError("edge_midpoints must have shape (4, 2)")


def _flat_edge_midpoints(corners: np.ndarray) -> np.ndarray:
    """Project the four unit-square edge midpoints through the corner homography."""
    if corners.shape != (4, 2):
        raise ValueError("corners must have shape (4, 2)")
    unit_corners = np.array([[0, 0], [1, 0], [0, 1], [1, 1]], dtype=np.float32)
    homography = cv2.getPerspectiveTransform(
        unit_corners, np.asarray(corners, dtype=np.float32)
    )
    unit_midpoints = np.array(
        [[[0.5, 0.0], [1.0, 0.5], [0.5, 1.0], [0.0, 0.5]]], dtype=np.float32
    )
    return cv2.perspectiveTransform(unit_midpoints, homography)[0].astype(np.float64)


def outline_midpoints(corners: np.ndarray, bow: np.ndarray | None) -> np.ndarray:
    """Return actual top/right/bottom/left points at the middle of each curved edge."""
    midpoints = _flat_edge_midpoints(corners)
    if bow is None:
        return midpoints
    if bow.shape != (8,):
        raise ValueError("bow must have shape (8,)")
    offsets = np.array([bow[0:2], bow[6:8], bow[2:4], bow[4:6]])
    return midpoints + offsets


def bow_from_midpoints(corners: np.ndarray, midpoints: np.ndarray) -> np.ndarray:
    """Translate actual top/right/bottom/left midpoint positions to the eight bow scalars."""
    if midpoints.shape != (4, 2):
        raise ValueError("midpoints must have shape (4, 2)")
    offsets = np.asarray(midpoints, dtype=np.float64) - _flat_edge_midpoints(corners)
    return np.concatenate((offsets[0], offsets[2], offsets[3], offsets[1]))


def find_finders(binary: np.ndarray, min_size: int = 20) -> list[tuple[float, float, float]]:
    """Search for finder patterns. Returns (cx, cy, outer width), largest first.

    A finder is three nested squares, so it appears as a contour with two levels of nesting.
    Candidates at the same location are merged.
    """
    contours, found = cv2.findContours(binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    # cv2's stubs promise an array, but an image without any contours yields None.
    hierarchy = cast("np.ndarray | None", found)
    if hierarchy is None:
        return []
    hierarchy = hierarchy[0]

    raw: list[tuple[float, float, float]] = []
    for i, contour in enumerate(contours):
        depth, child = 0, hierarchy[i][2]
        while child != -1 and depth < 3:
            depth += 1
            child = hierarchy[child][2]
        if depth < 2:
            continue
        x, y, w, h = cv2.boundingRect(contour)
        if w < min_size or h < min_size or not 0.75 <= w / h <= 1.33:
            continue
        raw.append((x + w / 2.0, y + h / 2.0, (w + h) / 2.0))

    merged: list[tuple[float, float, float]] = []
    for cx, cy, size in sorted(raw, key=lambda t: -t[2]):
        if any(abs(cx - mx) < size / 2 and abs(cy - my) < size / 2 for mx, my, _ in merged):
            continue
        merged.append((cx, cy, size))
    return merged


def finder_triple_score(triple: list[tuple[float, float, float]]) -> float:
    """How little three candidates look like one code's three finders. Lower is better.

    The two properties genuine finders share: nearly identical width, and an arrangement of
    two equal, perpendicular sides. A clean photographed triple scores well under 0.3; a triple
    completed by an artefact -- a bulb rim, the code's own outline picked up as one contour --
    lands past 1.0, driven by the width term. Degenerate triples score infinity.
    """
    widths = [w for _, _, w in triple]
    if len(triple) != 3 or min(widths) <= 0:
        return float(np.inf)
    width_spread = (max(widths) - min(widths)) / max(widths)

    points = [np.array([x, y], dtype=np.float64) for x, y, _ in triple]
    corner_scores = []
    for c in range(3):
        a, b = (points[m] for m in range(3) if m != c)
        v1, v2 = a - points[c], b - points[c]
        n1, n2 = float(np.linalg.norm(v1)), float(np.linalg.norm(v2))
        if n1 < 1e-6 or n2 < 1e-6:
            continue
        right_angle = abs(float(np.dot(v1, v2))) / (n1 * n2)
        equal_sides = abs(n1 - n2) / max(n1, n2)
        corner_scores.append(right_angle + equal_sides)
    if not corner_scores:
        return float(np.inf)

    # A code smaller than a few finder widths across is a coincidence, not a code.
    span = min(float(np.linalg.norm(points[a] - points[b])) for a, b in ((0, 1), (0, 2), (1, 2)))
    if span < 2.0 * max(widths):
        return float(np.inf)

    return min(corner_scores) + 2.0 * width_spread


def select_finder_triple(
    candidates: list[tuple[float, float, float]], limit: int = 10
) -> list[tuple[float, float, float]]:
    """Pick the three candidates that actually look like one code's finders.

    Taking the three largest is wrong, and it fails on exactly the photographs people bring:
    a bulb rim, a label edge or a reflection produces a large false candidate that outranks the
    real ones. The three genuine finders always share two properties instead -- nearly identical
    width, and an arrangement of two equal, perpendicular sides. Both are scored by
    :func:`finder_triple_score`, and the best-scoring triple wins. Whether even the winner is
    worth believing is the caller's question, and the same score answers it.
    """
    pool = candidates[:limit]
    if len(pool) < 3:
        return list(candidates[:3])

    best, best_score = None, np.inf
    for i in range(len(pool)):
        for j in range(i + 1, len(pool)):
            for k in range(j + 1, len(pool)):
                triple = [pool[i], pool[j], pool[k]]
                score = finder_triple_score(triple)
                if score < best_score:
                    best_score, best = score, triple

    return best if best is not None else list(pool[:3])


def third_finder_candidates(
    a: tuple[float, float, float], b: tuple[float, float, float], scale: float = 1.0
) -> list[tuple[float, float, float]]:
    """Where the missing third finder could be, given two that were found.

    A QR code is square, so two finder centres already fix the geometry up to a small number of
    discrete choices. Either the two are adjacent -- then the third sits perpendicular to their
    line, at the same distance, from one end or the other, on one side or the other. Or they are
    the diagonal pair, and the third completes a right isoceles triangle on one side or the
    other. Six candidates in total.

    They are not distinguished here. That is deliberate: the grid fit already scores every
    candidate against the cells the standard fixes, and a wrong corner produces an obviously
    worse score than the right one. Guessing badly is cheap; guessing silently is not.

    `scale` stretches the constructed offset. The right-angle construction assumes the pair's
    plane is parallel to the sensor; under real perspective the third finder sits closer or
    further by a few percent, and each scale is a different descent basin -- see the anchor
    sweep in pipeline.py for why the basins have to be enumerated rather than found.
    """
    pa = np.array([a[0], a[1]], dtype=np.float64)
    pb = np.array([b[0], b[1]], dtype=np.float64)
    width = (a[2] + b[2]) / 2.0
    delta = pb - pa
    distance = float(np.linalg.norm(delta))
    if distance < 1e-6:
        return []
    perpendicular = np.array([-delta[1], delta[0]]) / distance

    candidates: list[np.ndarray] = []
    for sign in (1.0, -1.0):
        offset = perpendicular * distance * scale * sign
        candidates.append(pa + offset)
        candidates.append(pb + offset)
        # The diagonal reading: a and b are opposite corners, the third completes the square.
        candidates.append((pa + pb) / 2.0 + perpendicular * (distance * scale / 2.0) * sign)

    return [(float(p[0]), float(p[1]), width) for p in candidates]


def order_finders(
    finders: list[tuple[float, float, float]],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Order three finders into (top-left, top-right, bottom-left).

    Top-left is the one at the right angle; which of the other two is top-right follows from
    the orientation of the cross product.
    """
    points = [np.array([x, y], dtype=np.float64) for x, y, _ in finders]
    best, best_score = None, np.inf
    for i in range(3):
        j, k = (m for m in range(3) if m != i)
        v1, v2 = points[j] - points[i], points[k] - points[i]
        norm = float(np.linalg.norm(v1) * np.linalg.norm(v2)) + 1e-9
        score = abs(float(np.dot(v1, v2))) / norm
        if score < best_score:
            best_score, best = score, (i, j, k)
    assert best is not None  # every triple scores finite, so the first iteration already sets it
    i, j, k = best
    top_left, a, b = points[i], points[j], points[k]
    cross = (a - top_left)[0] * (b - top_left)[1] - (a - top_left)[1] * (b - top_left)[0]
    return (top_left, a, b) if cross > 0 else (top_left, b, a)


def initial_corners(
    top_left: np.ndarray, top_right: np.ndarray, bottom_left: np.ndarray, modules: int
) -> np.ndarray:
    """Code corners from the finder centres: 3.5 modules outward along both axes."""
    ex = (top_right - top_left) / max(float(np.linalg.norm(top_right - top_left)), 1e-9)
    ey = (bottom_left - top_left) / max(float(np.linalg.norm(bottom_left - top_left)), 1e-9)
    span = (
        float(np.linalg.norm(top_right - top_left)) + float(np.linalg.norm(bottom_left - top_left))
    ) / 2.0
    offset = 3.5 * span / (modules - 7)
    return np.array(
        [
            top_left - ex * offset - ey * offset,
            top_right + ex * offset - ey * offset,
            bottom_left - ex * offset + ey * offset,
            top_right + bottom_left - top_left + ex * offset + ey * offset,
        ]
    )


def _score(
    warped: np.ndarray,
    corners: np.ndarray,
    modules: int,
    scale: int,
    known_dark: np.ndarray,
    known_light: np.ndarray,
    bow: np.ndarray | None = None,
) -> GridFit:
    """Score one rectification against the cells whose value the standard fixes.

    Plus, optionally, against the cells whose value it does not -- see COHERENCE_WEIGHT.
    """
    means, spread = sample_cells(warped, modules, scale)
    fit = estimate_levels(means, spread, known_dark, known_light)
    posterior = posterior_dark(means, fit)

    known = known_dark | known_light
    known_total = int(known.sum())

    # Quality: mean contrast-normalised distance from the threshold. Smooth enough to optimise
    # against, unlike the integer error count.
    #
    # Deliberately *unweighted* by the featureless depth below, and that took a broken
    # photograph to learn: a descent whose objective discounts cells standing in featureless
    # ground is rewarded for pushing troublesome cells INTO that ground, where they stop
    # costing -- it reported fewer wrong cells than the honest objective and produced a grid
    # whose data no longer decoded. The witness discount is safe only where nothing can move:
    # in the wrong-cell count that ranks finished candidates, never in the score a descent
    # climbs.
    margin = np.where(known_dark, fit.threshold - means, means - fit.threshold) / fit.contrast
    quality = float(np.tanh(margin[known] * 4.0).mean())

    if COHERENCE_WEIGHT > 0.0 and (~known).any():
        # What the known cells cannot say. They ring the code, so the objective has been deaf
        # to the several hundred data cells in the middle -- and a grid half a module out of
        # phase is visible in every one of them: each cell straddles two modules, so its core
        # mixes dark and light, its mean lands near the threshold and its internal spread
        # rises. Seated correctly, the same cells read cleanly one way or the other.
        #
        # The posterior already carries both halves of that signal (distance from the
        # threshold through the mean, uncertainty through the spread-fed sigma), so mean
        # confidence over the unknown cells is the whole term, bounded in [0, 1] like the
        # known-cell term it is added to.
        #
        # It cannot replace the known-cell term, only add to it: coherence alone is maximised
        # by any grid that lands wholly inside a uniform area, which the known cells are what
        # rules out. Hence a weight, and hence a measurement of it.
        quality += COHERENCE_WEIGHT * float(np.abs(2.0 * posterior[~known] - 1.0).mean())

    # The wrong count, unlike the quality, excludes the cells standing in featureless ground:
    # a known cell there is not wrong about the placement, it is wrong about the world -- the
    # print under it is gone -- and counting it makes every candidate on a damaged photograph
    # look misplaced. The survivors are extrapolated to the full ring so candidates whose
    # damage differs stay comparable: three wrong of a hundred living witnesses is the same
    # placement quality as six of two hundred. Only the selection between finished candidates
    # reads this number, never the descent, so it cannot teach anyone to bury witnesses.
    hard = means < fit.threshold
    depth = featureless_depth(posterior, known)
    alive = known & ~buried_cells(depth)
    alive_count = int(alive.sum())
    if alive_count < ALIVE_KNOWN_FLOOR * known_total:
        # Too little living testimony to judge the placement at all. Worst possible count,
        # not a lucky zero: the grid that buries its jury must not outrank one that faces it.
        wrong = known_total
    else:
        wrong_alive = int((hard[alive] != known_dark[alive]).sum())
        wrong = int(round(wrong_alive * known_total / alive_count))

    return GridFit(
        modules=modules,
        corners=np.asarray(corners, dtype=np.float64),
        quality=quality,
        wrong_known=wrong,
        known_total=known_total,
        means=means,
        posterior=posterior,
        bow=None if bow is None else np.asarray(bow, dtype=np.float64).copy(),
    )


def evaluate(
    gray: np.ndarray,
    corners: np.ndarray,
    modules: int,
    scale: int,
    known_dark: np.ndarray,
    known_light: np.ndarray,
) -> GridFit:
    """Score one corner placement against the cells whose value the standard fixes."""
    warped = warp(gray, corners, modules, scale)
    return _score(warped, corners, modules, scale, known_dark, known_light)


def evaluate_bowed(
    gray: np.ndarray,
    corners: np.ndarray,
    bow: np.ndarray,
    modules: int,
    scale: int,
    known_dark: np.ndarray,
    known_light: np.ndarray,
) -> GridFit:
    warped = _bowed_warp(gray, corners, bow, modules, scale)
    return _score(warped, corners, modules, scale, known_dark, known_light, bow=bow)


def _bowed_warp(
    gray: np.ndarray, corners: np.ndarray, bow: np.ndarray, modules: int, scale: int
) -> np.ndarray:
    """Rectify with a homography plus a quadratic bow per code edge, blended inward.

    The mathematical gap this closes: a homography maps straight lines to straight lines, and a
    module row on a curved surface is not a straight line in the photograph -- it bows. Four
    corners have no way to say "bow"; they can only tilt the plane.

    Each edge gets its own bow vector, swept across the code with linear falloff towards the
    opposite edge -- a Coons patch whose boundary curves are the homography edges plus one
    quadratic bump each. The corner-correction term a Coons patch normally needs vanishes here,
    because the bump 4t(1-t) is zero at both ends of its edge: every corner stays exactly where
    the flat fit pinned it. Eight scalars in all.

    Why per edge, and not the two shared vectors this started with: a shared vector displaces
    the top and bottom module rows identically, which is a cylinder and nothing else. A domed
    or dished sheet -- paper bulging toward the camera, a lens-distorted scan -- bows the two
    edges in *opposite* directions, and the shared parametrisation cannot say that at any
    weight. The tied version survives inside this one (top equal to bottom, left to right), so
    the models nest; scripts/ab_dome.py measures what untying buys and what it costs.

    Not a control lattice. A first version used a 3x3 lattice of free offsets -- eighteen
    parameters -- and it *overfitted the border*: the objective is measured on the known cells,
    which ring the code, so the lattice bought border margin by bending the unmeasured middle,
    and images the flat grid solved stopped decoding. Edge bows cannot express "fix the border,
    trash the middle": the interior is the bilinear blend of the edges, nothing about it is
    free. The known cells sit exactly on the edges being parametrised, and since the coherence
    term (COHERENCE_WEIGHT) the middle is no longer even unmeasured.

    Zero bow reproduces the homography exactly, so the two models nest.
    """
    n = modules * scale
    destination = np.array([[0, 0], [n, 0], [0, n], [n, n]], dtype=np.float32)
    # module space -> image space, the inverse of the mapping warp() hands to warpPerspective
    homography = cv2.getPerspectiveTransform(destination, np.asarray(corners, dtype=np.float32))

    xs, ys = np.meshgrid(np.arange(n, dtype=np.float64), np.arange(n, dtype=np.float64))
    denominator = homography[2, 0] * xs + homography[2, 1] * ys + homography[2, 2]
    map_x = (homography[0, 0] * xs + homography[0, 1] * ys + homography[0, 2]) / denominator
    map_y = (homography[1, 0] * xs + homography[1, 1] * ys + homography[1, 2]) / denominator

    u = xs / max(n - 1, 1)
    v = ys / max(n - 1, 1)
    bump_u = 4.0 * u * (1.0 - u)
    bump_v = 4.0 * v * (1.0 - v)
    # bow: (top, bottom, left, right) as x/y pairs. Top fades toward the bottom edge and
    # vice versa; left and right likewise across.
    along_u_x = bump_u * ((1.0 - v) * bow[0] + v * bow[2])
    along_u_y = bump_u * ((1.0 - v) * bow[1] + v * bow[3])
    along_v_x = bump_v * ((1.0 - u) * bow[4] + u * bow[6])
    along_v_y = bump_v * ((1.0 - u) * bow[5] + u * bow[7])
    map_x = map_x + along_u_x + along_v_x
    map_y = map_y + along_u_y + along_v_y

    return cv2.remap(
        gray,
        map_x.astype(np.float32),
        map_y.astype(np.float32),
        cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=255,
    )


def refine_bow(
    gray: np.ndarray,
    fit: GridFit,
    known_dark: np.ndarray,
    known_light: np.ndarray,
    scale: int = 12,
    start_delta: float = 3.0,
    min_delta: float = 0.1,
    on_step: Callable[[GridFit], None] | None = None,
) -> GridFit:
    """Let the fitted grid bow, after the flat refinement has done all a plane can do.

    Same coordinate descent, same smooth objective as refine_corners, over the eight bow
    parameters of :func:`_bowed_warp`. Separate stage on purpose: run on every candidate size
    it would multiply the search cost, while the bow only matters once the size is settled --
    so the corners carry the search and the bow is granted only to the winner.

    Starting at zero bow reproduces the homography result, and the descent keeps a change only
    when the objective improves, so this cannot return a worse grid than it was given. The
    stopping step is coarser than the corner refinement's 0.05 px: a bow is a broad, smooth
    correction, and chasing it below a tenth of a pixel buys noise, not signal.

    MEASURED RESULT, in two halves (scripts/ab_bow.py). On the synthetic cylinder: nothing --
    16/16, 16/16, 3/16, 0/16 across curvature 0.5 to 0.85, identical with and without, at
    about 20 percent extra runtime. The corner refinement already absorbs a *uniform* cylinder
    within the resolution-readable zone, and past that the edge modules are compressed below
    five pixels, where the failure is information, not geometry. Joint descent over corners
    and bow together was also tried and also moved nothing there.

    On real damage the ledger flips: a photographed fabric label that no configuration without
    the bow could solve (13 damaged codewords, six beyond the erasure budget at every setting)
    decodes *directly* with it -- one attempt, no probing. Cloth drapes; its bow is uneven and
    genuinely quadratic-ish in a way the synthetic cylinder, tamed by the corners, is not. The
    stage stays on for that photograph's sake: synthetic damage shows the term is harmless,
    real damage shows why it exists.

    The per-edge measurement is in scripts/ab_dome.py (16 images per level and arm), on the
    axis built for it: radial distortion, which bows opposite edges in opposite directions.
    At dome 0.12 the untied bow reads 15/16 against 7/16 for the tied one and for the flat
    grid -- the tied bow is *exactly* as blind there as no bow at all -- and at 0.15 it reads
    6/16 against 0/16 for both. On every gentler level all three arms are 16/16, so the extra
    freedom invents nothing. The cost is real: about a third over the tied bow on an easy
    image (82s against 62s for 16 solves), paid once per solve, on the winner only.

    The real photograph behind the axis: a code whose sides are visibly opposite arcs, which
    no configuration without per-edge bows could solve. Rectifying it by hand along its four
    boundary curves took 5.0 percent of known cells wrong to 0.4 and it decoded -- and with
    the edges untied the pipeline now does the same with no hand-drawn curves at all, in
    three decode attempts.
    """
    bow = fit.bow.copy() if fit.bow is not None else np.zeros(8, dtype=np.float64)

    def score(candidate: np.ndarray) -> GridFit:
        return evaluate_bowed(
            gray, fit.corners, candidate, fit.modules, scale, known_dark, known_light
        )

    best = score(bow)
    if best.quality < fit.quality:
        best = fit  # the remap disagrees with warpPerspective by a whisker; keep the better
    delta = start_delta
    while delta > min_delta:
        improved = False
        for axis in range(8):
            for step in (delta, -delta):
                candidate = bow.copy()
                candidate[axis] += step
                trial = score(candidate)
                if trial.quality > best.quality:
                    best, bow, improved = trial, candidate, True
                    if on_step:
                        on_step(best)
        if not improved:
            delta /= 2.0
    return best


def module_px(corners: np.ndarray, modules: int) -> float:
    """Pixels per module of a fitted grid, averaged over its two top edges."""
    top = float(np.linalg.norm(corners[1] - corners[0]))
    left = float(np.linalg.norm(corners[2] - corners[0]))
    return (top + left) / (2.0 * max(modules, 1))


def restart_coarse(
    gray: np.ndarray,
    fit: GridFit,
    known_dark: np.ndarray,
    known_light: np.ndarray,
    scale: int = 12,
    steps_in_modules: float = 2.0,
    on_step: Callable[[GridFit], None] | None = None,
) -> GridFit:
    """Run the corner descent again from a coarse step, for a grid that fitted badly.

    The descent in :func:`refine_corners` is local, and its 3 px start step is a fraction of a
    module on most photographs. That is right when the initial corners are already close, and
    it is a trap when something in the image offers a false optimum a module away. Observed on
    a photograph of a torn printout: the curled paper edge shaded the quiet zone into a soft
    dark strip exactly where the left finders' dark edge belongs, the descent settled half a
    module into it, and the grid stayed there with 19 of 244 known cells wrong -- while the
    timing pattern, which runs across the displacement, read a contented 100 percent.

    Escaping needs a step large enough to clear the false optimum in one move, so the step is
    measured in *modules*, not pixels: 3 px means half a module on one photograph and a fifth
    of one on the next. Measured on that photograph, restarting from the already-refined
    corners: 3 px and 6 px stay stuck (19 wrong, no decode), 9 px stays stuck, and 12 px --
    just under two modules there -- drops it to 9 wrong, 0 uncertain cells and a decode on the
    first attempt. 16 and 24 px land in the same place, so the effect is a threshold to clear,
    not a value to tune.

    Deliberately *not* the fix this looked like it needed. Masking the lying border column out
    of the objective was tried first and is the more elaborate idea; measured against this one
    it is unnecessary (all four border lines rescue the image equally once the step is coarse,
    including the three that are not damaged), and a coarse restart from the *initial* corners
    rather than the refined ones is actively worse (50 of 244 wrong). What matters is the
    combination: keep what the fine descent found, then let a coarse one try to leave it.

    MEASURED ON THE SYNTHETIC CORPUS: nothing at all (scripts/ab_restart.py, 16 images per
    level and arm). Curvature 0.70 and module size 5 px solve completely in both arms without
    the escalation ever firing; curvature 0.85 and 0.95 fire on all 16 images and rescue none;
    module size 4.5 and 4 px, and the torn-edge axis at 0.8 and 1.0, are level in both arms
    too. Every level, identical. (The torn-edge run predates both the split of that damage
    into an optical and a geometric half and the reshaping of its shadow, so it describes the
    axis as it then was rather than as it is now.)

    That is a statement about the corpus rather than about the escalation, and worth reading
    carefully before deleting either. A trapped descent and an unfittable surface both show up
    as a badly seated grid, and only the first is a local optimum. Strong synthetic curvature
    is the second: no step size reaches a placement a homography cannot express, which is why
    the escalation fires there on every image and helps none of them. The synthetic corpus has
    no case of the first kind -- the tear axis was built to add one and misses, because its
    shadow strip destroys finder detection before it traps anything. So the only evidence for
    this stage is the photograph that motivated it, and the only guard against it going stale
    is that photograph sitting in the private corpus.

    Kept only when the same objective the descent already optimises says it improved, so this
    can never return a worse grid than it was handed -- the same guarantee as
    :func:`refine_bow`, and for the same reason.
    """
    trial = refine_corners(
        gray,
        fit.corners,
        fit.modules,
        scale,
        known_dark,
        known_light,
        start_delta=steps_in_modules * module_px(fit.corners, fit.modules),
        on_step=on_step,
    )
    return trial if trial.quality > fit.quality else fit


def refine_corners(
    gray: np.ndarray,
    corners: np.ndarray,
    modules: int,
    scale: int,
    known_dark: np.ndarray,
    known_light: np.ndarray,
    start_delta: float = 3.0,
    on_step: Callable[[GridFit], None] | None = None,
) -> GridFit:
    """Nudge the four corners until the known cells sit as well as they can.

    A homography cannot represent a curved surface exactly. The best available approximation
    is not analytically available, but it is findable: coordinate descent with a shrinking step
    size, scored against the known cells.

    `on_step` is called with every fit the descent accepts, the starting one included. That is
    the hook the live view hangs on: the story of a recovery *is* this descent, and showing
    the true intermediate grids costs nothing beyond the improvements that happen anyway.
    """
    current = np.array(corners, dtype=np.float64)
    best = evaluate(gray, current, modules, scale, known_dark, known_light)
    if on_step:
        on_step(best)
    delta = start_delta
    while delta > 0.05:
        improved = False
        for corner in range(4):
            for axis in range(2):
                for step in (delta, -delta):
                    candidate = current.copy()
                    candidate[corner, axis] += step
                    trial = evaluate(gray, candidate, modules, scale, known_dark, known_light)
                    if trial.quality > best.quality:
                        best, current, improved = trial, candidate, True
                        if on_step:
                            on_step(best)
        if not improved:
            delta /= 2.0
    return best


def fit_outline(
    gray: np.ndarray,
    outline: CurvedOutline,
    sizes: Sequence[int],
    start_delta: float = 12.0,
    on_step: Callable[[GridFit], None] | None = None,
) -> list[GridFit]:
    """Fit and score each candidate size inside a manually supplied curved outline."""
    corners = outline.corners[[0, 1, 3, 2]]
    fits: list[GridFit] = []
    for modules in sizes:
        if not is_valid_size(modules):
            continue
        known_dark, known_light = structure_mask(modules)
        flat = refine_corners(
            gray,
            corners,
            modules,
            12,
            known_dark,
            known_light,
            start_delta=start_delta,
        )
        bow = bow_from_midpoints(flat.corners, outline.edge_midpoints)
        curved = evaluate_bowed(
            gray, flat.corners, bow, modules, 12, known_dark, known_light
        )
        fits.append(curved)
        if on_step:
            on_step(curved)
    return fits
