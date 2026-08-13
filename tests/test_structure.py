"""Die Strukturmaske ist das Eichmass des ganzen Verfahrens.

Ist sie falsch, misst sich alles andere an einer falschen Wahrheit -- und zwar lautlos, weil
ein falsches Eichmass zu plausiblen Zahlen fuehrt. Deshalb wird sie gegen einen unabhaengigen
Encoder geprueft und nicht gegen sich selbst.
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
def test_groesse_und_version_sind_umkehrbar(version):
    modules = modules_for_version(version)
    assert version_for_modules(modules) == version
    assert is_valid_size(modules)


def test_ungueltige_groessen_werden_erkannt():
    assert not is_valid_size(28)
    assert not is_valid_size(17)


def _beispiel_je_version(hoechste: int = 7) -> dict[int, np.ndarray]:
    """Sucht zu jeder Version einen wirklich kodierten Code.

    Die Nutzlastlaenge laesst sich nicht auf die Version zurueckrechnen -- der Encoder waehlt
    Modus und Version selbst. Also wird gesucht statt gerechnet.
    """
    gefunden: dict[int, np.ndarray] = {}
    for laenge in range(1, 400, 3):
        matrix = reencode("X" * laenge)
        version = version_for_modules(matrix.shape[0])
        if 1 <= version <= hoechste:
            gefunden.setdefault(version, matrix)
        if len(gefunden) == hoechste:
            break
    return gefunden


BEISPIELE = _beispiel_je_version()


@pytest.mark.parametrize("version", sorted(BEISPIELE))
def test_maske_stimmt_mit_echtem_encoder_ueberein(version):
    """Der harte Test: ein wirklich kodierter Code muss die Maske exakt erfuellen.

    Deckt Fehler in der Alignment-Tabelle, den Separatoren und der Lage des festen dunklen
    Moduls auf -- alles Stellen, an denen ein Vorzeichenfehler sonst unbemerkt bliebe.
    """
    matrix = BEISPIELE[version]
    known_dark, known_light = structure_mask(matrix.shape[0])
    assert matrix[known_dark].all(), "als dunkel bekannte Zelle ist im echten Code hell"
    assert not matrix[known_light].any(), "als hell bekannte Zelle ist im echten Code dunkel"


def test_dunkel_und_hell_ueberschneiden_sich_nicht():
    for modules in (21, 25, 29, 33, 37, 41, 45):
        known_dark, known_light = structure_mask(modules)
        assert not (known_dark & known_light).any()


def test_maske_deckt_ein_viertel_des_codes_ab():
    known_dark, known_light = structure_mask(29)
    anteil = (known_dark | known_light).sum() / 29**2
    assert 0.25 < anteil < 0.35


def test_timing_erkennt_verschobenes_gitter():
    matrix = reencode("TIMING-PROBE")
    assert timing_score(matrix) == 1.0
    verschoben = np.roll(matrix, 1, axis=1)
    assert timing_score(verschoben) < 0.6
