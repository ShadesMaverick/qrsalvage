"""The structure mask is the calibration reference of the whole method.

If it is wrong, everything else calibrates itself against a false truth -- silently, because a
wrong reference still produces plausible numbers. So it is checked against an independent
encoder rather than against itself.
"""

from __future__ import annotations

import numpy as np
import pytest

from qrsalvage.core.decoding import reencode
from qrsalvage.core.structure import (
    is_valid_size,
    modules_for_version,
    structure_mask,
    timing_score,
    version_for_modules,
)


@pytest.mark.parametrize("version", [1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
def test_size_and_version_round_trip(version):
    modules = modules_for_version(version)
    assert version_for_modules(modules) == version
    assert is_valid_size(modules)


def test_invalid_sizes_are_rejected():
    assert not is_valid_size(28)
    assert not is_valid_size(17)


def _sample_per_version(highest: int = 7) -> dict[int, np.ndarray]:
    """Find one genuinely encoded code for each version.

    Payload length cannot be mapped back to a version -- the encoder picks mode and version
    itself. So we search rather than calculate.
    """
    found: dict[int, np.ndarray] = {}
    for length in range(1, 400, 3):
        matrix = reencode("X" * length)
        version = version_for_modules(matrix.shape[0])
        if 1 <= version <= highest:
            found.setdefault(version, matrix)
        if len(found) == highest:
            break
    return found


SAMPLES = _sample_per_version()


@pytest.mark.parametrize("version", sorted(SAMPLES))
def test_mask_agrees_with_a_real_encoder(version):
    """The hard test: a genuinely encoded code has to satisfy the mask exactly.

    Catches errors in the alignment table, the separators and the position of the always-dark
    module -- all places where a sign error would otherwise go unnoticed.
    """
    matrix = SAMPLES[version]
    known_dark, known_light = structure_mask(matrix.shape[0])
    assert matrix[known_dark].all(), "a cell known to be dark is light in the real code"
    assert not matrix[known_light].any(), "a cell known to be light is dark in the real code"


def test_dark_and_light_never_overlap():
    for modules in (21, 25, 29, 33, 37, 41, 45):
        known_dark, known_light = structure_mask(modules)
        assert not (known_dark & known_light).any()


def test_mask_covers_about_a_quarter_of_the_code():
    known_dark, known_light = structure_mask(29)
    fraction = (known_dark | known_light).sum() / 29**2
    assert 0.25 < fraction < 0.35


def test_timing_detects_a_shifted_grid():
    matrix = reencode("TIMING-PROBE")
    assert timing_score(matrix) == 1.0
    shifted = np.roll(matrix, 1, axis=1)
    assert timing_score(shifted) < 0.6
