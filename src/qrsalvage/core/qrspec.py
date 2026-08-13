"""Die Tabellen und Regeln aus ISO/IEC 18004, soweit wir sie zum Reparieren brauchen.

Tabellen sind die fehleranfaelligste Art von Code: ein vertauschter Zahlenwert erzeugt keinen
Absturz, sondern stille Falschheit. Deshalb ist jede Tabelle hier durch eine Konsistenzregel
abgesichert, die sich pruefen laesst -- die Summe aus Daten- und Pruefzeichen aller Bloecke
muss die Gesamtzahl der Codewoerter einer Version ergeben. test_rs.py prueft das fuer alle
Eintraege, und zusaetzlich wird der ganze Weg gegen einen echten Encoder gefahren.
"""

from __future__ import annotations

from dataclasses import dataclass

# Gesamtzahl der Codewoerter (Daten + Pruefzeichen) je Version.
TOTAL_CODEWORDS: dict[int, int] = {
    1: 26,
    2: 44,
    3: 70,
    4: 100,
    5: 134,
    6: 172,
    7: 196,
    8: 242,
    9: 292,
    10: 346,
}

# Restbits nach den Codewoertern, die beim Platzieren mitlaufen und nichts bedeuten.
REMAINDER_BITS: dict[int, int] = {1: 0, 2: 7, 3: 7, 4: 7, 5: 7, 6: 7, 7: 0, 8: 0, 9: 0, 10: 0}

ECC_LEVELS = ("L", "M", "Q", "H")

# Bitmuster der Fehlerkorrekturstufe in der Formatinformation.
ECC_BITS: dict[str, int] = {"L": 0b01, "M": 0b00, "Q": 0b11, "H": 0b10}
BITS_TO_ECC: dict[int, str] = {v: k for k, v in ECC_BITS.items()}


@dataclass(frozen=True)
class BlockPlan:
    """Blockaufteilung einer Version-Stufen-Kombination."""

    ec_per_block: int
    groups: tuple[tuple[int, int], ...]  # (Anzahl Bloecke, Datencodewoerter je Block)

    @property
    def blocks(self) -> int:
        return sum(count for count, _ in self.groups)

    @property
    def data_codewords(self) -> int:
        return sum(count * size for count, size in self.groups)

    @property
    def total_codewords(self) -> int:
        return self.data_codewords + self.blocks * self.ec_per_block

    def block_sizes(self) -> list[int]:
        sizes: list[int] = []
        for count, size in self.groups:
            sizes.extend([size] * count)
        return sizes


# ISO/IEC 18004 Tabelle 9. Aufbau: (Pruefzeichen je Block, ((Bloecke, Datenzeichen), ...))
BLOCK_PLANS: dict[tuple[int, str], BlockPlan] = {
    (1, "L"): BlockPlan(7, ((1, 19),)),
    (1, "M"): BlockPlan(10, ((1, 16),)),
    (1, "Q"): BlockPlan(13, ((1, 13),)),
    (1, "H"): BlockPlan(17, ((1, 9),)),
    (2, "L"): BlockPlan(10, ((1, 34),)),
    (2, "M"): BlockPlan(16, ((1, 28),)),
    (2, "Q"): BlockPlan(22, ((1, 22),)),
    (2, "H"): BlockPlan(28, ((1, 16),)),
    (3, "L"): BlockPlan(15, ((1, 55),)),
    (3, "M"): BlockPlan(26, ((1, 44),)),
    (3, "Q"): BlockPlan(18, ((2, 17),)),
    (3, "H"): BlockPlan(22, ((2, 13),)),
    (4, "L"): BlockPlan(20, ((1, 80),)),
    (4, "M"): BlockPlan(18, ((2, 32),)),
    (4, "Q"): BlockPlan(26, ((2, 24),)),
    (4, "H"): BlockPlan(16, ((4, 9),)),
    (5, "L"): BlockPlan(26, ((1, 108),)),
    (5, "M"): BlockPlan(24, ((2, 43),)),
    (5, "Q"): BlockPlan(18, ((2, 15), (2, 16))),
    (5, "H"): BlockPlan(22, ((2, 11), (2, 12))),
    (6, "L"): BlockPlan(18, ((2, 68),)),
    (6, "M"): BlockPlan(16, ((4, 27),)),
    (6, "Q"): BlockPlan(24, ((4, 19),)),
    (6, "H"): BlockPlan(28, ((4, 15),)),
    (7, "L"): BlockPlan(20, ((2, 78),)),
    (7, "M"): BlockPlan(18, ((4, 31),)),
    (7, "Q"): BlockPlan(18, ((2, 14), (4, 15))),
    (7, "H"): BlockPlan(26, ((4, 13), (1, 14))),
    (8, "L"): BlockPlan(24, ((2, 97),)),
    (8, "M"): BlockPlan(22, ((2, 38), (2, 39))),
    (8, "Q"): BlockPlan(22, ((4, 18), (2, 19))),
    (8, "H"): BlockPlan(26, ((4, 14), (2, 15))),
    (9, "L"): BlockPlan(30, ((2, 116),)),
    (9, "M"): BlockPlan(22, ((3, 36), (2, 37))),
    (9, "Q"): BlockPlan(20, ((4, 16), (4, 17))),
    (9, "H"): BlockPlan(24, ((4, 12), (4, 13))),
    (10, "L"): BlockPlan(18, ((2, 68), (2, 69))),
    (10, "M"): BlockPlan(26, ((4, 43), (1, 44))),
    (10, "Q"): BlockPlan(24, ((6, 19), (2, 20))),
    (10, "H"): BlockPlan(28, ((6, 15), (2, 16))),
}


def block_plan(version: int, ecc: str) -> BlockPlan:
    try:
        return BLOCK_PLANS[(version, ecc)]
    except KeyError as exc:
        raise KeyError(f"keine Blockaufteilung fuer Version {version}, Stufe {ecc}") from exc


# --- Maskierung -----------------------------------------------------------------------

MASK_COUNT = 8


def mask_bit(pattern: int, row: int, col: int) -> bool:
    """Liefert True, wenn die Maske dieses Modul umkehrt."""
    if pattern == 0:
        return (row + col) % 2 == 0
    if pattern == 1:
        return row % 2 == 0
    if pattern == 2:
        return col % 3 == 0
    if pattern == 3:
        return (row + col) % 3 == 0
    if pattern == 4:
        return (row // 2 + col // 3) % 2 == 0
    if pattern == 5:
        return (row * col) % 2 + (row * col) % 3 == 0
    if pattern == 6:
        return ((row * col) % 2 + (row * col) % 3) % 2 == 0
    if pattern == 7:
        return ((row + col) % 2 + (row * col) % 3) % 2 == 0
    raise ValueError(f"unbekanntes Maskenmuster: {pattern}")


# --- Formatinformation ----------------------------------------------------------------

FORMAT_GENERATOR = 0b101_0011_0111
FORMAT_MASK = 0b101_0100_0001_0010


def format_bits(ecc: str, mask: int) -> int:
    """Erzeugt die 15 Bit Formatinformation samt BCH-Pruefteil und Maskierung."""
    data = (ECC_BITS[ecc] << 3) | mask
    value = data << 10
    for i in range(4, -1, -1):
        if value & (1 << (i + 10)):
            value ^= FORMAT_GENERATOR << i
    return ((data << 10) | value) ^ FORMAT_MASK


ALL_FORMATS: dict[int, tuple[str, int]] = {
    format_bits(ecc, mask): (ecc, mask) for ecc in ECC_LEVELS for mask in range(MASK_COUNT)
}


def decode_format(raw: int) -> tuple[str, int, int] | None:
    """Findet zu 15 gelesenen Bits die naechstliegende gueltige Formatinformation.

    Liefert (Stufe, Maske, Hamming-Abstand) oder None, wenn der Abstand zu gross ist. Der
    BCH-Code der Formatinformation korrigiert bis zu drei Bitfehler -- er ist damit die erste
    Stelle im ganzen Verfahren, an der sich eine Lesung unabhaengig pruefen laesst.
    """
    beste: tuple[str, int, int] | None = None
    for gueltig, (ecc, mask) in ALL_FORMATS.items():
        abstand = bin(gueltig ^ raw).count("1")
        if beste is None or abstand < beste[2]:
            beste = (ecc, mask, abstand)
    if beste is None or beste[2] > 3:
        return None
    return beste
