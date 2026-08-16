"""Several photographs of one code, fused into one reading.

The point of this path is the case no single image can reach, so the central test asserts both
halves: every photograph fails on its own, and together they succeed. Without the first half the
test would pass for the wrong reason and keep passing after the fusion stopped working.
"""

from __future__ import annotations

import json
from dataclasses import replace

import numpy as np
import pytest

from qrsalvage.core.decoding import reencode
from qrsalvage.core.ensemble import fuse_images
from qrsalvage.core.pipeline import solve, solve_many
from qrsalvage.core.structure import structure_mask
from qrsalvage.export import to_json
from qrsalvage.synth import Damage, render_photo

TEXT = "QRSALVAGE-FUSION-CASE-" + "0123456789" * 3
# Same length and character set, so it encodes to the same version and the only
# difference between the two matrices is the payload itself.
OTHER = "QRSALVAGE-FUSION-ELSE-" + "9876543210" * 3
BASE = Damage(contrast=0.18, curvature=0.30, module_px=8.0)

# A stain, not low contrast. Damage that hits every cell equally spoils all three photographs
# the same way and leaves the fusion nothing to play off -- searched, and at no contrast level
# does fusing three rescue what three cannot do individually. A stain sits somewhere else in
# every photograph, so each loses a different part of the code while the others still hold it.
# That is the case this path exists for, and these values were found by searching for one the
# single-image path provably cannot solve.
HARD_STAIN = 0.50
HARD_GROUP = 7


def photographs(stain: float, group: int, count: int = 3) -> list[np.ndarray]:
    """Several photographs of one code, each with its own angle, curvature, light and stain.

    Varying only the noise seed would not do. The dominant error is the grid, and every image
    taken from the same angle inherits the same one -- which is exactly the correlated-members
    trap that ensemble.py measured and documented for its own two variants.
    """
    matrix = reencode(TEXT)
    rng = np.random.default_rng(group)
    images = []
    for index in range(count):
        damage = replace(
            BASE,
            stain=stain,
            rotation_deg=float(rng.uniform(-8.0, 8.0)),
            curvature=float(np.clip(BASE.curvature * rng.uniform(0.7, 1.3), 0.05, 1.1)),
            glare=float(np.clip(BASE.glare * rng.uniform(0.5, 1.5), 0.0, 0.9)),
        )
        images.append(render_photo(matrix, damage, seed=group * 10 + index))
    return images


def _posterior(matrix: np.ndarray, confidence: float = 0.9) -> np.ndarray:
    return np.where(matrix, confidence, 1.0 - confidence)


@pytest.fixture(scope="module")
def hard_case():
    """The three photographs, and the fused result. Shared: solving them is the slow part."""
    images = photographs(HARD_STAIN, HARD_GROUP)
    return images, solve_many(images)


def test_several_photographs_solve_what_none_of_them_can_alone(hard_case):
    images, result = hard_case

    alone = [solve(image, budget=4000).text for image in images]
    assert alone == [None, None, None], (
        f"precondition broken: {sum(t == TEXT for t in alone)} image(s) solved on their own, "
        "so this case no longer tests the fusion"
    )

    assert result.solved
    assert result.text == TEXT
    assert result.fusion is not None
    assert result.fusion.members == 3
    assert result.fusion.disagreeing > 0, (
        "identical readings would mean the photographs are not independent"
    )


def test_the_json_export_records_what_the_result_was_built_from(hard_case):
    """A fused payload rests on evidence a single photograph does not have.

    Whoever reads the export decides whether to trust an install code on the strength of it, and
    "three photographs, disagreeing on this many cells" is part of that case. Left out, a fused
    result is indistinguishable from a clean single read.
    """
    _, result = hard_case
    report = json.loads(to_json(result))

    assert report["fusion"]["photographs"] == 3
    assert report["fusion"]["cells_in_dispute"] > 0
    assert report["fusion"]["rejected"] == []


def test_a_photograph_that_can_be_read_alone_wins_immediately():
    """The cheapest correct answer needs no argument about how a fusion was formed."""
    easy = render_photo(reencode(TEXT), replace(BASE, contrast=0.30), seed=1)
    result = solve_many([easy, *photographs(HARD_STAIN, HARD_GROUP, count=2)])

    assert result.text == TEXT
    assert result.fusion is None, "a solved single image must not be fused with anything"


def test_a_mirrored_photograph_is_turned_back_rather_than_averaged_in():
    """Nothing upstream can catch this, so the fusion has to.

    Transposing a QR code leaves the finders, the separators, both timing patterns and the
    alignment patterns exactly where they were. Only the single always-dark module moves, so a
    code photographed in a mirror fits its grid, scores one wrong known cell in a few hundred,
    and arrives here inside out.
    """
    matrix = reencode(TEXT)
    known_dark, known_light = structure_mask(matrix.shape[0])
    upright = _posterior(matrix)

    consensus = fuse_images([upright, upright.T.copy()], known_dark, known_light)

    assert consensus.members == 2
    assert consensus.mirrored == (1,)
    assert consensus.rejected == ()
    np.testing.assert_allclose(consensus.posterior, upright)


def test_a_photograph_of_a_different_code_is_dropped():
    matrix = reencode(TEXT)
    known_dark, known_light = structure_mask(matrix.shape[0])
    other = reencode(OTHER)
    assert other.shape == matrix.shape, "precondition: same version, so only the payload differs"

    consensus = fuse_images([_posterior(matrix), _posterior(other)], known_dark, known_light)

    assert consensus.rejected == (1,)
    assert consensus.members == 1
    np.testing.assert_allclose(consensus.posterior, _posterior(matrix))


def test_agreement_separates_the_same_code_from_a_different_one():
    """The threshold has to sit between chance and a genuine second photograph."""
    matrix = reencode(TEXT)
    known_dark, known_light = structure_mask(matrix.shape[0])
    other = reencode(OTHER)

    # A second photograph of the same code: a handful of cells read wrong.
    noisy = _posterior(matrix)
    rng = np.random.default_rng(0)
    free = np.flatnonzero(~(known_dark | known_light).ravel())
    for cell in rng.choice(free, size=12, replace=False):
        noisy.ravel()[cell] = 1.0 - noisy.ravel()[cell]

    same = fuse_images([_posterior(matrix), noisy], known_dark, known_light)
    different = fuse_images([_posterior(matrix), _posterior(other)], known_dark, known_light)

    assert same.agreement[1] > 0.9
    assert different.rejected == (1,)


def test_one_photograph_is_passed_through_untouched():
    matrix = reencode(TEXT)
    known_dark, known_light = structure_mask(matrix.shape[0])
    single = _posterior(matrix)

    consensus = fuse_images([single], known_dark, known_light)

    assert consensus.members == 1
    assert not consensus.fused
    np.testing.assert_allclose(consensus.posterior, single)


def test_solve_many_with_one_image_is_plain_solve():
    photo = render_photo(reencode(TEXT), replace(BASE, contrast=0.30), seed=3)

    single = solve(photo)
    many = solve_many([photo])

    assert many.text == single.text
    assert many.wrong_known == single.wrong_known
    assert many.fusion is None


def test_an_unknown_fusion_rule_is_refused():
    matrix = reencode(TEXT)
    known_dark, known_light = structure_mask(matrix.shape[0])
    with pytest.raises(ValueError, match="unknown fusion rule"):
        fuse_images(
            [_posterior(matrix), _posterior(matrix)], known_dark, known_light, rule="average"
        )
