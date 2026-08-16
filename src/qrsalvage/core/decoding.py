"""Render the matrix, decode it, and probe where the doubt is greatest.

The decoder here is not an advisor but an exact oracle: it does not say "warmer", it says
"valid" or "not valid". That is why no learned value function is needed -- only a sensible
order in which to question it, cheapest doubts first.
"""

from __future__ import annotations

import heapq
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


@dataclass
class SearchResult:
    """Outcome of the probing search."""

    text: str | None
    candidates_tried: int
    flipped: list[tuple[int, int]] = field(default_factory=list)
    matrix: np.ndarray | None = None


def _subsets_by_cost(costs: np.ndarray, budget: int):
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
    mm: ModuleMatrix, max_cells: int = 22, budget: int = 4000, scale: int = 4, on_step=None
) -> SearchResult:
    """Probe the matrix at its least certain cells, cheapest doubts first.

    The lock-picking analogy is literal: not all pins at once, but the weakest one first, and
    after every attempt you ask the lock whether it opens.
    """
    base = mm.hard()
    text = decode_matrix(base, scale=scale)
    if text:
        return SearchResult(text=text, candidates_tried=1, matrix=base)

    cost_field = mm.flip_cost()
    order = np.argsort(cost_field, axis=None)
    order = [int(i) for i in order if np.isfinite(cost_field.flat[i])][:max_cells]
    if not order:
        return SearchResult(text=None, candidates_tried=1)

    costs = np.array([cost_field.flat[i] for i in order], dtype=np.float64)
    n = mm.modules
    tried = 1

    for subset in _subsets_by_cost(costs, budget):
        candidate = base.copy()
        for position in subset:
            flat = order[position]
            candidate.flat[flat] = not candidate.flat[flat]
        tried += 1
        # Every 250th attempt, not every attempt: the point of the report is that the search
        # is alive, and a thousand messages a second would cost more than they say.
        if on_step and tried % 250 == 0:
            on_step(tried)
        text = decode_matrix(candidate, scale=scale)
        if text:
            flipped = [(order[p] // n, order[p] % n) for p in subset]
            return SearchResult(
                text=text, candidates_tried=tried, flipped=flipped, matrix=candidate
            )

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
