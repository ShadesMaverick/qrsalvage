"""Regression gegen das Bildkorpus in fixtures/.

Verglichen wird gegen den Hash, nicht gegen den Klartext: die Codes enthalten
Geraete-Install-Codes, und ein Testfall ist kein Grund, ein Geheimnis ins Repo zu schreiben.

Faellt hier ein Fixture um, ist das ein Befund ueber das Verfahren -- kein Anlass, die
Erwartung anzupassen.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import cv2
import pytest

from qrsalvage.core.pipeline import solve

WURZEL = Path(__file__).resolve().parents[1]
# Oeffentlich und synthetisch; jeder kann es mit scripts/make_fixtures.py reproduzieren.
FIXTURES = WURZEL / "fixtures"
# Privat und gitignoriert: echte Fotos, deren Inhalt schuetzenswert ist. Laeuft nur mit,
# wenn das Verzeichnis vorhanden ist -- ein geklontes Repo hat es nicht.
LOKAL = WURZEL / "fixtures-local"


def _faelle():
    treffer = []
    for ordner in (FIXTURES, LOKAL):
        if ordner.is_dir():
            treffer.extend(sorted(ordner.glob("*.json")))
    return treffer


@pytest.mark.regression
@pytest.mark.parametrize("meta_path", _faelle(), ids=lambda p: p.stem)
def test_fixture_wird_geloest(meta_path: Path):
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    bild = meta_path.with_suffix(".png")
    assert bild.is_file(), f"Bild zum Fixture fehlt: {bild.name}"

    img = cv2.imread(str(bild))
    assert img is not None, f"Bild nicht lesbar: {bild.name}"

    crop = tuple(meta["crop"]) if meta.get("crop") else None
    result = solve(img, crop=crop)

    assert result.solved, f"nicht geloest ({result.failure})"
    digest = hashlib.sha256(result.text.encode()).hexdigest()
    assert digest == meta["expected_sha256"], "entschluesselt, aber mit falschem Inhalt"

    if meta.get("expected_length"):
        assert len(result.text) == meta["expected_length"]
    if meta.get("qr_modules"):
        assert result.modules == meta["qr_modules"]


@pytest.mark.regression
def test_korpus_ist_nicht_leer():
    """Eine gruene Suite ohne Faelle ist keine gruene Suite."""
    assert _faelle(), "keine Fixtures vorhanden - Regression sagt nichts aus"
