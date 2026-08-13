"""Unsichere Zellen als Auslassungen an Reed-Solomon uebergeben.

Hier schliesst sich die Kette, die in ensemble.py offen geblieben ist. Die Tastsuche kippt
hoechstens gut zwanzig Zellen und probiert Kombinationen durch; Reed-Solomon dagegen bekommt
gesagt, *wo* es unsicher ist, und rechnet die richtigen Werte in einem Schritt aus. Bei t
Pruefzeichen sind t Auslassungen reparierbar gegenueber nur t/2 Fehlern -- die Verdopplung,
wegen der die dreiwertige Matrix ueberhaupt existiert.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from .galois import ReedSolomonError, correct_block
from .layout import (
    codeword_positions,
    deinterleave,
    extract_codewords,
    interleave,
    place_codewords,
    read_format,
    write_format,
)
from .qrspec import block_plan
from .structure import version_for_modules


@dataclass
class RepairResult:
    """Was die Reparatur ergeben hat -- auch im Misserfolg auskunftsfaehig."""

    matrix: np.ndarray | None
    ecc: str | None = None
    mask: int | None = None
    format_distance: int | None = None
    blocks: int = 0
    blocks_repaired: int = 0
    errors_corrected: int = 0
    erasures_used: int = 0
    per_block: list[str] = field(default_factory=list)
    failure: str | None = None

    @property
    def ok(self) -> bool:
        return self.matrix is not None


def _codeword_reliability(posterior: np.ndarray, positions: list[int]) -> float:
    """Verlaesslichkeit eines Codeworts: sein schwaechstes Bit.

    Nicht der Mittelwert. Ein Codewort ist bereits falsch, wenn ein einziges seiner acht Bits
    kippt -- ein Mittelwert wuerde sieben sichere Bits gegen ein wackeliges aufrechnen und das
    Codewort faelschlich als solide ausweisen.
    """
    flach = posterior.ravel()
    return min(abs(float(flach[p]) - 0.5) for p in positions)


def repair(
    matrix: np.ndarray,
    posterior: np.ndarray | None = None,
    erasures_per_block: int = 0,
) -> RepairResult:
    """Ein Reparaturversuch mit genau `erasures_per_block` Auslassungen je Block.

    Wichtig und nicht offensichtlich: Bei so vielen Auslassungen wie Pruefzeichen findet
    Reed-Solomon *immer* eine gueltige Loesung. Gueltig heisst aber nicht richtig -- liegen
    die echten Fehler ausserhalb der ausgelassenen Stellen, kommt ein sauber gerechnetes,
    falsches Codewort heraus. Diese Funktion kann das nicht bemerken; dafuer gibt es
    :func:`repair_progressive`, das jeden Versuch von aussen widerlegen laesst.
    """
    n = int(matrix.shape[0])
    version = version_for_modules(n)

    gelesen = read_format(matrix)
    if gelesen is None:
        return RepairResult(matrix=None, failure="Formatinformation nicht lesbar")
    ecc, mask, abstand = gelesen

    try:
        plan = block_plan(version, ecc)
    except KeyError as exc:
        return RepairResult(matrix=None, ecc=ecc, mask=mask, failure=str(exc))

    codewords = extract_codewords(matrix, mask)[: plan.total_codewords]
    if len(codewords) < plan.total_codewords:
        return RepairResult(matrix=None, ecc=ecc, mask=mask, failure="zu wenige Codewoerter")

    bloecke = deinterleave(codewords, version, ecc)
    positionen = codeword_positions(n, version, ecc)

    repariert: list[list[int]] = []
    fehler_gesamt = 0
    auslassungen_gesamt = 0
    reparierte_bloecke = 0
    bericht: list[str] = []

    for b, block in enumerate(bloecke):
        nsym = plan.ec_per_block

        erasures: list[int] = []
        if posterior is not None and erasures_per_block > 0:
            bewertet = [
                (_codeword_reliability(posterior, positionen[b][i]), i) for i in range(len(block))
            ]
            erasures = [i for _, i in sorted(bewertet)[:erasures_per_block]]

        try:
            ergebnis = correct_block(block, nsym, erasures)
        except (ReedSolomonError, ZeroDivisionError):
            ergebnis = None

        if ergebnis is None:
            bericht.append(f"Block {b}: nicht reparierbar")
            return RepairResult(
                matrix=None,
                ecc=ecc,
                mask=mask,
                format_distance=abstand,
                blocks=len(bloecke),
                per_block=bericht,
                failure=f"Block {b} von {len(bloecke)} liess sich nicht reparieren",
            )

        block_neu, fehlerstellen, benutzte = ergebnis
        repariert.append(block_neu)
        fehler_gesamt += len(fehlerstellen)
        auslassungen_gesamt += len(benutzte)
        if fehlerstellen or benutzte:
            reparierte_bloecke += 1
        bericht.append(f"Block {b}: {len(fehlerstellen)} Fehler, {len(benutzte)} Auslassungen")

    strom = interleave(repariert, version, ecc)
    neu = np.array(matrix, dtype=bool, copy=True)
    place_codewords(neu, strom, mask)
    write_format(neu, ecc, mask)

    return RepairResult(
        matrix=neu,
        ecc=ecc,
        mask=mask,
        format_distance=abstand,
        blocks=len(bloecke),
        blocks_repaired=reparierte_bloecke,
        errors_corrected=fehler_gesamt,
        erasures_used=auslassungen_gesamt,
        per_block=bericht,
    )


def repair_progressive(
    matrix: np.ndarray,
    posterior: np.ndarray | None = None,
    verify: Callable[[np.ndarray], bool] | None = None,
    max_erasure_fraction: float = 1.0,
) -> RepairResult:
    """Steigert die Zahl der Auslassungen, bis eine Loesung entsteht, die standhaelt.

    Das Aufsteigen ist nicht Bequemlichkeit, sondern notwendig: mehr Auslassungen erkaufen
    Reichweite mit Eindeutigkeit. Bei wenigen ist eine gefundene Loesung fast sicher die
    richtige, bei so vielen wie Pruefzeichen ist sie beliebig. Deshalb wird die sparsamste
    genommen, die `verify` uebersteht -- ohne diesen Widerspruch von aussen liefert das
    Verfahren am Ende immer etwas und meistens Unsinn.
    """
    kopf = read_format(matrix)
    if kopf is None:
        return RepairResult(matrix=None, failure="Formatinformation nicht lesbar")
    ecc, _, _ = kopf
    try:
        plan = block_plan(version_for_modules(int(matrix.shape[0])), ecc)
    except KeyError as exc:
        return RepairResult(matrix=None, ecc=ecc, failure=str(exc))

    grenze = int(plan.ec_per_block * max_erasure_fraction)
    letzte = RepairResult(matrix=None, ecc=ecc, failure="kein Versuch unternommen")

    for anzahl in range(0, grenze + 1):
        ergebnis = repair(matrix, posterior=posterior, erasures_per_block=anzahl)
        if not ergebnis.ok:
            letzte = ergebnis
            continue
        if verify is None or verify(ergebnis.matrix):
            return ergebnis
        letzte = RepairResult(
            matrix=None,
            ecc=ergebnis.ecc,
            mask=ergebnis.mask,
            format_distance=ergebnis.format_distance,
            blocks=ergebnis.blocks,
            failure=f"{anzahl} Auslassungen ergaben ein gueltiges, aber nicht lesbares Ergebnis",
        )
        if posterior is None:
            break  # ohne Unsicherheitsangabe bringt mehr Auslassen nichts Neues
    return letzte
