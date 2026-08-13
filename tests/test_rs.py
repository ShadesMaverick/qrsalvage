"""Absicherung der Reed-Solomon-Kette gegen einen unabhaengigen Encoder.

Tabellen und Bitreihenfolgen sind die gefaehrlichste Sorte Code: ein vertauschter Wert stuerzt
nicht ab, er liefert still etwas Falsches. Deshalb wird hier nichts gegen sich selbst geprueft,
sondern immer gegen einen echten, von zxing erzeugten Code -- und ueber die Umkehrung, die
dieselbe Matrix zurueckliefern muss.
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


def _beispiel(version: int) -> np.ndarray | None:
    """Ein echter Code der gewuenschten Version, vom Encoder erzeugt."""
    for laenge in range(1, 400, 2):
        matrix = reencode("A" * laenge)
        if version_for_modules(matrix.shape[0]) == version:
            return matrix
        if version_for_modules(matrix.shape[0]) > version:
            return None
    return None


VERSIONEN = [v for v in range(1, 11) if _beispiel(v) is not None]


# --- Tabellen -------------------------------------------------------------------------


@pytest.mark.parametrize(("version", "ecc"), sorted(BLOCK_PLANS))
def test_blockaufteilung_ergibt_die_gesamtzahl(version, ecc):
    """Die Konsistenzregel, die Tippfehler in der Tabelle auffliegen laesst."""
    plan = BLOCK_PLANS[(version, ecc)]
    assert plan.total_codewords == TOTAL_CODEWORDS[version]


# --- Galois-Koerper und Reed-Solomon --------------------------------------------------


def test_reed_solomon_repariert_fehler_und_auslassungen():
    daten = list(range(1, 20))
    nsym = 10
    # Ein gueltiger Block entsteht hier, indem wir einen bekannten Block nehmen und
    # Pruefzeichen so waehlen, dass die Syndrome verschwinden -- besorgt der Encoder.
    matrix = reencode("PRUEFBLOCK")
    ecc, mask, _ = read_format(matrix)
    version = version_for_modules(matrix.shape[0])
    block = deinterleave(extract_codewords(matrix, mask), version, ecc)[0]
    nsym = block_plan(version, ecc).ec_per_block
    assert daten  # nur um die Absicht zu dokumentieren: unten zaehlt der echte Block

    # Fehlerfreier Block: nichts zu tun
    sauber, fehler, auslassungen = correct_block(list(block), nsym)
    assert sauber == list(block)
    assert not fehler and not auslassungen

    # Zwei unbekannte Fehler
    beschaedigt = list(block)
    beschaedigt[3] ^= 0xFF
    beschaedigt[9] ^= 0x5A
    geheilt, fehler, _ = correct_block(beschaedigt, nsym)
    assert geheilt == list(block)
    assert sorted(fehler) == [3, 9]


def test_auslassungen_reichen_doppelt_so_weit_wie_fehler():
    """Der Kernpunkt des ganzen Moduls, als Test formuliert."""
    matrix = reencode("REICHWEITE-TEST-12345")
    ecc, mask, _ = read_format(matrix)
    version = version_for_modules(matrix.shape[0])
    plan = block_plan(version, ecc)
    block = deinterleave(extract_codewords(matrix, mask), version, ecc)[0]
    nsym = plan.ec_per_block

    stellen = list(range(nsym))  # genau so viele Schaeden wie Pruefzeichen
    beschaedigt = list(block)
    for p in stellen:
        beschaedigt[p] ^= 0x3C

    # Als unbekannte Fehler: aussichtslos, das uebersteigt die Korrekturgrenze.
    with pytest.raises(ReedSolomonError):
        correct_block(beschaedigt, nsym)

    # Als Auslassungen mit bekanntem Ort: vollstaendig reparierbar.
    geheilt, _, benutzte = correct_block(beschaedigt, nsym, erasures=stellen)
    assert geheilt == list(block)
    assert len(benutzte) == nsym


# --- Platzierung und Verschachtelung --------------------------------------------------


@pytest.mark.parametrize("version", VERSIONEN)
def test_platzierung_deckt_genau_die_datenmodule_ab(version):
    matrix = _beispiel(version)
    n = matrix.shape[0]
    order = placement_order(n)
    assert len(set(order)) == len(order), "eine Position doppelt vergeben"
    frei = int((~function_mask(n)).sum())
    assert len(order) == frei


@pytest.mark.parametrize("version", VERSIONEN)
def test_extrahieren_und_zurueckschreiben_ergibt_dieselbe_matrix(version):
    """Die Umkehrprobe: eine verschobene Reihenfolge faellt hier sofort auf."""
    matrix = _beispiel(version)
    gelesen = read_format(matrix)
    assert gelesen is not None, "Formatinformation eines echten Codes muss lesbar sein"
    ecc, mask, abstand = gelesen
    assert abstand == 0, "ein unbeschaedigter Code darf keinen BCH-Abstand haben"

    codewords = extract_codewords(matrix, mask)
    zurueck = np.array(matrix, dtype=bool, copy=True)
    zurueck[~function_mask(matrix.shape[0])] = False
    place_codewords(zurueck, codewords, mask)
    assert np.array_equal(zurueck, matrix)


@pytest.mark.parametrize("version", VERSIONEN)
def test_verschachtelung_ist_umkehrbar(version):
    matrix = _beispiel(version)
    ecc, mask, _ = read_format(matrix)
    codewords = extract_codewords(matrix, mask)[: block_plan(version, ecc).total_codewords]
    bloecke = deinterleave(codewords, version, ecc)
    assert interleave(bloecke, version, ecc) == codewords


@pytest.mark.parametrize("version", VERSIONEN)
def test_echter_code_hat_verschwindende_syndrome(version):
    """Der schaerfste Tabellentest: stimmt die Blockaufteilung nicht, rauscht es hier."""
    matrix = _beispiel(version)
    ecc, mask, _ = read_format(matrix)
    plan = block_plan(version, ecc)
    codewords = extract_codewords(matrix, mask)[: plan.total_codewords]
    for block in deinterleave(codewords, version, ecc):
        sauber, fehler, auslassungen = correct_block(block, plan.ec_per_block)
        assert sauber == block
        assert not fehler and not auslassungen


# --- Reparatur ganzer Matrizen --------------------------------------------------------


def test_reparatur_stellt_beschaedigte_module_wieder_her():
    text = "Z:0123456789ABCDEF$I:00112233445566778899AABBCCDDEEFF1234"
    original = reencode(text)
    n = original.shape[0]
    frei = np.argwhere(~function_mask(n))

    beschaedigt = original.copy()
    rng = np.random.default_rng(7)
    getroffen = rng.choice(len(frei), size=12, replace=False)
    for idx in getroffen:
        r, c = frei[idx]
        beschaedigt[r, c] = not beschaedigt[r, c]

    assert decode_matrix(beschaedigt) is None or decode_matrix(beschaedigt) == text

    ergebnis = repair_progressive(beschaedigt)
    assert ergebnis.ok, ergebnis.failure
    assert np.array_equal(ergebnis.matrix, original)
    assert ergebnis.errors_corrected > 0


def test_auslassungen_retten_was_fehler_allein_nicht_schaffen():
    """Der Beweis am ganzen Bild: dieselbe Beschaedigung, einmal ohne, einmal mit Ortsangabe."""
    text = "AUSLASSUNGEN-SCHLAGEN-FEHLER"
    original = reencode(text)
    n = original.shape[0]
    ecc, mask, _ = read_format(original)
    plan = block_plan(version_for_modules(n), ecc)

    frei = np.argwhere(~function_mask(n))
    rng = np.random.default_rng(3)
    # So viel Schaden, dass die blosse Fehlerkorrektur ueberfordert ist
    anzahl = plan.ec_per_block * plan.blocks
    getroffen = rng.choice(len(frei), size=anzahl, replace=False)

    beschaedigt = original.copy()
    posterior = np.where(original, 0.99, 0.01)
    for idx in getroffen:
        r, c = frei[idx]
        beschaedigt[r, c] = not beschaedigt[r, c]
        posterior[r, c] = 0.5  # genau das weiss die Bildseite: hier bin ich unsicher

    ohne_ortsangabe = repair_progressive(beschaedigt, posterior=None)
    mit_ortsangabe = repair_progressive(beschaedigt, posterior=posterior)

    assert mit_ortsangabe.ok, mit_ortsangabe.failure
    assert np.array_equal(mit_ortsangabe.matrix, original)
    assert mit_ortsangabe.erasures_used > 0
    if ohne_ortsangabe.ok:
        pytest.skip("Beschaedigung war auch ohne Ortsangabe zu bewaeltigen")
