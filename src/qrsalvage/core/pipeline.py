"""The whole path from photograph to plain text, without output and without file access.

This layer decides nothing on its own, it composes: preprocess, find the grid, try the versions,
sample, decode, probe if needed. All reporting is the caller's business -- the core stays free
of anything but library code.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .decoding import SearchResult, decode_matrix, ordered_search
from .ensemble import Consensus, GeometryConsensus, consensus_posterior, geometry_consensus
from .geometry import GridFit, find_finders, initial_corners, order_finders, refine_corners
from .matrix import ModuleMatrix
from .preprocess import prepare
from .repair import RepairResult, repair_progressive
from .structure import is_valid_size, structure_mask, timing_score, version_for_modules

DEFAULT_SIZES = (21, 25, 29, 33, 37, 41)
ENSEMBLE_MODES = ("off", "sampling", "geometry")


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
    repair: RepairResult | None = None
    failure: str | None = None

    @property
    def solved(self) -> bool:
        return self.text is not None


def fit_grid(gray: np.ndarray, binary: np.ndarray, sizes=DEFAULT_SIZES) -> list[GridFit]:
    """Fit a grid for every candidate size and score it against the known cells.

    The version is deliberately not taken on faith from the finder width: with few pixels per
    module that estimate regularly lands between two candidates, and the difference between
    right and wrong is immediately visible in the known cells.
    """
    finders = find_finders(binary)
    if len(finders) < 3:
        return []
    top_left, top_right, bottom_left = order_finders(finders[:3])

    fits: list[GridFit] = []
    for modules in sizes:
        if not is_valid_size(modules):
            continue
        known_dark, known_light = structure_mask(modules)
        corners = initial_corners(top_left, top_right, bottom_left, modules)
        fits.append(refine_corners(gray, corners, modules, 12, known_dark, known_light))
    return fits


def solve(
    bgr: np.ndarray,
    crop: tuple[int, int, int, int] | None = None,
    sizes=DEFAULT_SIZES,
    budget: int = 4000,
    band: float = 0.15,
    ensemble: str = "off",
) -> SolveResult:
    """Recover a QR code from a photograph. Never raises, always reports.

    `ensemble` selects what gets measured repeatedly:

    - ``"off"``       one measurement, one grid.
    - ``"sampling"``  one grid, several preprocessings. Demonstrably useless -- every member
                      shares the grid error. Details in ensemble.py.
    - ``"geometry"``  several independently fitted grids. More expensive, but the spread hits
                      the actual source of error.
    """
    if ensemble not in ENSEMBLE_MODES:
        raise ValueError(f"unknown ensemble mode: {ensemble!r}")
    if crop is not None:
        x0, y0, x1, y1 = crop
        bgr = bgr[y0:y1, x0:x1]

    gray, binary = prepare(bgr)
    finders = find_finders(binary)
    if len(finders) < 3:
        return SolveResult(
            text=None, finders=finders, failure=f"only {len(finders)} finder candidates found"
        )

    fits = fit_grid(gray, binary, sizes)
    if not fits:
        return SolveResult(text=None, finders=finders, failure="no grid could be fitted")

    best = min(fits, key=lambda f: (f.wrong_known, -f.quality))
    known_dark, known_light = structure_mask(best.modules)

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

    # Ordered by cost: the direct attempt first, then Reed-Solomon with erasures, and only
    # last the combinatorial probe. The decoder computes the right values in one step where
    # the search would have to try thousands of combinations.
    repair_result: RepairResult | None = None
    hard = mm.hard()
    text = decode_matrix(hard)
    search = SearchResult(text=text, candidates_tried=1, matrix=hard if text else None)

    if not text:
        repair_result = repair_progressive(
            hard, posterior=posterior, verify=lambda m: decode_matrix(m) is not None
        )
        if repair_result.ok:
            text = decode_matrix(repair_result.matrix)
            if text:
                search = SearchResult(text=text, candidates_tried=2, matrix=repair_result.matrix)

    if not text:
        search = ordered_search(mm, budget=budget)

    # Two separate error counts, because they measure two different things: wrong_known scores
    # the grid fit, wrong_sampled the sampling that the search actually ran on. Conflating them
    # makes a change to the sampling invisible.
    known = known_dark | known_light
    wrong_sampled = int(((posterior >= 0.5)[known] != known_dark[known]).sum())

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
        finders=finders,
        per_size=fits,
        consensus=consensus,
        geometry=geometry,
        repair=repair_result,
        failure=None if search.text else "no valid code in the searched space",
    )
