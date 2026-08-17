"""Finding finder patterns by scanning for their run-length signature.

The contour detector in geometry.py asks for three cleanly nested rings. That is a brittle
condition: a crease in the paper, a scratch across the print or a speck of grit breaks the
outer ring, the contour stops being a closed loop, and a finder that is perfectly obvious to
the eye disappears from the detector's view. On a corpus of eleven damaged codes collected from
the web, six failed before the pipeline even started, for exactly that reason.

This detector asks a different question. Along any line crossing a finder, the dark and light
runs have the proportions 1:1:3:1:1 -- that is what the pattern is *for*, and it holds along
every row and every column through the centre. Damage removes some of those lines; it does not
remove them all. Averaging over many scan lines is what makes the difference.

The two detectors are complementary, so the pipeline runs both and merges the results.
"""

from __future__ import annotations

from collections.abc import Iterator

import numpy as np

# How far a single run may deviate from the expected module width, as a fraction of it.
TOLERANCE = 0.5


def _runs(line: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Run-length encode a boolean line. Returns (starts, lengths, values)."""
    if line.size == 0:
        return np.empty(0, int), np.empty(0, int), np.empty(0, bool)
    change = np.flatnonzero(np.diff(line)) + 1
    starts = np.concatenate(([0], change))
    ends = np.concatenate((change, [line.size]))
    return starts, ends - starts, line[starts]


def _matches(five: np.ndarray) -> float:
    """Return the module width if five runs have the 1:1:3:1:1 shape, otherwise 0."""
    total = five.sum()
    if total < 7:
        return 0.0
    module = total / 7.0
    slack = module * TOLERANCE
    if (
        abs(module - five[0]) < slack
        and abs(module - five[1]) < slack
        and abs(3 * module - five[2]) < 3 * slack
        and abs(module - five[3]) < slack
        and abs(module - five[4]) < slack
    ):
        return module
    return 0.0


def _scan_line(line: np.ndarray) -> Iterator[tuple[float, float]]:
    """Yield (centre position, module width) for every finder signature along one line."""
    starts, lengths, values = _runs(line)
    if lengths.size < 5:
        return
    for i in range(lengths.size - 4):
        # The signature starts on a dark run: dark, light, dark, light, dark.
        if not values[i]:
            continue
        module = _matches(lengths[i : i + 5])
        if module:
            centre = starts[i + 2] + lengths[i + 2] / 2.0
            yield centre, module


def _cluster(points: list[tuple[float, float, float]], tolerance_factor: float = 0.7) -> list[dict]:
    """Merge candidates that describe the same finder.

    Every scan line through a finder produces its own candidate, so a clean finder arrives as a
    cloud of a few dozen. Their count is also the best evidence available: a cluster confirmed
    from many directions is a finder, a cluster of two is a coincidence in the texture.
    """
    clusters: list[dict] = []
    for x, y, module in points:
        for cluster in clusters:
            radius = tolerance_factor * max(cluster["module"], module)
            if abs(cluster["x"] - x) < radius and abs(cluster["y"] - y) < radius:
                n = cluster["n"]
                cluster["x"] = (cluster["x"] * n + x) / (n + 1)
                cluster["y"] = (cluster["y"] * n + y) / (n + 1)
                cluster["module"] = (cluster["module"] * n + module) / (n + 1)
                cluster["n"] = n + 1
                break
        else:
            clusters.append({"x": x, "y": y, "module": module, "n": 1})
    return clusters


def find_finders_scan(
    binary: np.ndarray, step: int = 2, min_support: int = 4
) -> list[tuple[float, float, float]]:
    """Locate finder patterns by their run-length signature.

    Returns (cx, cy, outer width) per candidate, strongest support first, so the result is
    interchangeable with the contour detector's.

    A horizontal hit alone is not enough -- a run of text or a barcode can produce one. Each
    horizontal candidate is therefore confirmed on its own column before it counts, which is
    what turns a one-dimensional coincidence into a two-dimensional pattern.
    """
    dark = binary < 128
    height, width = dark.shape

    horizontal: list[tuple[float, float, float]] = []
    for row in range(0, height, step):
        for centre, module in _scan_line(dark[row]):
            horizontal.append((centre, float(row), module))
    if not horizontal:
        return []

    confirmed: list[tuple[float, float, float]] = []
    for x, y, module in horizontal:
        column = dark[:, int(round(x))]
        for centre, vertical_module in _scan_line(column):
            # The vertical signature has to sit on the same spot and agree on the scale. The
            # tolerance is three modules rather than one, because the horizontal hit can come
            # from any row crossing the finder's middle band, not only from its centre row.
            if abs(centre - y) < 3.0 * module and 0.5 < vertical_module / module < 2.0:
                confirmed.append((x, centre, (module + vertical_module) / 2.0))
                break

    clusters = _cluster(confirmed)
    strong = [c for c in clusters if c["n"] >= min_support]
    strong.sort(key=lambda c: -c["n"])
    return [(c["x"], c["y"], c["module"] * 7.0) for c in strong]


def merge_finders(
    *groups: list[tuple[float, float, float]], tolerance: float = 0.6
) -> list[tuple[float, float, float]]:
    """Combine candidates from several detectors, dropping duplicates.

    Order matters: whatever the first detector found keeps its position, and later groups only
    contribute what nobody has seen yet. The contour detector is the more precise of the two
    when it works at all, so it goes first.
    """
    merged: list[tuple[float, float, float]] = []
    for group in groups:
        for x, y, size in group:
            radius = tolerance * max(size, 1.0)
            if any(abs(mx - x) < radius and abs(my - y) < radius for mx, my, _ in merged):
                continue
            merged.append((x, y, size))
    return merged
