"""Regression against the image corpus in fixtures/.

Comparison is against a hash, not against the plain text: real codes carry device secrets, and
a test case is no reason to write one into a repository.

If a fixture stops passing, that is a finding about the method -- not a reason to adjust the
expectation.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import cv2
import pytest

from qrsalvage.core.pipeline import solve

ROOT = Path(__file__).resolve().parents[1]
# Public and synthetic; anyone can reproduce it with scripts/make_fixtures.py.
FIXTURES = ROOT / "fixtures"
# Private and gitignored: real photographs whose content is sensitive. Only runs when the
# directory exists -- a cloned repository does not have it.
PRIVATE = ROOT / "fixtures-local"


def _cases():
    found = []
    for folder in (FIXTURES, PRIVATE):
        if folder.is_dir():
            found.extend(sorted(folder.glob("*.json")))
    return found


@pytest.mark.regression
@pytest.mark.parametrize("meta_path", _cases(), ids=lambda p: p.stem)
def test_fixture_is_solved(meta_path: Path):
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    image_path = meta_path.with_suffix(".png")
    assert image_path.is_file(), f"image for fixture missing: {image_path.name}"

    image = cv2.imread(str(image_path))
    assert image is not None, f"cannot read image: {image_path.name}"

    crop = tuple(meta["crop"]) if meta.get("crop") else None
    result = solve(image, crop=crop)

    assert result.solved, f"not solved ({result.failure})"
    digest = hashlib.sha256(result.text.encode()).hexdigest()
    assert digest == meta["expected_sha256"], "decoded, but with the wrong content"

    if meta.get("expected_length"):
        assert len(result.text) == meta["expected_length"]
    if meta.get("qr_modules"):
        assert result.modules == meta["qr_modules"]


@pytest.mark.regression
def test_the_corpus_is_not_empty():
    """A green suite with no cases in it is not a green suite."""
    assert _cases(), "no fixtures present - the regression suite proves nothing"
