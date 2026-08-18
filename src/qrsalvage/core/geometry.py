"""Find the finders, build the grid, then nudge the grid until it fits.

This is where the real search of the method happens. The space is continuous (eight corner
coordinates) and the signal from the known cells is dense, which is why hill climbing works
here -- whereas on the bit level there is nothing to climb.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

import cv2
import numpy as np

from .sampling import estimate_levels, posterior_dark, sample_cells, warp


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


def select_finder_triple(
    candidates: list[tuple[float, float, float]], limit: int = 10
) -> list[tuple[float, float, float]]:
    """Pick the three candidates that actually look like one code's finders.

    Taking the three largest is wrong, and it fails on exactly the photographs people bring:
    a bulb rim, a label edge or a reflection produces a large false candidate that outranks the
    real ones. The three genuine finders always share two properties instead -- nearly identical
    width, and an arrangement of two equal, perpendicular sides. Both are scored here, and the
    best-scoring triple wins.
    """
    pool = candidates[:limit]
    if len(pool) < 3:
        return list(candidates[:3])

    best, best_score = None, np.inf
    for i in range(len(pool)):
        for j in range(i + 1, len(pool)):
            for k in range(j + 1, len(pool)):
                triple = [pool[i], pool[j], pool[k]]
                widths = [w for _, _, w in triple]
                if min(widths) <= 0:
                    continue
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
                    continue

                # A code smaller than a few finder widths across is a coincidence, not a code.
                span = min(
                    float(np.linalg.norm(points[a] - points[b]))
                    for a, b in ((0, 1), (0, 2), (1, 2))
                )
                if span < 2.0 * max(widths):
                    continue

                score = min(corner_scores) + 2.0 * width_spread
                if score < best_score:
                    best_score, best = score, triple

    return best if best is not None else list(pool[:3])


def third_finder_candidates(
    a: tuple[float, float, float], b: tuple[float, float, float]
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
        offset = perpendicular * distance * sign
        candidates.append(pa + offset)
        candidates.append(pb + offset)
        # The diagonal reading: a and b are opposite corners, the third completes the square.
        candidates.append((pa + pb) / 2.0 + perpendicular * (distance / 2.0) * sign)

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
) -> GridFit:
    """Score one rectification against the cells whose value the standard fixes."""
    means, spread = sample_cells(warped, modules, scale)
    fit = estimate_levels(means, spread, known_dark, known_light)
    posterior = posterior_dark(means, fit)

    known = known_dark | known_light
    # Quality: mean contrast-normalised distance from the threshold. Smooth enough to optimise
    # against, unlike the integer error count.
    margin = np.where(known_dark, fit.threshold - means, means - fit.threshold) / fit.contrast
    quality = float(np.tanh(margin[known] * 4.0).mean())
    hard = means < fit.threshold
    wrong = int((hard[known] != known_dark[known]).sum())

    return GridFit(
        modules=modules,
        corners=np.asarray(corners, dtype=np.float64),
        quality=quality,
        wrong_known=wrong,
        known_total=int(known.sum()),
        means=means,
        posterior=posterior,
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


def _bowed_warp(
    gray: np.ndarray, corners: np.ndarray, bow: np.ndarray, modules: int, scale: int
) -> np.ndarray:
    """Rectify with a homography plus two separable quadratic bows.

    The mathematical gap this closes: a homography maps straight lines to straight lines, and a
    module row on a cylinder is not a straight line in the photograph -- it bows. Four corners
    have no way to say "bow"; they can only tilt the plane.

    The parametrisation is deliberately the *smallest* one that can say it. A cylinder displaces
    grid lines by an arc that depends on one coordinate only, and with the corners already
    pinned by the flat fit, the quadratic bump 4t(1-t) is that arc's second-order shape. So:
    two bow vectors, one swept along each axis, four scalars in all.

    Not a control lattice. A first version used a 3x3 lattice of free offsets -- eighteen
    parameters -- and it *overfitted the border*: the objective is measured on the known cells,
    which ring the code, so the lattice bought border margin by bending the unmeasured middle,
    and images the flat grid solved stopped decoding. Four separable parameters cannot express
    "fix the border, trash the middle"; the constraint is the parametrisation itself, with no
    penalty weight to tune.

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
    map_x = map_x + bow[0] * bump_u + bow[2] * bump_v
    map_y = map_y + bow[1] * bump_u + bow[3] * bump_v

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

    Same coordinate descent, same smooth objective as refine_corners, over the four bow
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
    """
    bow = np.zeros(4, dtype=np.float64)

    def score(candidate: np.ndarray) -> GridFit:
        warped = _bowed_warp(gray, fit.corners, candidate, fit.modules, scale)
        return _score(warped, fit.corners, fit.modules, scale, known_dark, known_light)

    best = score(bow)
    if best.quality < fit.quality:
        best = fit  # the remap disagrees with warpPerspective by a whisker; keep the better
    delta = start_delta
    while delta > min_delta:
        improved = False
        for axis in range(4):
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
    module size 4.5 and 4 px, and the tear axis at 0.8 and 1.0, are level in both arms too.
    Every level, identical.

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
