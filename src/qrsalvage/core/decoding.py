"""Render the matrix, decode it, and probe where the doubt is greatest.

The decoder here is not an advisor but an exact oracle: it does not say "warmer", it says
"valid" or "not valid". That is why no learned value function is needed -- only a sensible
order in which to question it, cheapest doubts first.
"""

from __future__ import annotations

import heapq
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

import numpy as np

from . import oracle
from .matrix import ModuleMatrix


def render(matrix: np.ndarray, scale: int = 10, quiet: int = 4) -> np.ndarray:
    """Draw a module matrix as an ideal black-and-white image with a quiet zone.

    The quiet zone is mandatory: an image cropped flush to the code edge is rejected by every
    decoder, no matter how clean the code inside it is.

    repeat instead of kron, and the quiet zone written into a preallocated page instead of
    np.pad: this function is effectively the entire cost of a decode attempt, and the probe
    makes thousands of them. Measured on the probe benchmark, the rewrite roughly halves the
    per-attempt price.
    """
    n = int(matrix.shape[0])
    margin = quiet * scale
    side = n * scale + 2 * margin
    page = np.full((side, side), np.uint8(255))
    cells = np.where(matrix, np.uint8(0), np.uint8(255))
    page[margin : margin + n * scale, margin : margin + n * scale] = cells.repeat(
        scale, axis=0
    ).repeat(scale, axis=1)
    return page


def decode_matrix(matrix: np.ndarray, scale: int = 4) -> str | None:
    """A single decode attempt on the rendered matrix."""
    return oracle.decode(render(matrix, scale=scale))


def _patch_module(
    page: np.ndarray, row: int, col: int, dark: bool, scale: int, quiet: int = 4
) -> None:
    """Set one module in a page that render() has already drawn.

    The probe's candidates differ from the base matrix in a handful of modules out of several
    thousand. Redrawing the whole page for each one spends almost all of its time reproducing
    pixels nobody touched, so the search patches those few blocks and puts them back instead.
    The geometry has to match render() exactly: same quiet zone, same scale, dark is zero.
    """
    margin = quiet * scale
    top, left = margin + row * scale, margin + col * scale
    page[top : top + scale, left : left + scale] = 0 if dark else 255


@dataclass
class SearchResult:
    """Outcome of the probing search."""

    text: str | None
    candidates_tried: int
    flipped: list[tuple[int, int]] = field(default_factory=list)
    matrix: np.ndarray | None = None


def _subsets_by_cost(costs: np.ndarray, budget: int) -> Iterator[tuple[int, ...]]:
    """Enumerate subsets in ascending order of total cost.

    Best-first search over a heap: each subset already emitted spawns exactly two successors --
    extend it, or advance its last element. That way every subset comes out exactly once and in
    the right order.
    """
    m = len(costs)
    if m == 0:
        return
    heap: list[tuple[float, tuple[int, ...]]] = [(float(costs[0]), (0,))]
    seen = 0
    while heap and seen < budget:
        cost, subset = heapq.heappop(heap)
        seen += 1
        yield subset
        last = subset[-1]
        if last + 1 < m:
            heapq.heappush(heap, (cost + float(costs[last + 1]), (*subset, last + 1)))
            heapq.heappush(
                heap,
                (cost - float(costs[last]) + float(costs[last + 1]), (*subset[:-1], last + 1)),
            )


def ordered_search(
    mm: ModuleMatrix,
    max_cells: int = 22,
    budget: int = 4000,
    scale: int = 4,
    on_step: Callable[[int], None] | None = None,
) -> SearchResult:
    """Probe the matrix at its least certain cells, cheapest doubts first.

    The lock-picking analogy is literal: not all pins at once, but the weakest one first, and
    after every attempt you ask the lock whether it opens.
    """
    base = mm.hard()
    # Drawn once and then patched in place for every candidate. render() is the whole cost of a
    # decode attempt apart from the oracle itself -- measured at 3.7 % of a hard solve over 4003
    # attempts -- and each candidate differs from this page in at most `max_cells` modules.
    page = render(base, scale=scale)
    text = oracle.decode(page)
    if text:
        return SearchResult(text=text, candidates_tried=1, matrix=base)

    cost_field = mm.flip_cost()
    ranked = np.argsort(cost_field, axis=None)
    order = [int(i) for i in ranked if np.isfinite(cost_field.flat[i])][:max_cells]
    if not order:
        return SearchResult(text=None, candidates_tried=1)

    costs = np.array([cost_field.flat[i] for i in order], dtype=np.float64)
    n = mm.modules
    tried = 1

    for subset in _subsets_by_cost(costs, budget):
        flipped = [divmod(order[position], n) for position in subset]
        for row, col in flipped:
            _patch_module(page, row, col, not base[row, col], scale)
        tried += 1
        # Every 250th attempt, not every attempt: the point of the report is that the search
        # is alive, and a thousand messages a second would cost more than they say.
        if on_step and tried % 250 == 0:
            on_step(tried)
        text = oracle.decode(page)
        if text:
            # Only the winner is ever built as a matrix. Every other candidate exists purely as
            # a few patched blocks on the page and is undone again below.
            candidate = base.copy()
            for row, col in flipped:
                candidate[row, col] = not candidate[row, col]
            return SearchResult(
                text=text, candidates_tried=tried, flipped=flipped, matrix=candidate
            )
        for row, col in flipped:
            _patch_module(page, row, col, bool(base[row, col]), scale)

    return SearchResult(text=None, candidates_tried=tried)


def reencode(text: str, ecc: str | None = None) -> np.ndarray:
    """Encode the recovered content afresh and return a standards-compliant module matrix.

    Better than drawing the reconstruction: the result is then guaranteed to be a valid code
    rather than a reconstruction that happened to pass.

    `ecc` forces an error correction level. Left open, the encoder picks one, which is usually
    not the level the original carried -- worth knowing when the point is to reproduce a label
    rather than to make a new one. Raising it is not free either: the redundancy has to go
    somewhere, so a higher level means more modules and, at a fixed printed size, smaller ones.
    """
    if ecc is not None:
        ecc = ecc.upper()
        if ecc not in ("L", "M", "Q", "H"):
            raise ValueError(f"unknown error correction level: {ecc!r}")
    return oracle.encode(text, ecc)
