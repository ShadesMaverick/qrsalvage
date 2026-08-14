"""Where in the grid each bit lives: function modules, placement order, interleaving.

This part is pure bookkeeping, but the kind of bookkeeping where a mistake does not announce
itself: an order that is off by one still yields codewords, just wrong ones. It is secured not
by care but by inversion -- whoever extracts and places back must get the same matrix. test_rs.py
checks exactly that against real codes.
"""

from __future__ import annotations

import numpy as np

from .qrspec import REMAINDER_BITS, block_plan, decode_format, format_bits, mask_bit
from .structure import ALIGNMENT_CENTERS, version_for_modules


def function_mask(modules: int) -> np.ndarray:
    """Every module that carries no data: finders, timing, alignment, format, version."""
    n = modules
    version = version_for_modules(n)
    mask = np.zeros((n, n), dtype=bool)

    # Finders including separators -- an 8x8 field in each corner
    mask[0:8, 0:8] = True
    mask[0:8, n - 8 : n] = True
    mask[n - 8 : n, 0:8] = True

    mask[6, :] = True  # timing
    mask[:, 6] = True

    for ar in ALIGNMENT_CENTERS.get(version, ()):
        for ac in ALIGNMENT_CENTERS.get(version, ()):
            if (ar, ac) in ((6, 6), (6, n - 7), (n - 7, 6)):
                continue
            mask[ar - 2 : ar + 3, ac - 2 : ac + 3] = True

    mask[8, 0:9] = True  # format information
    mask[0:9, 8] = True
    mask[8, n - 8 : n] = True
    mask[n - 8 : n, 8] = True

    if version >= 7:  # version information
        mask[0:6, n - 11 : n - 8] = True
        mask[n - 11 : n - 8, 0:6] = True

    return mask


def placement_order(modules: int) -> list[tuple[int, int]]:
    """The order in which data modules are written.

    Two columns wide, from bottom right leftwards, alternating direction, skipping column 6
    where the vertical timing pattern sits.
    """
    n = modules
    functions = function_mask(n)
    order: list[tuple[int, int]] = []
    col = n - 1
    upward = True
    while col > 0:
        if col == 6:
            col -= 1
        for i in range(n):
            row = (n - 1 - i) if upward else i
            for c in (col, col - 1):
                if not functions[row, c]:
                    order.append((row, c))
        col -= 2
        upward = not upward
    return order


def format_positions(modules: int) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """Module positions of both format copies, ascending by bit number (bit 0 first).

    The order is verified against forced error correction levels: encode the same text as L, M,
    Q and H and exactly that level has to come back out, from both copies and at BCH distance
    zero. Numbered the other way round the same routine returns a distance of three for every
    code -- just inside the correction limit and therefore dangerously inconspicuous.
    """
    n = modules
    first = [(r, 8) for r in range(6)] + [(7, 8), (8, 8), (8, 7)]
    first += [(8, c) for c in range(5, -1, -1)]

    second = [(8, n - 1 - i) for i in range(8)]
    second += [(n - 7 + i, 8) for i in range(7)]
    return first, second


def read_format(matrix: np.ndarray) -> tuple[str, int, int] | None:
    """Read the format information from both copies and take the more credible one.

    Two independent copies, each with its own BCH protection: a misreading shows up here before
    it propagates through the entire decoding.
    """
    candidates = []
    for positions in format_positions(matrix.shape[0]):
        raw = 0
        for bit, (r, c) in enumerate(positions):
            if matrix[r, c]:
                raw |= 1 << bit
        decoded = decode_format(raw)
        if decoded is not None:
            candidates.append(decoded)

    if not candidates:
        return None
    return min(candidates, key=lambda t: t[2])


def write_format(matrix: np.ndarray, ecc: str, mask_pattern: int) -> None:
    """Write the format information into both copies and set the always-dark module."""
    n = matrix.shape[0]
    bits = format_bits(ecc, mask_pattern)

    for positions in format_positions(n):
        for bit, (r, c) in enumerate(positions):
            matrix[r, c] = bool(bits & (1 << bit))
    matrix[4 * version_for_modules(n) + 9, 8] = True


def extract_codewords(matrix: np.ndarray, mask_pattern: int) -> list[int]:
    """Read the data modules in placement order and unmask them."""
    order = placement_order(matrix.shape[0])
    bits: list[int] = []
    for r, c in order:
        value = bool(matrix[r, c])
        if mask_bit(mask_pattern, r, c):
            value = not value
        bits.append(int(value))

    codewords: list[int] = []
    for i in range(0, len(bits) - 7, 8):
        value = 0
        for bit in bits[i : i + 8]:
            value = (value << 1) | bit
        codewords.append(value)
    return codewords


def place_codewords(matrix: np.ndarray, codewords: list[int], mask_pattern: int) -> None:
    """Inverse of :func:`extract_codewords`, writes back into the matrix."""
    n = matrix.shape[0]
    order = placement_order(n)
    bits: list[int] = []
    for value in codewords:
        bits.extend((value >> shift) & 1 for shift in range(7, -1, -1))
    bits.extend([0] * REMAINDER_BITS.get(version_for_modules(n), 0))

    for (r, c), bit in zip(order, bits, strict=False):
        value = bool(bit)
        if mask_bit(mask_pattern, r, c):
            value = not value
        matrix[r, c] = value


def deinterleave(codewords: list[int], version: int, ecc: str) -> list[list[int]]:
    """Undo the interleaving; returns [data..., check symbols...] per block.

    QR spreads the codewords round-robin across the blocks so that contiguous damage in the
    image is distributed over all of them instead of destroying one. For us that means uncertain
    cells have to travel the same route back, otherwise the erasures point at the wrong places.
    """
    plan = block_plan(version, ecc)
    sizes = plan.block_sizes()
    blocks: list[list[int]] = [[] for _ in sizes]

    position = 0
    for i in range(max(sizes)):
        for index, size in enumerate(sizes):
            if i < size:
                blocks[index].append(codewords[position])
                position += 1

    for _ in range(plan.ec_per_block):
        for index in range(len(sizes)):
            blocks[index].append(codewords[position])
            position += 1

    return blocks


def interleave(blocks: list[list[int]], version: int, ecc: str) -> list[int]:
    """Inverse of :func:`deinterleave`."""
    plan = block_plan(version, ecc)
    sizes = plan.block_sizes()
    out: list[int] = []

    for i in range(max(sizes)):
        for index, size in enumerate(sizes):
            if i < size:
                out.append(blocks[index][i])

    for i in range(plan.ec_per_block):
        for index, size in enumerate(sizes):
            out.append(blocks[index][size + i])

    return out


def codeword_positions(matrix_size: int, version: int, ecc: str) -> list[list[list[int]]]:
    """Which module positions (as flat indices) belong to which codeword of which block?

    This is the bridge between image uncertainty and decoder: a wobbly cell becomes an erasure
    at exactly the right place in the right block.
    """
    order = placement_order(matrix_size)
    plan = block_plan(version, ecc)
    sizes = plan.block_sizes()

    # Order of codewords in the stream -> (block, index within block)
    assignment: list[tuple[int, int]] = []
    for i in range(max(sizes)):
        for index, size in enumerate(sizes):
            if i < size:
                assignment.append((index, i))
    for i in range(plan.ec_per_block):
        for index, size in enumerate(sizes):
            assignment.append((index, size + i))

    positions: list[list[list[int]]] = [
        [[] for _ in range(size + plan.ec_per_block)] for size in sizes
    ]
    for stream_index, (block, index) in enumerate(assignment):
        for bit in range(8):
            place = stream_index * 8 + bit
            if place >= len(order):
                break
            r, c = order[place]
            positions[block][index].append(r * matrix_size + c)
    return positions
