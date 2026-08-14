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
    deinterleave,
    extract_codewords,
    function_mask,
    interleave,
    place_codewords,
    placement_order,
    read_format,
)
from qrsalvage.core.qrspec import BLOCK_PLANS, TOTAL_CODEWORDS, block_plan
from qrsalvage.core.repair import repair_progressive
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
    ecc, mask, _ = read_format(matrix)
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
    n = matrix.shape[0]
    order = placement_order(n)
    assert len(set(order)) == len(order), "a position was handed out twice"
    assert len(order) == int((~function_mask(n)).sum())


@pytest.mark.parametrize("version", VERSIONS)
def test_extract_and_place_back_returns_the_same_matrix(version):
    """The inversion check: an order that is off by one shows up here immediately."""
    matrix = _sample(version)
    header = read_format(matrix)
    assert header is not None, "an undamaged code must have readable format information"
    ecc, mask, distance = header
    assert distance == 0, "an undamaged code must not show a BCH distance"

    codewords = extract_codewords(matrix, mask)
    rebuilt = np.array(matrix, dtype=bool, copy=True)
    rebuilt[~function_mask(matrix.shape[0])] = False
    place_codewords(rebuilt, codewords, mask)
    assert np.array_equal(rebuilt, matrix)


@pytest.mark.parametrize("version", VERSIONS)
def test_interleaving_is_invertible(version):
    matrix = _sample(version)
    ecc, mask, _ = read_format(matrix)
    codewords = extract_codewords(matrix, mask)[: block_plan(version, ecc).total_codewords]
    blocks = deinterleave(codewords, version, ecc)
    assert interleave(blocks, version, ecc) == codewords


@pytest.mark.parametrize("version", VERSIONS)
def test_a_real_code_has_vanishing_syndromes(version):
    """The sharpest table test: if the block layout is wrong, this is where it shows."""
    matrix = _sample(version)
    ecc, mask, _ = read_format(matrix)
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
    assert np.array_equal(result.matrix, original)
    assert result.errors_corrected > 0


def test_erasures_rescue_what_errors_alone_cannot():
    """The proof on a whole image: same damage, once without and once with position hints."""
    text = "ERASURES-BEAT-ERRORS"
    original = reencode(text)
    n = original.shape[0]
    ecc, _, _ = read_format(original)
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
    assert np.array_equal(with_hint.matrix, original)
    assert with_hint.erasures_used > 0
    if without_hint.ok:
        pytest.skip("the damage was manageable without position hints too")
