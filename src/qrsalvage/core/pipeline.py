"""The whole path from photograph to plain text, without output and without file access.

This layer decides nothing on its own, it composes: preprocess, find the grid, try the versions,
sample, decode, probe if needed. All reporting is the caller's business -- the core stays free
of anything but library code.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from .decoding import SearchResult, decode_matrix, ordered_search
from .ensemble import (
    DEFAULT_FUSION,
    Consensus,
    GeometryConsensus,
    ImageConsensus,
    consensus_posterior,
    fuse_images,
    geometry_consensus,
)
from .geometry import (
    GridFit,
    find_finders,
    initial_corners,
    order_finders,
    refine_bow,
    refine_corners,
    select_finder_triple,
    third_finder_candidates,
)
from .layout import read_format
from .matrix import ModuleMatrix
from .preprocess import prepare
from .repair import RepairResult, repair_progressive, repair_scattered
from .scanfinder import find_finders_scan, merge_finders
from .structure import is_valid_size, structure_mask, timing_score, version_for_modules

DEFAULT_SIZES = (21, 25, 29, 33, 37, 41)
ENSEMBLE_MODES = ("off", "sampling", "geometry")

# Whether the winning grid gets the bowed refinement on top of the flat one. Measured in
# scripts/ab_bow.py: neutral on the synthetic cylinder, which the corner fit already absorbs,
# and decisive on a real fabric photograph that nothing else could solve. Details at
# geometry.refine_bow.
BOW_REFINE = True


def _emit(progress, event: str, **data) -> None:
    """Report one step of the recovery to whoever is watching.

    The core stays library-pure: it neither prints nor knows who listens -- the callback is
    injected by a shell, and a broken listener must never sink a recovery, so whatever it
    raises is swallowed here. Every payload is plain JSON types on purpose: the same events
    feed a terminal, a streaming HTTP response and, later, a web worker, and the cheapest way
    to keep three transports honest is to give them nothing that needs translating.
    """
    if progress is None:
        return
    try:
        progress(event, data)
    except Exception:  # noqa: S110 - a watcher must never sink the recovery it watches
        return


@dataclass
class SolveResult:
    """What an attempt produced -- including when it failed."""

    text: str | None
    modules: int | None = None
    version: int | None = None
    wrong_known: int | None = None
    wrong_sampled: int | None = None
    known_total: int | None = None
    timing: float | None = None
    uncertain: int | None = None
    candidates_tried: int = 0
    flipped: list[tuple[int, int]] = field(default_factory=list)
    matrix: ModuleMatrix | None = None
    decoded_matrix: np.ndarray | None = None
    finders: list[tuple[float, float, float]] = field(default_factory=list)
    per_size: list[GridFit] = field(default_factory=list)
    consensus: Consensus | None = None
    geometry: GeometryConsensus | None = None
    fusion: ImageConsensus | None = None
    repair: RepairResult | None = None
    inverted: bool = False
    ecc: str | None = None
    failure: str | None = None

    @property
    def solved(self) -> bool:
        return self.text is not None


SCALES = (1.0, 0.6, 0.4, 0.25)

# The band of pixels-per-module that prepare() is built for, and the value to aim at when a
# rescale is needed. Below the band a fixed 1.5 px blur smears neighbouring modules together;
# above it the adaptive threshold block covers too few modules to follow the illumination.
GOOD_MODULE_PX = (7.0, 16.0)
TARGET_MODULE_PX = 11.0
MAX_DIMENSION = 4000


def detect_finders(binary: np.ndarray) -> list[tuple[float, float, float]]:
    """Both detectors, merged.

    They fail on different things, which is the whole reason for keeping both. The contour
    detector wants three intact nested rings and gives a precise centre when it gets them; the
    scan detector only wants the 1:1:3:1:1 proportions to survive along enough lines, which
    they do through creases, grit and eroded edges. Contours go first so their precision wins
    wherever both saw the same pattern.
    """
    return merge_finders(find_finders(binary), find_finders_scan(binary))


def _search_scales(bgr: np.ndarray, scales=SCALES, invert: bool = False):
    """Look for the finders across a small scale pyramid and keep the best resolution.

    `prepare` is tuned for roughly nine pixels per module -- the adaptive threshold block is
    about four modules wide there, which is what lets it follow the illumination rather than
    the code. On a photograph taken closer, or with a better camera, a module can span twenty
    pixels; the block is then two modules wide and starts thresholding the modules themselves,
    and the finder search collapses. Downscaling puts the ratio back where the parameters
    assume it.

    This pass searches blind and only downwards, because a code too small to read is still
    findable while one whose modules are too large is not. Once something is found,
    :func:`_rescale_to_working_range` corrects the resolution in either direction.

    Returns the image actually used, so every coordinate downstream refers to it.
    """
    attempts = []
    for index, scale in enumerate(scales):
        used_scale = min(scale, 1.0)
        if scale >= 1.0:
            candidate = bgr
        else:
            candidate = cv2.resize(bgr, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        if min(candidate.shape[:2]) < 80:
            continue
        gray, binary = prepare(candidate, invert=invert)
        finders = detect_finders(binary)

        spread = 1.0
        if len(finders) >= 3:
            widths = [w for _, _, w in select_finder_triple(finders)]
            spread = (max(widths) - min(widths)) / max(max(widths), 1e-6)
        attempts.append((index, spread, len(finders), used_scale, candidate, gray, binary, finders))

        # A clean triple at the highest resolution that offers one is as good as it gets.
        if len(finders) >= 3 and spread < 0.15:
            break

    if not attempts:
        gray, binary = prepare(bgr, invert=invert)
        return bgr, gray, binary, detect_finders(binary), (0.0, 0.0, 1.0)

    # Ranking, in this order: having three finders at all beats everything, because without
    # them nothing downstream runs; then agreement on their width, since a disagreeing triple
    # usually means a false candidate crept in; then resolution. Getting this order wrong is
    # not academic -- an earlier version preferred a single finder at full resolution over
    # three finders at 60 percent, and lost images that were perfectly recoverable.
    def rank(attempt):
        index, spread, count, *_ = attempt
        return (count < 3, round(spread, 2), index)

    _, _, _, used_scale, candidate, gray, binary, finders = min(attempts, key=rank)
    return _rescale_to_working_range(bgr, candidate, gray, binary, finders, invert, used_scale)


def _prepare_with_hints(bgr: np.ndarray, points, invert: bool):
    """Bring a hand-marked photograph into the working range before measuring it.

    The escape hatch used to skip the resolution correction the automatic path gets, and
    failed exactly where it was needed: on a twelve-megapixel photograph the fixed
    preprocessing blur is a fraction of a module, the adaptive threshold block covers a corner
    of one, and the hand-marked finders sink with the ship. Measured before this function
    existed: ninety seconds of work ending in a grid with 65 of 236 known cells wrong, on a
    photograph whose cropped version fits cleanly.

    The three clicks themselves say how large the code is -- the two short sides of the
    triangle they span are (modules - 7) modules long -- so the photograph is cropped to the
    marked code and rescaled onto the band prepare() is built for, before anything is
    measured. The version is unknown here, so the middle of the candidate range sets the
    factor; every size from 21 to 41 modules then lands within about a module of the band,
    which prepare() tolerates.
    """
    pts = np.array(points, dtype=np.float64)
    sides = sorted(float(np.linalg.norm(pts[i] - pts[j])) for i, j in ((0, 1), (0, 2), (1, 2)))
    span = (sides[0] + sides[1]) / 2.0
    module_px = span / 22.0  # the middle of DEFAULT_SIZES, minus the 7 finder modules

    if span < 1.0 or GOOD_MODULE_PX[0] <= module_px <= GOOD_MODULE_PX[1]:
        gray, binary = prepare(bgr, invert=invert)
        return bgr, gray, binary, snap_to_finders(binary, points), (0.0, 0.0, 1.0)

    # Crop to the marked code first. The clicks bound it, and preparing twelve megapixels in
    # order to use one is what made this path minutes-slow. The margin covers the code's
    # reach past the finder centres plus the quiet zone, at the smallest version (0.55 spans).
    margin = 0.6 * span
    x0 = max(0, int(pts[:, 0].min() - margin))
    y0 = max(0, int(pts[:, 1].min() - margin))
    x1 = min(bgr.shape[1], int(pts[:, 0].max() + margin))
    y1 = min(bgr.shape[0], int(pts[:, 1].max() + margin))
    region = bgr[y0:y1, x0:x1]

    factor = TARGET_MODULE_PX / module_px
    if max(region.shape[:2]) * factor > MAX_DIMENSION:
        factor = MAX_DIMENSION / max(region.shape[:2])
    work = cv2.resize(
        region,
        None,
        fx=factor,
        fy=factor,
        interpolation=cv2.INTER_AREA if factor < 1.0 else cv2.INTER_CUBIC,
    )
    gray, binary = prepare(work, invert=invert)
    shifted = [((x - x0) * factor, (y - y0) * factor) for x, y in points]
    return work, gray, binary, snap_to_finders(binary, shifted), (float(x0), float(y0), factor)


def _attempt(bgr: np.ndarray, sizes, invert: bool, finder_points, progress=None):
    """One complete pass at one polarity: find the code, then fit every candidate grid."""
    if finder_points is not None:
        used, gray, binary, finders, transform = _prepare_with_hints(bgr, finder_points, invert)
    else:
        used, gray, binary, finders, transform = _search_scales(bgr, invert=invert)

    # Everything below runs in working-image coordinates; whoever watches sees the original
    # photograph, so every point in an event goes back through the transform first.
    ox, oy, factor = transform
    _emit(
        progress,
        "finders",
        count=len(finders),
        points=[{"x": x / factor + ox, "y": y / factor + oy} for x, y, _ in finders],
        inverted=invert,
    )

    def on_fit(fit) -> None:
        _emit(
            progress,
            "grid",
            modules=int(fit.modules),
            wrong=int(fit.wrong_known),
            total=int(fit.known_total),
            quality=round(float(fit.quality), 4),
            corners=[[c[0] / factor + ox, c[1] / factor + oy] for c in fit.corners.tolist()],
        )

    # Hand-placed centres are only ever approximate -- nobody clicks a module centre to the
    # pixel. The refinement therefore starts with a much coarser step so it can walk back a
    # misplaced click; with the automatic centres a fine step converges faster and better.
    delta = 12.0 if finder_points else 3.0

    fits: list[GridFit] = []
    if len(finders) >= 3:
        fits = fit_grid(gray, finders, sizes, start_delta=delta, on_step=on_fit)
    elif len(finders) == 2:
        # One finder may be worn away entirely, or merely faded enough that neither detector
        # recognises it -- both happen on real damage. The geometry is still determined up to
        # six discrete choices, so all of them are fitted and the known cells decide. This path
        # costs six times a normal fit, which is why it is a fallback.
        for third in third_finder_candidates(finders[0], finders[1]):
            if not (0 <= third[0] < gray.shape[1] and 0 <= third[1] < gray.shape[0]):
                continue
            fits.extend(fit_grid(gray, [*finders[:2], third], sizes, start_delta=max(delta, 8.0)))

    return used, gray, binary, finders, fits, invert, transform


def _error_rate(attempt) -> float:
    """Fraction of known cells the best grid of an attempt gets wrong. 1.0 if it found none."""
    fits = attempt[4]
    if not fits:
        return 1.0
    best = min(fits, key=lambda f: (f.wrong_known, -f.quality))
    return best.wrong_known / max(best.known_total, 1)


def _rescale_to_working_range(original, candidate, gray, binary, finders, invert=False, base=1.0):
    """Once the finders are found, redo the work at a resolution the preprocessing suits.

    The last element of the return value is the transform from working-image coordinates back
    to `original`'s: (offset_x, offset_y, factor), applied as original = working / factor +
    offset. Everything downstream measures on the working image, but everything shown to a
    person -- the finder rings on the photograph above all -- has to land on the pixels they
    are actually looking at.

    The pyramid above searches blindly, because before the finders are found there is no way to
    know how large a module is. Afterwards there is: a finder is seven modules wide. If that
    puts the module outside the band prepare() is built for, one more pass at the right scale
    is worth far more than any amount of parameter fiddling.

    Both directions matter, and the upward one is easy to talk yourself out of. Enlarging adds
    no information -- but it changes the ratio between the fixed 1.5 px blur and the module,
    and at five pixels per module that blur spans a third of a module and merges neighbours. On
    a Matter label photographed from a normal distance this step is the difference between four
    wrong known cells and none, between no result and the payload.
    """
    passthrough = (0.0, 0.0, base)
    if len(finders) < 3:
        return candidate, gray, binary, finders, passthrough

    widths = [w for _, _, w in select_finder_triple(finders) if w > 0]
    if not widths:
        return candidate, gray, binary, finders, passthrough
    module_px = (sum(widths) / len(widths)) / 7.0
    if GOOD_MODULE_PX[0] <= module_px <= GOOD_MODULE_PX[1]:
        return candidate, gray, binary, finders, passthrough

    # Crop to the code before rescaling. The finders say where it is, and enlarging a whole
    # photograph to reach the right module size is both slow and pointless -- on a label
    # photographed at arm's length the code is a fiftieth of the frame. Cropping first took
    # this path from 63 seconds to a few.
    ratio = original.shape[1] / candidate.shape[1]
    triple = select_finder_triple(finders)
    margin = 2.0 * max(w for _, _, w in triple)
    xs = [x for x, _, _ in triple]
    ys = [y for _, y, _ in triple]
    x0 = max(0, int((min(xs) - margin) * ratio))
    y0 = max(0, int((min(ys) - margin) * ratio))
    x1 = min(original.shape[1], int((max(xs) + margin) * ratio))
    y1 = min(original.shape[0], int((max(ys) + margin) * ratio))
    if x1 - x0 < 40 or y1 - y0 < 40:
        return candidate, gray, binary, finders, passthrough
    region = original[y0:y1, x0:x1]

    factor = TARGET_MODULE_PX / (module_px * ratio)
    if max(region.shape[:2]) * factor > MAX_DIMENSION:
        factor = MAX_DIMENSION / max(region.shape[:2])
    if not 0.05 < factor < 8.0:
        return candidate, gray, binary, finders, passthrough

    resized = cv2.resize(
        region,
        None,
        fx=factor,
        fy=factor,
        interpolation=cv2.INTER_CUBIC if factor > 1 else cv2.INTER_AREA,
    )
    retry_gray, retry_binary = prepare(resized, invert=invert)
    retry_finders = detect_finders(retry_binary)
    if len(retry_finders) < 3:
        return candidate, gray, binary, finders, passthrough
    return resized, retry_gray, retry_binary, retry_finders, (float(x0), float(y0), factor)


def snap_to_finders(binary: np.ndarray, points, radius: float = 60.0):
    """Treat hand-placed centres as hints and snap them onto real finder patterns.

    Nobody clicks a module centre to the pixel, and a few pixels of slack are enough to spoil
    the estimated module size and with it the version choice. So the click is not taken as a
    measurement. The detector is re-run with its size threshold lowered -- the reason the user
    is clicking at all is usually that a finder was found but discarded -- and each click is
    replaced by the nearest surviving candidate. A click with nothing near it is kept as is,
    which is still better than refusing to proceed.
    """
    candidates = find_finders(binary, min_size=8)
    snapped = []
    for x, y in points:
        near = [
            (abs(cx - x) + abs(cy - y), cx, cy, size)
            for cx, cy, size in candidates
            if abs(cx - x) < radius and abs(cy - y) < radius
        ]
        if near:
            _, cx, cy, size = min(near)
            snapped.append((cx, cy, size))
        else:
            snapped.append((float(x), float(y), 0.0))
    return snapped


def fit_grid(
    gray: np.ndarray, finders, sizes=DEFAULT_SIZES, start_delta: float = 3.0, on_step=None
) -> list[GridFit]:
    """Fit a grid for every candidate size and score it against the known cells.

    The version is deliberately not taken on faith from the finder width: with few pixels per
    module that estimate regularly lands between two candidates, and the difference between
    right and wrong is immediately visible in the known cells.
    """
    if len(finders) < 3:
        return []
    top_left, top_right, bottom_left = order_finders(select_finder_triple(finders))

    fits: list[GridFit] = []
    for modules in sizes:
        if not is_valid_size(modules):
            continue
        known_dark, known_light = structure_mask(modules)
        corners = initial_corners(top_left, top_right, bottom_left, modules)
        fits.append(
            refine_corners(
                gray,
                corners,
                modules,
                12,
                known_dark,
                known_light,
                start_delta=start_delta,
                on_step=on_step,
            )
        )
    return fits


def _decode_chain(
    mm: ModuleMatrix, budget: int, progress=None
) -> tuple[SearchResult, RepairResult | None]:
    """Turn a module matrix into text, cheapest route first.

    Ordered by cost: the direct attempt, then Reed-Solomon with erasures, and only last the
    combinatorial probe. The decoder computes the right values in one step where the search
    would have to try thousands of combinations.

    Shared by the single-image and the multi-image path on purpose. The two differ only in how
    the matrix was measured, and a second copy of this ladder is exactly how they would start
    giving different answers to the same evidence.
    """
    hard = mm.hard()
    text = decode_matrix(hard)
    if text:
        return SearchResult(text=text, candidates_tried=1, matrix=hard), None

    verify = lambda m: decode_matrix(m) is not None  # noqa: E731 - two words, used twice
    _emit(progress, "repair", method="ladder", step=0)
    repair_result = repair_progressive(
        hard,
        posterior=mm.posterior,
        verify=verify,
        on_step=lambda count: _emit(progress, "repair", method="ladder", step=count),
    )
    if repair_result.ok:
        text = decode_matrix(repair_result.matrix)
        if text:
            found = SearchResult(text=text, candidates_tried=2, matrix=repair_result.matrix)
            return found, repair_result

    # The prefix ladder above failed, so the damage does not sit at the bottom of the
    # reliability order. Scattered erasure sets reach the interleaved cases; see repair.py.
    scattered = repair_scattered(
        hard,
        mm.posterior,
        verify=verify,
        on_step=lambda tried: _emit(progress, "repair", method="scattered", step=tried),
    )
    if scattered.ok:
        text = decode_matrix(scattered.matrix)
        if text:
            return SearchResult(text=text, candidates_tried=3, matrix=scattered.matrix), scattered

    _emit(progress, "probe", tried=0, budget=budget)
    search = ordered_search(
        mm,
        budget=budget,
        on_step=lambda tried: _emit(progress, "probe", tried=tried, budget=budget),
    )
    return search, repair_result


def solve(
    bgr: np.ndarray,
    crop: tuple[int, int, int, int] | None = None,
    sizes=DEFAULT_SIZES,
    budget: int = 4000,
    band: float = 0.15,
    ensemble: str = "off",
    finder_points: list[tuple[float, float]] | None = None,
    invert: bool | None = None,
    progress=None,
) -> SolveResult:
    """Recover a QR code from a photograph. Never raises, always reports.

    `ensemble` selects what gets measured repeatedly:

    - ``"off"``       one measurement, one grid.
    - ``"sampling"``  one grid, several preprocessings. Demonstrably useless -- every member
                      shares the grid error. Details in ensemble.py.
    - ``"geometry"``  several independently fitted grids. More expensive, but the spread hits
                      the actual source of error.

    `finder_points` overrides the automatic finder search with three centre coordinates in any
    order. This is the escape hatch for photographs where the search fails -- a cluttered
    background, a finder eaten by a stain. Only the positions matter; the grid fit derives the
    module size from their spacing and refines from there, so clicking them roughly is enough.
    """
    if ensemble not in ENSEMBLE_MODES:
        raise ValueError(f"unknown ensemble mode: {ensemble!r}")
    crop_offset = (0.0, 0.0)
    if crop is not None:
        x0, y0, x1, y1 = crop
        bgr = bgr[y0:y1, x0:x1]
        crop_offset = (float(x0), float(y0))

    # Events from inside the attempt carry working-image coordinates already mapped back to
    # the (cropped) input; the crop offset is the one shift the attempt cannot know about.
    def shifted(event: str, data: dict) -> None:
        if crop_offset != (0.0, 0.0):
            for point in data.get("points", []):
                point["x"] += crop_offset[0]
                point["y"] += crop_offset[1]
            for corner in data.get("corners", []):
                corner[0] += crop_offset[0]
                corner[1] += crop_offset[1]
        _emit(progress, event, **data)

    _emit(progress, "image", width=int(bgr.shape[1]), height=int(bgr.shape[0]))
    attempt = _attempt(bgr, sizes, bool(invert), finder_points, progress=shifted)

    # The polarity cannot be settled at the finder stage, which is where a first version of
    # this tried to settle it. A finder pattern is nested squares, and its inverse is nested
    # squares too, so the detector finds it in either polarity, at the same place, and looks
    # equally convinced. What separates the two is what the cells then say: read at the wrong
    # polarity, a perfectly placed grid gets a fifth of the known cells wrong. So the decision
    # happens here, on the same evidence as the version and the scale.
    if invert is None and _error_rate(attempt) > 0.05:
        _emit(progress, "polarity", trying="inverted")
        flipped = _attempt(bgr, sizes, True, finder_points, progress=shifted)
        if _error_rate(flipped) < _error_rate(attempt):
            attempt = flipped

    bgr, gray, binary, finders, fits, inverted, transform = attempt

    # Everything internal measures on the working image; everything a person sees -- the
    # finder rings the page draws on the photograph above all -- has to land on the pixels
    # they are looking at. So the reported finders go back through the transform.
    ox, oy, factor = transform
    shown_finders = [
        (x / factor + ox + crop_offset[0], y / factor + oy + crop_offset[1], w / factor)
        for x, y, w in finders
    ]

    if len(finders) < 2:
        return SolveResult(
            text=None,
            finders=shown_finders,
            failure=f"only {len(finders)} finder candidates found",
        )
    if not fits:
        return SolveResult(text=None, finders=shown_finders, failure="no grid could be fitted")

    best = min(fits, key=lambda f: (f.wrong_known, -f.quality))
    known_dark, known_light = structure_mask(best.modules)

    # Only the winner earns the bow: on every candidate size it would multiply the search cost,
    # and a bow cannot rescue a wrong size anyway. Descent from zero offsets, so this never
    # returns a worse grid than the flat refinement produced. Measured in scripts/ab_bow.py.
    _emit(progress, "chosen", modules=int(best.modules), version=version_for_modules(best.modules))
    if BOW_REFINE:
        ox_, oy_, f_ = transform

        def on_bow(fit) -> None:
            shifted(
                "grid",
                {
                    "modules": int(fit.modules),
                    "wrong": int(fit.wrong_known),
                    "total": int(fit.known_total),
                    "quality": round(float(fit.quality), 4),
                    "phase": "bow",
                    "corners": [[c[0] / f_ + ox_, c[1] / f_ + oy_] for c in fit.corners.tolist()],
                },
            )

        best = refine_bow(gray, best, known_dark, known_light, on_step=on_bow)

    consensus: Consensus | None = None
    geometry: GeometryConsensus | None = None
    posterior = best.posterior

    if ensemble == "sampling":
        # Grid fixed, only the sampling varies. Demonstrably ineffective, see ensemble.py.
        consensus = consensus_posterior(
            bgr, best.corners, best.modules, 12, known_dark, known_light
        )
        posterior = consensus.posterior
    elif ensemble == "geometry":
        # Every member looks for its own grid. The version stays fixed, otherwise the members
        # would point at different cells and could not be merged.
        geometry = geometry_consensus(bgr, best.corners, best.modules, known_dark, known_light)
        if geometry is not None:
            posterior = geometry.posterior

    mm = ModuleMatrix(posterior=posterior, known_dark=known_dark, known_light=known_light)
    _emit(
        progress,
        "sampled",
        modules=int(best.modules),
        wrong_known=int(best.wrong_known),
        uncertain=int(len(mm.uncertain_cells(band))),
        posterior=[[round(float(p), 2) for p in row] for row in posterior.tolist()],
    )
    search, repair_result = _decode_chain(mm, budget, progress=progress)

    # Two separate error counts, because they measure two different things: wrong_known scores
    # the grid fit, wrong_sampled the sampling that the search actually ran on. Conflating them
    # makes a change to the sampling invisible.
    known = known_dark | known_light
    wrong_sampled = int(((posterior >= 0.5)[known] != known_dark[known]).sum())

    # The error correction level of the original, which the format information carries. Worth
    # reporting: someone reproducing a label wants the level it had, not the one an encoder
    # would pick.
    ecc = None
    if search.matrix is not None:
        header = read_format(search.matrix)
        if header is not None:
            ecc = header[0]

    return SolveResult(
        text=search.text,
        modules=best.modules,
        version=version_for_modules(best.modules),
        wrong_known=best.wrong_known,
        wrong_sampled=wrong_sampled,
        known_total=best.known_total,
        timing=timing_score(mm.hard()),
        uncertain=int(len(mm.uncertain_cells(band))),
        candidates_tried=search.candidates_tried,
        flipped=search.flipped,
        matrix=mm,
        decoded_matrix=search.matrix,
        finders=shown_finders,
        per_size=fits,
        consensus=consensus,
        geometry=geometry,
        repair=repair_result,
        inverted=inverted,
        ecc=ecc,
        failure=None if search.text else "no valid code in the searched space",
    )


# The probe budget each photograph gets on its own before the fusion is attempted. Deliberately
# small: an image that can be read by itself is read by the direct decode or by the erasure
# path, which cost one or two attempts. Deep probing per image spends the budget where the
# information is not -- the whole reason for taking a second photograph is that the first one
# does not contain enough.
MEMBER_BUDGET = 200


def solve_many(
    images: list[np.ndarray],
    crop: tuple[int, int, int, int] | None = None,
    sizes=DEFAULT_SIZES,
    budget: int = 4000,
    band: float = 0.15,
    rule: str = DEFAULT_FUSION,
    min_agreement: float = 0.75,
    member_budget: int = MEMBER_BUDGET,
    invert: bool | None = None,
    progress=None,
) -> SolveResult:
    """Recover one code from several photographs of it.

    The ensembles inside a single image cannot reach the error that dominates here, and
    ensemble.py records the measurement that says so: every member of those shares the one
    grid, so they reproduce its error with false confidence. Separate photographs are the
    variation that actually applies -- taken at a different angle, in different light, they get
    different cells wrong, and where they disagree the fused posterior lands near a half, which
    is precisely what the erasure path and the ordered probe want to be told.

    Any photograph that solves on its own wins immediately: it is the cheapest correct answer,
    and it needs no argument about how the fusion was formed.
    """
    if not images:
        return SolveResult(text=None, failure="no images given")
    if len(images) == 1:
        return solve(
            images[0], crop=crop, sizes=sizes, budget=budget, invert=invert, progress=progress
        )

    members = []
    for index, image in enumerate(images):
        _emit(progress, "member", index=index, total=len(images))

        def tagged(event: str, data: dict, _index=index) -> None:
            _emit(progress, event, member=_index, **data)

        member = solve(
            image, crop=crop, sizes=sizes, budget=member_budget, invert=invert, progress=tagged
        )
        members.append(member)
        if member.solved:
            return member

    usable = [m for m in members if m.matrix is not None]
    if not usable:
        return SolveResult(
            text=None,
            finders=members[0].finders,
            failure="no image produced a grid to fuse",
        )

    # Best grid first: it becomes the reference every other photograph is checked against, and
    # its geometry is what gets reported. A poor reference would reject its better companions.
    # Photographs whose grid came out a different size are handed over as they are -- the
    # fusion rejects them itself and *records* it. An earlier version filtered them out here,
    # and the page then reported "1 photograph fused" to someone who had just given it two,
    # with no word about where the other one went.
    usable.sort(key=lambda m: (m.wrong_known, -m.timing))
    best = usable[0]

    known_dark, known_light = structure_mask(best.modules)
    consensus = fuse_images(
        [m.matrix.posterior for m in usable],
        known_dark,
        known_light,
        rule=rule,
        min_agreement=min_agreement,
    )

    _emit(
        progress,
        "fusion",
        members=consensus.members,
        agreement=[round(a, 4) for a in consensus.agreement],
        disagreeing=consensus.disagreeing,
        rejected=list(consensus.rejected),
    )
    mm = ModuleMatrix(consensus.posterior, known_dark, known_light)
    search, repair_result = _decode_chain(mm, budget, progress=progress)

    known = known_dark | known_light
    wrong_sampled = int(((consensus.posterior >= 0.5)[known] != known_dark[known]).sum())

    ecc = None
    if search.matrix is not None:
        header = read_format(search.matrix)
        if header is not None:
            ecc = header[0]

    dropped = len(images) - consensus.members
    return SolveResult(
        text=search.text,
        modules=best.modules,
        version=best.version,
        wrong_known=best.wrong_known,
        wrong_sampled=wrong_sampled,
        known_total=best.known_total,
        timing=timing_score(mm.hard()),
        uncertain=int(len(mm.uncertain_cells(band))),
        candidates_tried=search.candidates_tried,
        flipped=search.flipped,
        matrix=mm,
        decoded_matrix=search.matrix,
        finders=best.finders,
        per_size=best.per_size,
        repair=repair_result,
        inverted=best.inverted,
        ecc=ecc,
        fusion=consensus,
        failure=None
        if search.text
        else f"no valid code in the searched space, fusing {consensus.members} of {len(images)}"
        + (f" ({dropped} did not match)" if dropped else ""),
    )
