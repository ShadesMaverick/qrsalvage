"""The whole path from photograph to plain text, without output and without file access.

This layer decides nothing on its own, it composes: preprocess, find the grid, try the versions,
sample, decode, probe if needed. All reporting is the caller's business -- the core stays free
of anything but library code.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

import cv2
import numpy as np

from . import oracle
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
    CurvedOutline,
    GridFit,
    find_finders,
    finder_triple_score,
    fit_outline,
    initial_corners,
    order_finders,
    outline_midpoints,
    refine_bow,
    refine_corners,
    restart_coarse,
    select_finder_triple,
    third_finder_candidates,
)
from .layout import codeword_positions, read_format, read_format_consensus, read_format_copies
from .matrix import ModuleMatrix
from .policy import attempt_error_rate, choose_grid, fusion_rank, should_restart
from .preprocess import prepare
from .qrspec import block_plan
from .repair import RepairResult, repair_progressive, repair_scattered
from .sampling import BURIED_DEPTH, buried_cells, featureless_depth
from .scanfinder import find_finders_scan, merge_finders
from .structure import is_valid_size, structure_mask, timing_score, version_for_modules

DEFAULT_SIZES = (21, 25, 29, 33, 37, 41)
ENSEMBLE_MODES = ("off", "sampling", "geometry")

# Whether the winning grid gets the bowed refinement on top of the flat one. Measured in
# scripts/ab_bow.py: neutral on the synthetic cylinder, which the corner fit already absorbs,
# and decisive on a real fabric photograph that nothing else could solve. Details at
# geometry.refine_bow.
BOW_REFINE = True

# A grid that fitted this badly is not a hard image, it is a misplaced grid: the skill's own
# reading of the diagnostics puts a healthy fit under 1 percent of known cells wrong and calls
# anything past 5 percent a geometry problem. Past it, the winning grid gets one more descent
# from a coarse step, which is the only thing that reaches a false optimum a module away.
# Never returns a worse grid; measurement and the failure that motivated it at
# geometry.restart_coarse.
COARSE_RESTART = True
COARSE_RESTART_THRESHOLD = 0.05

# Whether cells inside single-colour patches reach the decoder damped by their featureless
# depth instead of as confident readings. The counting argument and the depth live at
# sampling.featureless_depth.
#
# MEASURED RESULT (scripts/ab_worn.py, 16 images per level and arm, budget 4000). The worn
# axis erases the bottom rows of the print whole, and without this the axis is simply dead:
# 0/16 at every level from 0.09 up, because every erased cell reaches Reed-Solomon as a
# confident light module. Damped, the same levels read 9/16, 9/16, 10/16 and 4/16 (worn 0.09
# to 0.18), the two control levels stay 16/16 in both arms, and neither arm produced a single
# wrong text -- the count that matters most, since a repair fed wrong erasure positions can
# manufacture presentable garbage. The stain axis profits as a side effect: a stain is a
# featureless patch too, and with this and the per-edge bow together every fusion hard case
# at stain 0.55 now reads from a single photograph (see tests/test_fusion.py).
BLANK_FEATURELESS = True

# Past this triple score the third best "finder" is likelier an artefact than a finder, and
# the two credible ones additionally go down the pair path, competing on the same terms.
# Calibration: clean synthetic and photographed triples score below 0.3 (width agreement and
# right angle), while a triple completed by an artefact -- observed with a worn-off bottom
# edge whose broken outline came back as one giant contour -- lands past 1.2, carried by the
# width term alone. The doubt is cheap where it is wrong: the six extra pair fits only run
# when the score is bad, and the known cells still decide between every candidate fitted.
TRIPLE_DOUBT = 0.5

# The anchor sweep: when a grid hangs on two finders and a constructed third, the side away
# from the pair has no witness, and the failure that proves it is exact. On a photograph with
# a worn-off bottom edge, two grids read all 220 visible structure cells -- timing, both
# finders, the full alignment pattern -- without a single error, and still assigned 197 data
# cells differently; their bottom-right corners sat 24 px apart, the gap bent back out of the
# witnesses' sight by perspective and the per-edge bow. No objective built on the cells the
# standard fixes can rank such grids, because they are all silent in exactly the region that
# differs. Each constructed-third scale is its own descent basin (the descent cannot cross
# between them; reaching the solving grid took a hand-built start at 1.06), so on failure the
# basins are enumerated: refit at each scale along the winning direction, and let the decoder
# -- the one witness with something to say -- judge each basin through the cheap half of the
# decode chain. Bad scales stay cheap to reject: they tear the alignment pattern and the
# timing off their cells, and the known-cell count discards them before any decoding.
#
# MEASURED RESULT (scripts/ab_anchor.py, 16 images per level and arm, budget 4000, with the
# witness judge below in place). On the worn axis, whose erased bottom rows manufacture
# exactly this geometry: 9/16 -> 11/16 at worn 0.09 and at 0.12, 10/16 -> 10/16 at 0.15,
# 4/16 -> 10/16 at 0.18; the control level stays 16/16 in both arms, and neither arm
# produced a single wrong text. Ten recoveries across the axis, each one a photograph whose
# only obstacle was that the right-angle construction had picked the wrong basin. The cost
# lands on failures alone -- a solved image never enters the sweep.
ANCHOR_SWEEP = True
ANCHOR_SCALES = (0.94, 0.97, 1.03, 1.06)

# The sweep's second judge, and it fires only on the repairs nothing else vouches for. A
# repair that spent *every* check symbol as an erasure has confirmed nothing -- repair.py
# states it plainly: with as many erasures as check symbols Reed-Solomon always finds a valid
# solution -- and the outside verify only catches structural nonsense. Such a repair may
# still be right, on heavy damage it is even the only possible right answer; what it may not
# do is overrule witnesses. Past this confidence a cell counts as one, and an unconfirmed
# repair that flips even a single witness is rejected however cleanly it decodes: the true
# full-freedom repair only writes into blank cells, the invented one recomputes whole
# codewords and contradicts confidently-read cells somewhere along the way.
#
# Both simpler judges were measured first and rejected. A flat cap below the ladder's top
# rung removed the two wrong texts of the first measurement and with them every genuine
# recovery at worn 0.18 (9/16 back to 4/16) -- on heavy damage the true repair needs the
# full ladder too. Applying the witness check to every repair removed the wrong texts and
# the genuine recoveries at worn 0.09 and 0.12 instead -- error *correction* overrules
# witnesses by definition, and a repair with check symbols left over has been vouched for by
# exactly those symbols. Confirmed repairs pass unquestioned; only total freedom is audited.
#
# Measured, this judge does more than block the two inventions: rejecting them lets the
# sweep keep searching, and on one seed the very case that had produced byte garbage went on
# to decode correctly from a later basin. The final tally is at ANCHOR_SWEEP above.
ANCHOR_WITNESS_CONFIDENCE = 0.35
# A bit this close to 0.5 is effectively absent from the photograph. The cutoff is deliberately
# narrow: it recognizes exact featureless damping and numerical residue around it, not ordinary
# low contrast. The release panel exposed the distinction: valid wrong payloads had seven to ten
# such codewords under seven L-level checks; the worn cases correctly recovered at the decoding
# boundary had none.
REPAIR_UNKNOWN_CONFIDENCE = 0.02


def matrix_has_sufficient_evidence(
    mm: ModuleMatrix,
    ecc: str,
    format_distance: int | None = None,
    *,
    require_exact_format: bool = False,
) -> bool:
    """Reject a decoded payload when the photograph leaves too many codewords unknown.

    Reed-Solomon can only identify a unique answer when the count of effectively erased
    codewords does not exceed its check symbols. A featureless patch can leave more complete
    codewords absent than the chosen decoder route acknowledges. Accepting any valid matrix in
    that state -- direct, repaired, or found by probing -- would report one arbitrary member of
    many possible payloads.
    """
    if not ecc:
        return False
    # The format field chooses ECC and mask before the payload is even read. A corrected format
    # header plus a repaired payload lets two uncertain layers certify each other; require the
    # redundant header copies to agree exactly before returning repaired text.
    if require_exact_format and format_distance not in (None, 0):
        return False
    try:
        version = version_for_modules(mm.modules)
        plan = block_plan(version, ecc)
        positions = codeword_positions(mm.modules, version, ecc)
    except KeyError:
        return False
    flat = mm.posterior.ravel()
    for block_positions in positions:
        unknown = sum(
            min(abs(float(flat[position]) - 0.5) for position in word) < REPAIR_UNKNOWN_CONFIDENCE
            for word in block_positions
        )
        if unknown > plan.ec_per_block:
            return False
    return True


def repair_has_sufficient_evidence(mm: ModuleMatrix, repair: RepairResult) -> bool:
    """Apply the shared payload-evidence contract to one Reed-Solomon result."""
    if repair.matrix is None or not repair.ecc or repair.blocks < 1:
        return False
    observed = _repair_format(mm.hard())
    if observed is None or (observed[0], observed[1]) != (repair.ecc, repair.mask):
        return False
    return matrix_has_sufficient_evidence(
        mm, repair.ecc, repair.format_distance, require_exact_format=True
    )


def _unambiguous_format(matrix: np.ndarray) -> tuple[str, int, int] | None:
    """Read one ECC/mask choice only when all readable format copies agree."""
    return read_format_consensus(matrix)


def _repair_format(matrix: np.ndarray) -> tuple[str, int, int] | None:
    """Require two agreeing readable copies and one exact witness for payload repair."""
    copies = read_format_copies(matrix)
    if len(copies) != 2 or any(candidate is None for candidate in copies):
        return None
    candidates = [candidate for candidate in copies if candidate is not None]
    layouts = {(ecc, mask) for ecc, mask, _distance in candidates}
    if len(layouts) != 1 or not any(distance == 0 for _ecc, _mask, distance in candidates):
        return None
    return min(candidates, key=lambda candidate: candidate[2])


def _observed_format(mm: ModuleMatrix) -> tuple[str, int, int] | None:
    """Read unambiguous format evidence from the measured hard matrix."""
    return _unambiguous_format(mm.hard())


# The progress callback a shell injects: (event name, JSON-ready payload). See _emit.
ProgressFn = Callable[[str, dict], None]


def _emit(progress: ProgressFn | None, event: str, **data: object) -> None:
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
    blanked: int = 0
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
    source: str = "recovery"

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

# One prepared working image: (image actually used, gray, binary, finder candidates, transform
# back to the original's coordinates as (offset_x, offset_y, factor)).
_Prepared = tuple[
    np.ndarray,
    np.ndarray,
    np.ndarray,
    list[tuple[float, float, float]],
    tuple[float, float, float],
]

# One row of the scale pyramid in _search_scales: (pyramid index, finder width spread, finder
# count, scale used, image at that scale, gray, binary, finder candidates).
_ScaleAttempt = tuple[
    int,
    float,
    int,
    float,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    list[tuple[float, float, float]],
]

# One complete pass at one polarity: a _Prepared plus the fitted grids, the polarity used,
# and -- when the grids hang on a constructed third finder -- the pair they hang on. The pair
# is what the anchor sweep needs later: it marks the geometry as one with an unwitnessed side.
_Attempt = tuple[
    np.ndarray,
    np.ndarray,
    np.ndarray,
    list[tuple[float, float, float]],
    list[GridFit],
    bool,
    tuple[float, float, float],
    "list[tuple[float, float, float]] | None",
]


def detect_finders(binary: np.ndarray) -> list[tuple[float, float, float]]:
    """Both detectors, merged.

    They fail on different things, which is the whole reason for keeping both. The contour
    detector wants three intact nested rings and gives a precise centre when it gets them; the
    scan detector only wants the 1:1:3:1:1 proportions to survive along enough lines, which
    they do through creases, grit and eroded edges. Contours go first so their precision wins
    wherever both saw the same pattern.
    """
    return merge_finders(find_finders(binary), find_finders_scan(binary))


def _search_scales(
    bgr: np.ndarray, scales: tuple[float, ...] = SCALES, invert: bool = False
) -> _Prepared:
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
    attempts: list[_ScaleAttempt] = []
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
    def rank(attempt: _ScaleAttempt) -> tuple[bool, float, int]:
        index, spread, count, *_ = attempt
        return (count < 3, round(spread, 2), index)

    _, _, _, used_scale, candidate, gray, binary, finders = min(attempts, key=rank)
    return _rescale_to_working_range(bgr, candidate, gray, binary, finders, invert, used_scale)


def _prepare_with_hints(
    bgr: np.ndarray, points: list[tuple[float, float]], invert: bool
) -> _Prepared:
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
    if len(pts) == 2:
        # A marked pair instead of a triple: the third finder is destroyed or outside the
        # frame, which is exactly when marking it is impossible. The two centres still say how
        # large the code is -- assuming they are adjacent, which the diagonal pair breaks by a
        # factor of root two. That lands the rescale at eight instead of eleven pixels per
        # module, still inside the band prepare() is built for, so the ambiguity is tolerable
        # rather than resolved.
        span = float(np.linalg.norm(pts[0] - pts[1]))
    else:
        sides = sorted(float(np.linalg.norm(pts[i] - pts[j])) for i, j in ((0, 1), (0, 2), (1, 2)))
        span = (sides[0] + sides[1]) / 2.0
    module_px = span / 22.0  # the middle of DEFAULT_SIZES, minus the 7 finder modules

    if span < 1.0 or GOOD_MODULE_PX[0] <= module_px <= GOOD_MODULE_PX[1]:
        gray, binary = prepare(bgr, invert=invert)
        return bgr, gray, binary, snap_to_finders(binary, points), (0.0, 0.0, 1.0)

    # Crop to the marked code first. The clicks bound it, and preparing twelve megapixels in
    # order to use one is what made this path minutes-slow. The margin covers the code's
    # reach past the finder centres plus the quiet zone, at the smallest version (0.55 spans).
    # A pair leaves one whole side of the code outside its bounding box -- the third corner
    # sits a full span away, on whichever side, so the margin has to cover that too.
    margin = 0.6 * span if len(pts) >= 3 else 1.25 * span
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


def _prepare_with_outline(
    bgr: np.ndarray, outline: CurvedOutline, invert: bool
) -> tuple[np.ndarray, np.ndarray, np.ndarray, CurvedOutline, tuple[float, float, float]]:
    """Crop and scale the eight manual handles into preprocessing's working range."""
    sides = [
        float(np.linalg.norm(outline.corners[(index + 1) % 4] - outline.corners[index]))
        for index in range(4)
    ]
    side = float(np.mean(sides))
    middle_size = DEFAULT_SIZES[(len(DEFAULT_SIZES) - 1) // 2]
    module_px = side / middle_size
    handles = np.vstack((outline.corners, outline.edge_midpoints))
    if side < 1.0:
        gray, binary = prepare(bgr, invert=invert)
        return bgr, gray, binary, outline, (0.0, 0.0, 1.0)
    margin = 0.15 * side
    x0 = max(0, int(np.floor(handles[:, 0].min() - margin)))
    y0 = max(0, int(np.floor(handles[:, 1].min() - margin)))
    x1 = min(bgr.shape[1], int(np.ceil(handles[:, 0].max() + margin)))
    y1 = min(bgr.shape[0], int(np.ceil(handles[:, 1].max() + margin)))
    if x1 <= x0 or y1 <= y0:
        gray, binary = prepare(bgr, invert=invert)
        return bgr, gray, binary, outline, (0.0, 0.0, 1.0)
    region = bgr[y0:y1, x0:x1]

    factor = 1.0
    if module_px > 0.0 and not GOOD_MODULE_PX[0] <= module_px <= GOOD_MODULE_PX[1]:
        factor = TARGET_MODULE_PX / module_px
    if max(region.shape[:2]) * factor > MAX_DIMENSION:
        factor = MAX_DIMENSION / max(region.shape[:2])
    if factor == 1.0:
        work = region
    else:
        target_size: tuple[int, int] | None = None
        if min(region.shape[:2]) * factor < 1.0:
            # OpenCV derives dsize from fx/fy by rounding. An extreme but contract-valid
            # aspect ratio can therefore turn the short side into zero and raise instead of
            # reporting an ordinary recovery failure. Such an image cannot contain a useful
            # two-dimensional grid, but keeping one pixel lets the normal failure path judge it.
            target_size = (
                max(1, round(region.shape[1] * factor)),
                max(1, round(region.shape[0] * factor)),
            )
        work = cv2.resize(
            region,
            target_size,
            fx=factor,
            fy=factor,
            interpolation=cv2.INTER_AREA if factor < 1.0 else cv2.INTER_CUBIC,
        )
    gray, binary = prepare(work, invert=invert)

    def transform(points: np.ndarray) -> np.ndarray:
        return (np.asarray(points, dtype=np.float64) - np.array([x0, y0])) * factor

    prepared = CurvedOutline(
        corners=transform(outline.corners),
        edge_midpoints=transform(outline.edge_midpoints),
    )
    return work, gray, binary, prepared, (float(x0), float(y0), factor)


def _attempt(
    bgr: np.ndarray,
    sizes: Sequence[int],
    invert: bool,
    finder_points: list[tuple[float, float]] | None,
    outline: CurvedOutline | None = None,
    progress: ProgressFn | None = None,
) -> _Attempt:
    """One complete pass at one polarity: find the code, then fit every candidate grid."""
    prepared_outline: CurvedOutline | None = None
    if outline is not None:
        used, gray, binary, prepared_outline, transform = _prepare_with_outline(
            bgr, outline, invert
        )
        finders: list[tuple[float, float, float]] = []
    elif finder_points is not None:
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

    def on_fit(fit: GridFit) -> None:
        corners = fit.corners[[0, 1, 3, 2]]
        midpoints = outline_midpoints(fit.corners, fit.bow)
        _emit(
            progress,
            "grid",
            modules=int(fit.modules),
            wrong=int(fit.wrong_known),
            total=int(fit.known_total),
            quality=round(float(fit.quality), 4),
            corners=[[c[0] / factor + ox, c[1] / factor + oy] for c in corners.tolist()],
            edge_midpoints=[
                [point[0] / factor + ox, point[1] / factor + oy] for point in midpoints.tolist()
            ],
        )

    # Hand-placed centres are only ever approximate -- nobody clicks a module centre to the
    # pixel. The refinement therefore starts with a much coarser step so it can walk back a
    # misplaced click; with the automatic centres a fine step converges faster and better.
    delta = 12.0 if finder_points else 3.0

    def pair_fits(pair: list[tuple[float, float, float]]) -> list[GridFit]:
        """Every geometric reading of two finders, fitted; the known cells decide.

        Constructed thirds outside the image are skipped for automatic pairs only: those are
        unvetted, and a far-out third fits a garbage grid onto border pixels. A hand-marked
        pair is the opposite case -- the person marked two centres precisely because the third
        is destroyed or beyond the frame -- so for them every reading is fitted.
        """
        found: list[GridFit] = []
        for third in third_finder_candidates(pair[0], pair[1]):
            in_frame = 0 <= third[0] < gray.shape[1] and 0 <= third[1] < gray.shape[0]
            if finder_points is None and not in_frame:
                continue
            # The constructed third is a right-angle guess that ignores perspective, so it
            # starts further out than any hand-placed click -- it gets the same coarse first
            # step the clicks get, measured to matter on a photograph whose skew put the true
            # corner a dozen pixels from the construction.
            found.extend(fit_grid(gray, [*pair, third], sizes, start_delta=max(delta, 12.0)))
        return found

    fits: list[GridFit] = []
    anchor_pair: list[tuple[float, float, float]] | None = None
    if prepared_outline is not None:
        fits = fit_outline(gray, prepared_outline, sizes, start_delta=12.0, on_step=on_fit)
    elif len(finders) >= 3:
        triple = select_finder_triple(finders)
        fits = fit_grid(gray, triple, sizes, start_delta=delta, on_step=on_fit)
        if finder_triple_score(triple) > TRIPLE_DOUBT:
            # The best triple available still does not look like three finders -- one of them
            # is probably an artefact standing in for a finder the damage took. The two that
            # agree on their width go down the pair path as well, and the known cells decide
            # between everything fitted, exactly as they decide everything else.
            anchor_pair = min(
                ([a, b] for i, a in enumerate(finders[:10]) for b in finders[i + 1 : 10]),
                key=lambda p: abs(p[0][2] - p[1][2]) / max(p[0][2], p[1][2], 1e-6),
            )
            fits.extend(pair_fits(anchor_pair))
    elif len(finders) == 2:
        # One finder may be worn away entirely, or merely faded enough that neither detector
        # recognises it -- both happen on real damage. The geometry is still determined up to
        # six discrete choices, so all of them are fitted and the known cells decide. This path
        # costs six times a normal fit, which is why it is a fallback.
        anchor_pair = list(finders[:2])
        fits = pair_fits(anchor_pair)

    return used, gray, binary, finders, fits, invert, transform, anchor_pair


def _error_rate(attempt: _Attempt) -> float:
    """Fraction of known cells the best grid of an attempt gets wrong. 1.0 if it found none."""
    return attempt_error_rate(attempt[4])


def _rescale_to_working_range(
    original: np.ndarray,
    candidate: np.ndarray,
    gray: np.ndarray,
    binary: np.ndarray,
    finders: list[tuple[float, float, float]],
    invert: bool = False,
    base: float = 1.0,
) -> _Prepared:
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


def snap_to_finders(
    binary: np.ndarray, points: list[tuple[float, float]], radius: float = 60.0
) -> list[tuple[float, float, float]]:
    """Treat hand-placed centres as hints and snap them onto real finder patterns.

    Nobody clicks a module centre to the pixel, and a few pixels of slack are enough to spoil
    the estimated module size and with it the version choice. So the click is not taken as a
    measurement. The detector is re-run with its size threshold lowered -- the reason the user
    is clicking at all is usually that a finder was found but discarded -- and each click is
    replaced by the nearest surviving candidate. A click with nothing near it is kept as is,
    which is still better than refusing to proceed.
    """
    candidates = find_finders(binary, min_size=8)
    snapped: list[tuple[float, float, float]] = []
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
    gray: np.ndarray,
    finders: list[tuple[float, float, float]],
    sizes: Sequence[int] = DEFAULT_SIZES,
    start_delta: float = 3.0,
    on_step: Callable[[GridFit], None] | None = None,
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


def _damp_featureless(
    posterior: np.ndarray, known_dark: np.ndarray, known_light: np.ndarray
) -> tuple[np.ndarray, int]:
    """Damp featureless ground towards unknown; returns (posterior, buried cell count).

    One function for every path that builds a matrix for the decoder -- single image, fusion,
    anchor sweep -- because the decoder's contract is the same on all of them: what it sees
    has been through the test. The reasoning lives at sampling.featureless_depth and at the
    BLANK_FEATURELESS constant above.
    """
    if not BLANK_FEATURELESS:
        return posterior, 0
    known = known_dark | known_light
    depth = featureless_depth(posterior, known)
    buried = buried_cells(depth) & ~known
    blanked = int(buried.sum())
    if depth.any():
        damp = np.where(buried, 0.0, np.clip(1.0 - depth / BURIED_DEPTH, 0.0, 1.0))
        posterior = np.where(~known, 0.5 + (posterior - 0.5) * damp, posterior)
    return posterior, blanked


def _decode_chain(
    mm: ModuleMatrix, budget: int, progress: ProgressFn | None = None, probe: bool = True
) -> tuple[SearchResult, RepairResult | None]:
    """Turn a module matrix into text, cheapest route first.

    Ordered by cost: the direct attempt, then Reed-Solomon with erasures, and only last the
    combinatorial probe. The decoder computes the right values in one step where the search
    would have to try thousands of combinations.

    Shared by the single-image and the multi-image path on purpose. The two differ only in how
    the matrix was measured, and a second copy of this ladder is exactly how they would start
    giving different answers to the same evidence. The anchor sweep runs this same chain with
    `probe` off -- it judges many candidate geometries, and per candidate the combinatorial
    probe costs more than it could tell; the sweep then adds its own witness check on top
    (ANCHOR_WITNESS_CONFIDENCE) before adopting what this chain returns.
    """
    hard = mm.hard()
    header = _observed_format(mm)
    text = decode_matrix(hard)
    if text and header is not None and matrix_has_sufficient_evidence(mm, header[0]):
        return SearchResult(text=text, candidates_tried=1, matrix=hard), None

    verify = lambda m: decode_matrix(m) is not None  # noqa: E731 - two words, used twice
    _emit(progress, "repair", method="ladder", step=0)
    repair_result = repair_progressive(
        hard,
        posterior=mm.posterior,
        verify=verify,
        on_step=lambda count: _emit(progress, "repair", method="ladder", step=count),
    )
    if repair_result.ok and repair_has_sufficient_evidence(mm, repair_result):
        assert repair_result.matrix is not None  # ok is defined as exactly this
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
    if scattered.ok and repair_has_sufficient_evidence(mm, scattered):
        assert scattered.matrix is not None  # ok is defined as exactly this
        text = decode_matrix(scattered.matrix)
        if text:
            return SearchResult(text=text, candidates_tried=3, matrix=scattered.matrix), scattered

    if not probe:
        return SearchResult(text=None, candidates_tried=3), repair_result

    _emit(progress, "probe", tried=0, budget=budget)
    search = ordered_search(
        mm,
        budget=budget,
        on_step=lambda tried: _emit(progress, "probe", tried=tried, budget=budget),
    )
    if search.text is not None:
        candidate_header = None if search.matrix is None else _unambiguous_format(search.matrix)
        if candidate_header is None or not matrix_has_sufficient_evidence(mm, candidate_header[0]):
            return SearchResult(text=None, candidates_tried=search.candidates_tried), repair_result
    return search, repair_result


def solve(
    bgr: np.ndarray,
    crop: tuple[int, int, int, int] | None = None,
    sizes: Sequence[int] = DEFAULT_SIZES,
    budget: int = 4000,
    band: float = 0.15,
    ensemble: str = "off",
    finder_points: list[tuple[float, float]] | None = None,
    outline: CurvedOutline | None = None,
    invert: bool | None = None,
    progress: ProgressFn | None = None,
) -> SolveResult:
    """Recover a QR code from a photograph. Never raises, always reports.

    `ensemble` selects what gets measured repeatedly:

    - ``"off"``       one measurement, one grid.
    - ``"sampling"``  one grid, several preprocessings. Demonstrably useless -- every member
                      shares the grid error. Details in ensemble.py.
    - ``"geometry"``  several independently fitted grids. More expensive, but the spread hits
                      the actual source of error.

    `finder_points` overrides the automatic finder search with two or three centre coordinates
    in any order. This is the escape hatch for photographs where the search fails -- a
    cluttered background, a finder eaten by a stain. Only the positions matter; the grid fit
    derives the module size from their spacing and refines from there, so clicking them
    roughly is enough. Two points mean the third finder cannot be marked at all -- destroyed,
    or outside the frame -- and every geometric reading of the pair is fitted instead.

    `outline` supplies four clockwise corners and the top, right, bottom and left edge
    midpoints. It bypasses finder detection and seeds the existing per-edge bow model.
    """
    if ensemble not in ENSEMBLE_MODES:
        raise ValueError(f"unknown ensemble mode: {ensemble!r}")
    crop_offset = (0.0, 0.0)
    if crop is not None:
        x0, y0, x1, y1 = crop
        bgr = bgr[y0:y1, x0:x1]
        crop_offset = (float(x0), float(y0))
        if finder_points is not None:
            # Hand-marked centres live in the coordinates of the image the caller gave --
            # the same frame every reported finder is mapped back into. The crop is an
            # internal narrowing and must not change what the numbers mean.
            finder_points = [(x - x0, y - y0) for x, y in finder_points]
        if outline is not None:
            offset = np.array([x0, y0], dtype=np.float64)
            outline = CurvedOutline(
                corners=outline.corners - offset,
                edge_midpoints=outline.edge_midpoints - offset,
            )

    # Ask the installed outside decoder about the photograph before imposing qrsalvage's
    # stricter grid model on it. ZXing can read some valid codes with extreme non-square pixel
    # scaling even though our finder geometry cannot construct a trustworthy square grid. The
    # oracle returns only checksum-valid QR payloads; failed attempts still fall through to the
    # recovery pipeline, where uncertainty and erasures do the work ordinary readers cannot.
    if finder_points is None and outline is None:
        gray_photo = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        direct_text = oracle.decode(gray_photo)
        if direct_text:
            _emit(progress, "image", width=int(bgr.shape[1]), height=int(bgr.shape[0]))
            _emit(progress, "direct", source="whole photograph")
            return SolveResult(
                text=direct_text,
                candidates_tried=1,
                failure=None,
                source="direct",
            )

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
            for midpoint in data.get("edge_midpoints", []):
                midpoint[0] += crop_offset[0]
                midpoint[1] += crop_offset[1]
        _emit(progress, event, **data)

    _emit(progress, "image", width=int(bgr.shape[1]), height=int(bgr.shape[0]))
    attempt = _attempt(bgr, sizes, bool(invert), finder_points, outline, progress=shifted)

    # The polarity cannot be settled at the finder stage, which is where a first version of
    # this tried to settle it. A finder pattern is nested squares, and its inverse is nested
    # squares too, so the detector finds it in either polarity, at the same place, and looks
    # equally convinced. What separates the two is what the cells then say: read at the wrong
    # polarity, a perfectly placed grid gets a fifth of the known cells wrong. So the decision
    # happens here, on the same evidence as the version and the scale.
    if invert is None and _error_rate(attempt) > 0.05:
        _emit(progress, "polarity", trying="inverted")
        flipped = _attempt(bgr, sizes, True, finder_points, outline, progress=shifted)
        if _error_rate(flipped) < _error_rate(attempt):
            attempt = flipped

    bgr, gray, binary, finders, fits, inverted, transform, anchor_pair = attempt

    # Everything internal measures on the working image; everything a person sees -- the
    # finder rings the page draws on the photograph above all -- has to land on the pixels
    # they are looking at. So the reported finders go back through the transform.
    ox, oy, factor = transform
    shown_finders = [
        (x / factor + ox + crop_offset[0], y / factor + oy + crop_offset[1], w / factor)
        for x, y, w in finders
    ]

    if outline is None and len(finders) < 2:
        return SolveResult(
            text=None,
            finders=shown_finders,
            failure=f"only {len(finders)} finder candidates found",
        )
    if not fits:
        return SolveResult(text=None, finders=shown_finders, failure="no grid could be fitted")

    best = choose_grid(fits)
    known_dark, known_light = structure_mask(best.modules)

    # Only the winner earns the bow: on every candidate size it would multiply the search cost,
    # and a bow cannot rescue a wrong size anyway. Automatic geometry descends from zero bow;
    # a manual outline descends from its supplied curves. Either seed is retained unless the
    # objective improves, so refinement never returns a worse grid. Measured in scripts/ab_bow.py.
    _emit(progress, "chosen", modules=int(best.modules), version=version_for_modules(best.modules))
    ox_, oy_, f_ = transform

    def grid_event(phase: str) -> Callable[[GridFit], None]:
        def report(fit: GridFit) -> None:
            corners = fit.corners[[0, 1, 3, 2]]
            midpoints = outline_midpoints(fit.corners, fit.bow)
            shifted(
                "grid",
                {
                    "modules": int(fit.modules),
                    "wrong": int(fit.wrong_known),
                    "total": int(fit.known_total),
                    "quality": round(float(fit.quality), 4),
                    "phase": phase,
                    "corners": [[c[0] / f_ + ox_, c[1] / f_ + oy_] for c in corners.tolist()],
                    "edge_midpoints": [
                        [point[0] / f_ + ox_, point[1] / f_ + oy_] for point in midpoints.tolist()
                    ],
                },
            )

        return report

    # Before the bow, because a bow fitted onto a misplaced grid is a bow spent bending the
    # wrong thing -- and because the restart is what decides whether the grid is placed at all.
    if outline is None and COARSE_RESTART and should_restart(best, COARSE_RESTART_THRESHOLD):
        best = restart_coarse(gray, best, known_dark, known_light, on_step=grid_event("restart"))
    if BOW_REFINE:
        best = refine_bow(gray, best, known_dark, known_light, on_step=grid_event("bow"))

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

    # Single-colour patches carry no data whatever the pixels say. Cells buried in one reach
    # the decoder as exact unknowns -- that hard half is what guarantees their codewords rank
    # below every merely-shaky cell the photograph has anyway, so the erasure ladder spends
    # its first erasures inside the damage. The rim a patch brushes is damped in proportion,
    # which keeps it ahead of healthy cells and behind the core: the ladder reaches it only
    # with whatever budget the core left over. After the ensembles, so a fused posterior is
    # judged as fused; before the events, so a watcher sees what the decoder sees.
    posterior, blanked = _damp_featureless(posterior, known_dark, known_light)

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

    if search.text is None and outline is None and ANCHOR_SWEEP and anchor_pair is not None:
        # Enumerate the descent basins the constructed third could not choose between -- see
        # the note at ANCHOR_SWEEP. Only the winning direction is swept: the selection picked
        # the right reading of the pair, it is the reading's *scale* no witness could settle.
        m = float(best.modules)
        destination = np.array([[0, 0], [m, 0], [0, m], [m, m]], dtype=np.float32)
        homography = cv2.getPerspectiveTransform(
            destination, np.asarray(best.corners, dtype=np.float32)
        )

        def module_point(col: float, row: float) -> np.ndarray:
            v = homography @ np.array([col, row, 1.0])
            return v[:2] / v[2]

        centres = [module_point(3.5, 3.5), module_point(m - 3.5, 3.5), module_point(3.5, m - 3.5)]
        base = third_finder_candidates(anchor_pair[0], anchor_pair[1])
        if base:
            direction = int(
                np.argmin([min(np.hypot(t[0] - c[0], t[1] - c[1]) for c in centres) for t in base])
            )
            seen_corners = [best.corners]
            for scale in ANCHOR_SCALES:
                third = third_finder_candidates(anchor_pair[0], anchor_pair[1], scale=scale)[
                    direction
                ]
                in_frame = 0 <= third[0] < gray.shape[1] and 0 <= third[1] < gray.shape[0]
                if finder_points is None and not in_frame:
                    continue
                refits = fit_grid(gray, [*anchor_pair, third], (best.modules,), start_delta=12.0)
                if not refits:
                    continue
                trial = refits[0]
                if BOW_REFINE:
                    trial = refine_bow(gray, trial, known_dark, known_light)
                # A scale that tears the alignment pattern and the timing off their cells is
                # not a basin worth decoding; and two scales that fell into the same basin
                # need only one verdict.
                if trial.wrong_known > 3 * best.wrong_known + 5:
                    continue
                if any(float(np.abs(trial.corners - s).max()) < 1.5 for s in seen_corners):
                    continue
                seen_corners.append(trial.corners)

                trial_posterior, trial_blanked = _damp_featureless(
                    trial.posterior, known_dark, known_light
                )
                trial_mm = ModuleMatrix(trial_posterior, known_dark, known_light)
                trial_search, trial_repair = _decode_chain(trial_mm, budget, probe=False)

                # The witness check -- but only for repairs no check symbol vouches for.
                # See ANCHOR_WITNESS_CONFIDENCE for the two wrong texts and the two simpler
                # judges this is made of.
                adopted = trial_search.text is not None
                if adopted and trial_repair is not None and trial_repair.ecc:
                    try:
                        plan = block_plan(version_for_modules(best.modules), trial_repair.ecc)
                        unconfirmed = trial_repair.erasures_used >= plan.ec_per_block * max(
                            trial_repair.blocks, 1
                        )
                    except KeyError:
                        unconfirmed = True
                    if unconfirmed and trial_search.matrix is not None:
                        witnesses = (np.abs(trial_posterior - 0.5) > ANCHOR_WITNESS_CONFIDENCE) & ~(
                            known_dark | known_light
                        )
                        overruled = int(
                            ((trial_search.matrix != trial_mm.hard()) & witnesses).sum()
                        )
                        adopted = overruled == 0

                grid_event("anchor")(trial)
                _emit(
                    progress,
                    "anchor",
                    scale=scale,
                    wrong=int(trial.wrong_known),
                    adopted=adopted,
                )
                if adopted:
                    best, posterior, blanked = trial, trial_posterior, trial_blanked
                    mm, search, repair_result = trial_mm, trial_search, trial_repair
                    break

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
        blanked=blanked,
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
    sizes: Sequence[int] = DEFAULT_SIZES,
    budget: int = 4000,
    band: float = 0.15,
    rule: str = DEFAULT_FUSION,
    min_agreement: float = 0.75,
    member_budget: int = MEMBER_BUDGET,
    invert: bool | None = None,
    finder_points: list[tuple[float, float]] | None = None,
    progress: ProgressFn | None = None,
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

    One photograph after another, and measured that way rather than assumed. Recovering a burst
    concurrently is the obvious suggestion and it is wrong twice over. The loop below is a
    short-circuit: the first photograph that solves ends the whole call, so running all of them
    at once would pay for every recovery the sequence never has to make. And the concurrency
    does not repay it anyway -- four recoveries in four threads took 0.90x the time of running
    the same four in turn, because the descent that dominates a solve is Python-level work
    under the GIL, where threads contend rather than cooperate. Processes would escape the GIL
    and lose the progress callbacks, the shared memory and the short-circuit with it.
    """
    if not images:
        return SolveResult(text=None, failure="no images given")
    if len(images) == 1:
        return solve(
            images[0],
            crop=crop,
            sizes=sizes,
            budget=budget,
            band=band,
            invert=invert,
            finder_points=finder_points,
            progress=progress,
        )

    members = []
    for index, image in enumerate(images):
        _emit(progress, "member", index=index, total=len(images))

        def tagged(event: str, data: dict, _index: int = index) -> None:
            _emit(progress, event, member=_index, **data)

        # The same hand-marked centres for every photograph, like the crop: both assume the
        # framings match, and mixed framings are the caller's to align beforehand.
        member = solve(
            image,
            crop=crop,
            sizes=sizes,
            budget=member_budget,
            band=band,
            invert=invert,
            finder_points=finder_points,
            progress=tagged,
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
    usable.sort(key=fusion_rank)
    best = usable[0]
    assert best.modules is not None  # a member with a matrix always carries its grid's size

    known_dark, known_light = structure_mask(best.modules)
    posteriors: list[np.ndarray] = []
    for member in usable:
        assert member.matrix is not None  # usable is filtered on exactly this
        posteriors.append(member.matrix.posterior)
    consensus = fuse_images(
        posteriors,
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
    # The members arrive damped already, and averaging half-values keeps them there -- but a
    # patch every photograph read the same way can first *become* uniform in the fusion.
    fused, blanked = _damp_featureless(consensus.posterior, known_dark, known_light)

    mm = ModuleMatrix(fused, known_dark, known_light)
    search, repair_result = _decode_chain(mm, budget, progress=progress)

    known = known_dark | known_light
    wrong_sampled = int(((fused >= 0.5)[known] != known_dark[known]).sum())

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
        blanked=blanked,
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
