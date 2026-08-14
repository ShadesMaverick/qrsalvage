"""Find the finders, build the grid, then nudge the grid until it fits.

This is where the real search of the method happens. The space is continuous (eight corner
coordinates) and the signal from the known cells is dense, which is why hill climbing works
here -- whereas on the bit level there is nothing to climb.
"""

from __future__ import annotations

from dataclasses import dataclass

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
    contours, hierarchy = cv2.findContours(binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
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


def order_finders(finders):
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


def evaluate(gray, corners, modules, scale, known_dark, known_light) -> GridFit:
    """Score one corner placement against the cells whose value the standard fixes."""
    warped = warp(gray, corners, modules, scale)
    means, _ = sample_cells(warped, modules, scale)
    fit = estimate_levels(means, known_dark, known_light)
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


def refine_corners(
    gray, corners, modules, scale, known_dark, known_light, start_delta: float = 3.0
) -> GridFit:
    """Nudge the four corners until the known cells sit as well as they can.

    A homography cannot represent a curved surface exactly. The best available approximation
    is not analytically available, but it is findable: coordinate descent with a shrinking step
    size, scored against the known cells.
    """
    current = np.array(corners, dtype=np.float64)
    best = evaluate(gray, current, modules, scale, known_dark, known_light)
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
        if not improved:
            delta /= 2.0
    return best
