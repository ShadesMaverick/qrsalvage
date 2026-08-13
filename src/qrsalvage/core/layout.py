"""Wo im Raster welches Bit liegt: Funktionsmodule, Platzierungsreihenfolge, Verschachtelung.

Dieser Teil ist reine Buchhaltung, aber Buchhaltung, bei der ein Fehler nicht auffaellt: eine
um eins verschobene Reihenfolge liefert weiterhin Codewoerter, nur eben falsche. Abgesichert
wird das nicht durch Sorgfalt, sondern durch die Umkehrung -- wer extrahiert und wieder
platziert, muss dieselbe Matrix erhalten. test_rs.py prueft genau das gegen echte Codes.
"""

from __future__ import annotations

import numpy as np

from .qrspec import (
    REMAINDER_BITS,
    block_plan,
    decode_format,
    format_bits,
    mask_bit,
)
from .structure import ALIGNMENT_CENTERS, version_for_modules


def function_mask(modules: int) -> np.ndarray:
    """Alle Module, die keine Daten tragen: Finder, Timing, Alignment, Format, Version."""
    n = modules
    version = version_for_modules(n)
    mask = np.zeros((n, n), dtype=bool)

    # Finder samt Separatoren -- jeweils ein 8x8-Feld in der Ecke
    mask[0:8, 0:8] = True
    mask[0:8, n - 8 : n] = True
    mask[n - 8 : n, 0:8] = True

    mask[6, :] = True  # Timing
    mask[:, 6] = True

    centers = ALIGNMENT_CENTERS.get(version, ())
    for ar in centers:
        for ac in centers:
            if (ar, ac) in ((6, 6), (6, n - 7), (n - 7, 6)):
                continue
            mask[ar - 2 : ar + 3, ac - 2 : ac + 3] = True

    mask[8, 0:9] = True  # Formatinformation
    mask[0:9, 8] = True
    mask[8, n - 8 : n] = True
    mask[n - 8 : n, 8] = True

    if version >= 7:  # Versionsinformation
        mask[0:6, n - 11 : n - 8] = True
        mask[n - 11 : n - 8, 0:6] = True

    return mask


def placement_order(modules: int) -> list[tuple[int, int]]:
    """Reihenfolge, in der die Datenmodule beschrieben werden.

    Zwei Spalten breit, von rechts unten nach links, Richtung wechselnd, Spalte 6 uebersprungen
    (dort liegt das senkrechte Timing-Pattern).
    """
    n = modules
    funcs = function_mask(n)
    order: list[tuple[int, int]] = []
    col = n - 1
    upward = True
    while col > 0:
        if col == 6:
            col -= 1
        for i in range(n):
            row = (n - 1 - i) if upward else i
            for c in (col, col - 1):
                if not funcs[row, c]:
                    order.append((row, c))
        col -= 2
        upward = not upward
    return order


def format_positions(modules: int) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """Die Modulstellen beider Formatkopien, aufsteigend nach Bitnummer (Bit 0 zuerst).

    Die Reihenfolge ist gegen erzwungene Fehlerkorrekturstufen geprueft: kodiert man denselben
    Text mit L, M, Q und H, muss hier genau diese Stufe wieder herauskommen, aus beiden Kopien
    und mit BCH-Abstand null. Umgekehrt nummeriert liefert dieselbe Leseroutine bei jedem Code
    einen Abstand von drei -- knapp innerhalb der Korrekturgrenze und damit gefaehrlich
    unauffaellig.
    """
    n = modules
    erste = [(r, 8) for r in range(6)] + [(7, 8), (8, 8), (8, 7)]
    erste += [(8, c) for c in range(5, -1, -1)]

    zweite = [(8, n - 1 - i) for i in range(8)]
    zweite += [(n - 7 + i, 8) for i in range(7)]
    return erste, zweite


def read_format(matrix: np.ndarray) -> tuple[str, int, int] | None:
    """Liest die Formatinformation aus beiden Kopien und nimmt die glaubwuerdigere.

    Zwei unabhaengige Kopien mit je eigener BCH-Sicherung: hier faellt ein Lesefehler auf,
    bevor er sich durch die gesamte Decodierung zieht.
    """
    erste, zweite = format_positions(matrix.shape[0])

    kandidaten = []
    for stellen in (erste, zweite):
        raw = 0
        for bit, (r, c) in enumerate(stellen):
            if matrix[r, c]:
                raw |= 1 << bit
        gelesen = decode_format(raw)
        if gelesen is not None:
            kandidaten.append(gelesen)

    if not kandidaten:
        return None
    return min(kandidaten, key=lambda t: t[2])


def write_format(matrix: np.ndarray, ecc: str, mask_pattern: int) -> None:
    """Schreibt die Formatinformation in beide Kopien und setzt das feste dunkle Modul."""
    n = matrix.shape[0]
    bits = format_bits(ecc, mask_pattern)

    for stellen in format_positions(n):
        for bit, (r, c) in enumerate(stellen):
            matrix[r, c] = bool(bits & (1 << bit))
    matrix[4 * version_for_modules(n) + 9, 8] = True


def extract_codewords(matrix: np.ndarray, mask_pattern: int) -> list[int]:
    """Liest die Datenmodule in Platzierungsreihenfolge und entmaskiert sie."""
    order = placement_order(matrix.shape[0])
    bits: list[int] = []
    for r, c in order:
        wert = bool(matrix[r, c])
        if mask_bit(mask_pattern, r, c):
            wert = not wert
        bits.append(int(wert))

    codewords: list[int] = []
    for i in range(0, len(bits) - 7, 8):
        wert = 0
        for b in bits[i : i + 8]:
            wert = (wert << 1) | b
        codewords.append(wert)
    return codewords


def place_codewords(matrix: np.ndarray, codewords: list[int], mask_pattern: int) -> None:
    """Umkehrung von :func:`extract_codewords`, schreibt in die Matrix zurueck."""
    n = matrix.shape[0]
    order = placement_order(n)
    bits: list[int] = []
    for wert in codewords:
        bits.extend((wert >> shift) & 1 for shift in range(7, -1, -1))
    bits.extend([0] * REMAINDER_BITS.get(version_for_modules(n), 0))

    for (r, c), bit in zip(order, bits, strict=False):
        wert = bool(bit)
        if mask_bit(mask_pattern, r, c):
            wert = not wert
        matrix[r, c] = wert


def deinterleave(codewords: list[int], version: int, ecc: str) -> list[list[int]]:
    """Loest die Verschachtelung auf und liefert je Block [Daten..., Pruefzeichen...].

    QR verteilt die Codewoerter reihum ueber die Bloecke, damit ein zusammenhaengender Schaden
    im Bild sich auf alle Bloecke verteilt statt einen zu zerstoeren. Fuer uns heisst das:
    unsichere Zellen muessen denselben Weg zurueckgehen, sonst zeigen die Auslassungen auf die
    falschen Stellen.
    """
    plan = block_plan(version, ecc)
    sizes = plan.block_sizes()
    bloecke: list[list[int]] = [[] for _ in sizes]

    pos = 0
    for i in range(max(sizes)):
        for b, size in enumerate(sizes):
            if i < size:
                bloecke[b].append(codewords[pos])
                pos += 1

    for _ in range(plan.ec_per_block):
        for b in range(len(sizes)):
            bloecke[b].append(codewords[pos])
            pos += 1

    return bloecke


def interleave(bloecke: list[list[int]], version: int, ecc: str) -> list[int]:
    """Umkehrung von :func:`deinterleave`."""
    plan = block_plan(version, ecc)
    sizes = plan.block_sizes()
    out: list[int] = []

    for i in range(max(sizes)):
        for b, size in enumerate(sizes):
            if i < size:
                out.append(bloecke[b][i])

    for i in range(plan.ec_per_block):
        for b, size in enumerate(sizes):
            out.append(bloecke[b][size + i])

    return out


def codeword_positions(matrix_size: int, version: int, ecc: str) -> list[list[list[int]]]:
    """Welche Modulpositionen (als flache Indizes) gehoeren zu welchem Codewort welchen Blocks?

    Das ist die Bruecke zwischen Bildunsicherheit und Decoder: eine wackelige Zelle wird darueber
    zu einer Auslassung an genau der richtigen Stelle im richtigen Block.
    """
    order = placement_order(matrix_size)
    plan = block_plan(version, ecc)
    sizes = plan.block_sizes()

    # Reihenfolge der Codewoerter im Strom -> (Block, Index im Block)
    zuordnung: list[tuple[int, int]] = []
    for i in range(max(sizes)):
        for b, size in enumerate(sizes):
            if i < size:
                zuordnung.append((b, i))
    for i in range(plan.ec_per_block):
        for b, size in enumerate(sizes):
            zuordnung.append((b, size + i))

    positionen: list[list[list[int]]] = [
        [[] for _ in range(size + plan.ec_per_block)] for size in sizes
    ]
    for stream_index, (block, index) in enumerate(zuordnung):
        for bit in range(8):
            stelle = stream_index * 8 + bit
            if stelle >= len(order):
                break
            r, c = order[stelle]
            positionen[block][index].append(r * matrix_size + c)
    return positionen
