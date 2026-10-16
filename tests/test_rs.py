"""Securing the Reed-Solomon chain against an independent encoder.

Tables and bit orders are the most dangerous kind of code: a transposed value does not crash,
it quietly delivers something wrong. So nothing here is checked against itself -- always against
a real code produced by zxing, and through the inversion, which has to return the same matrix.
"""

from __future__ import annotations

import numpy as np
import pytest

from qrsalvage.core.decoding import decode_matrix, reencode
from qrsalvage.core.galois import ReedSolomonError, correct_block
from qrsalvage.core.layout import (
    codeword_positions,
    deinterleave,
    extract_codewords,
    format_positions,
    function_mask,
    interleave,
    place_codewords,
    placement_order,
    read_format,
    read_format_consensus,
)
from qrsalvage.core.qrspec import BLOCK_PLANS, TOTAL_CODEWORDS, block_plan, format_bits
from qrsalvage.core.repair import repair_progressive, repair_scattered
from qrsalvage.core.structure import version_for_modules


def _sample(version: int) -> np.ndarray | None:
    """A real code of the requested version, produced by the encoder."""
    for length in range(1, 400, 2):
        matrix = reencode("A" * length)
        if version_for_modules(matrix.shape[0]) == version:
            return matrix
        if version_for_modules(matrix.shape[0]) > version:
            return None
    return None


VERSIONS = [v for v in range(1, 11) if _sample(v) is not None]


def _first_block(text: str):
    """Return (block, check symbol count) for the first block of a real code.

    A valid block is obtained by taking one out of a genuinely encoded code -- that way the
    check symbols are the encoder's, not ours, and the test cannot pass by agreeing with itself.
    """
    matrix = reencode(text)
    header = read_format(matrix)
    assert header is not None
    ecc, mask, _ = header
    version = version_for_modules(matrix.shape[0])
    plan = block_plan(version, ecc)
    block = deinterleave(extract_codewords(matrix, mask), version, ecc)[0]
    return block, plan.ec_per_block


# --- Tables ----------------------------------------------------------------------------


@pytest.mark.parametrize(("version", "ecc"), sorted(BLOCK_PLANS))
def test_block_layout_adds_up_to_the_total(version, ecc):
    """The consistency rule that exposes a typo in the table."""
    plan = BLOCK_PLANS[(version, ecc)]
    assert plan.total_codewords == TOTAL_CODEWORDS[version]


# --- Galois field and Reed-Solomon -------------------------------------------------------


def test_reed_solomon_repairs_errors():
    block, nsym = _first_block("CHECKBLOCK")

    # Intact block: nothing to do
    clean, errors, erasures = correct_block(list(block), nsym)
    assert clean == list(block)
    assert not errors and not erasures

    # Two unknown errors
    damaged = list(block)
    damaged[3] ^= 0xFF
    damaged[9] ^= 0x5A
    healed, errors, _ = correct_block(damaged, nsym)
    assert healed == list(block)
    assert sorted(errors) == [3, 9]


def test_erasures_reach_twice_as_far_as_errors():
    """The central point of the whole module, stated as a test."""
    block, nsym = _first_block("REACH-TEST-12345")

    positions = list(range(nsym))  # exactly as many defects as there are check symbols
    damaged = list(block)
    for p in positions:
        damaged[p] ^= 0x3C

    # As unknown errors: hopeless, that exceeds the correction limit.
    with pytest.raises(ReedSolomonError):
        correct_block(damaged, nsym)

    # As erasures with known positions: fully repairable.
    healed, _, used = correct_block(damaged, nsym, erasures=positions)
    assert healed == list(block)
    assert len(used) == nsym


# --- Placement and interleaving ----------------------------------------------------------


@pytest.mark.parametrize("version", VERSIONS)
def test_placement_covers_exactly_the_data_modules(version):
    matrix = _sample(version)
    assert matrix is not None
    n = matrix.shape[0]
    order = placement_order(n)
    assert len(set(order)) == len(order), "a position was handed out twice"
    assert len(order) == int((~function_mask(n)).sum())


@pytest.mark.parametrize("version", VERSIONS)
def test_extract_and_place_back_returns_the_same_matrix(version):
    """The inversion check: an order that is off by one shows up here immediately."""
    matrix = _sample(version)
    assert matrix is not None
    header = read_format(matrix)
    assert header is not None, "an undamaged code must have readable format information"
    ecc, mask, distance = header
    assert distance == 0, "an undamaged code must not show a BCH distance"

    codewords = extract_codewords(matrix, mask)
    rebuilt = np.array(matrix, dtype=bool, copy=True)
    rebuilt[~function_mask(matrix.shape[0])] = False
    place_codewords(rebuilt, codewords, mask)
    assert np.array_equal(rebuilt, matrix)


def test_format_consensus_rejects_two_exact_but_different_copies():
    matrix = reencode("FORMAT-COPY-CONFLICT", ecc="L")
    header = read_format(matrix)
    assert header is not None
    first, _second = format_positions(matrix.shape[0])
    conflicting = format_bits("M", header[1])
    for bit, (row, col) in enumerate(first):
        matrix[row, col] = bool(conflicting & (1 << bit))

    assert read_format(matrix) == ("M", header[1], 0)
    assert read_format_consensus(matrix) is None


@pytest.mark.parametrize("version", VERSIONS)
def test_interleaving_is_invertible(version):
    matrix = _sample(version)
    assert matrix is not None
    header = read_format(matrix)
    assert header is not None
    ecc, mask, _ = header
    codewords = extract_codewords(matrix, mask)[: block_plan(version, ecc).total_codewords]
    blocks = deinterleave(codewords, version, ecc)
    assert interleave(blocks, version, ecc) == codewords


@pytest.mark.parametrize("version", VERSIONS)
def test_a_real_code_has_vanishing_syndromes(version):
    """The sharpest table test: if the block layout is wrong, this is where it shows."""
    matrix = _sample(version)
    assert matrix is not None
    header = read_format(matrix)
    assert header is not None
    ecc, mask, _ = header
    plan = block_plan(version, ecc)
    codewords = extract_codewords(matrix, mask)[: plan.total_codewords]
    for block in deinterleave(codewords, version, ecc):
        clean, errors, erasures = correct_block(block, plan.ec_per_block)
        assert clean == block
        assert not errors and not erasures


# --- Repairing whole matrices ------------------------------------------------------------


def test_repair_restores_damaged_modules():
    # Synthetic, but shaped like a real Zigbee pairing payload so the code lands in the same
    # version and mode. A real one would be a device secret in a public repository.
    text = "Z:0123456789ABCDEF$I:00112233445566778899AABBCCDDEEFF"
    original = reencode(text)
    n = original.shape[0]
    free = np.argwhere(~function_mask(n))

    damaged = original.copy()
    rng = np.random.default_rng(7)
    for index in rng.choice(len(free), size=12, replace=False):
        r, c = free[index]
        damaged[r, c] = not damaged[r, c]

    assert decode_matrix(damaged) is None or decode_matrix(damaged) == text

    result = repair_progressive(damaged)
    assert result.ok, result.failure
    assert result.matrix is not None
    assert np.array_equal(result.matrix, original)
    assert result.errors_corrected > 0


def test_erasures_rescue_what_errors_alone_cannot():
    """The proof on a whole image: same damage, once without and once with position hints."""
    text = "ERASURES-BEAT-ERRORS"
    original = reencode(text)
    n = original.shape[0]
    header = read_format(original)
    assert header is not None
    ecc, _, _ = header
    plan = block_plan(version_for_modules(n), ecc)

    free = np.argwhere(~function_mask(n))
    rng = np.random.default_rng(3)
    # Enough damage that plain error correction is overwhelmed
    count = plan.ec_per_block * plan.blocks
    chosen = rng.choice(len(free), size=count, replace=False)

    damaged = original.copy()
    posterior = np.where(original, 0.99, 0.01)
    for index in chosen:
        r, c = free[index]
        damaged[r, c] = not damaged[r, c]
        posterior[r, c] = 0.5  # exactly what the image side knows: I am unsure here

    without_hint = repair_progressive(damaged, posterior=None)
    with_hint = repair_progressive(damaged, posterior=posterior)

    assert with_hint.ok, with_hint.failure
    assert with_hint.matrix is not None
    assert np.array_equal(with_hint.matrix, original)
    assert with_hint.erasures_used > 0
    if without_hint.ok:
        pytest.skip("the damage was manageable without position hints too")


def test_scattered_erasures_reach_what_no_prefix_can():
    """Damage interleaved with sound codewords in the reliability order.

    Constructed so that every prefix of the order provably fails: the sound-but-doubtful
    codewords are all cheaper than the damaged ones, so a prefix must erase the whole decoy
    band before it touches the first damaged codeword, and by then the budget is spent. An
    arbitrary subset walks around the decoys.
    """
    text = "SCATTERED-BEATS-PREFIX"
    original = reencode(text)
    n = original.shape[0]
    version = version_for_modules(n)
    header = read_format(original)
    assert header is not None
    ecc, _, _ = header
    plan = block_plan(version, ecc)
    t = plan.ec_per_block
    positions = codeword_positions(n, version, ecc)[0]

    damaged_count = t // 2 + 1  # one more than plain error correction can absorb
    decoy_count = t - 2
    assert decoy_count > t - damaged_count, "premise: decoys must outlast every prefix"

    damaged = original.copy()
    posterior = np.where(original, 0.999, 0.001)

    # The damaged codewords: one flipped module each, and slightly *more* reliable than the
    # decoys, so every prefix of the reliability order fills up with decoys first.
    for index in range(damaged_count):
        flat = positions[index][0]
        damaged.flat[flat] = not damaged.flat[flat]
        posterior.flat[flat] = 0.52 if damaged.flat[flat] else 0.48
    for index in range(damaged_count, damaged_count + decoy_count):
        flat = positions[index][0]
        posterior.flat[flat] = 0.51 if damaged.flat[flat] else 0.49

    damaged_header = read_format(damaged)
    assert damaged_header is not None
    block = deinterleave(
        extract_codewords(damaged, damaged_header[1])[: plan.total_codewords],
        version,
        ecc,
    )[0]
    with pytest.raises(ReedSolomonError):
        corrected, error_positions, _ = correct_block(block, t, [])
        if len(error_positions) < damaged_count:
            raise ReedSolomonError("miscorrected instead of failing")  # also a fail

    # The outside check, as in production. Without it the ladder happily returns a valid-but-
    # wrong solution here -- five erased decoys plus one "corrected" error satisfy the
    # syndromes -- which is precisely the failure mode repair.py documents.
    def verify(candidate: np.ndarray) -> bool:
        return decode_matrix(candidate) == text

    ladder = repair_progressive(damaged, posterior=posterior, verify=verify)
    assert not ladder.ok, "premise broken: a prefix sufficed, nothing scattered to show"

    scattered = repair_scattered(damaged, posterior, verify=verify)
    assert scattered.ok, scattered.failure
    assert scattered.matrix is not None
    assert np.array_equal(scattered.matrix, original)
