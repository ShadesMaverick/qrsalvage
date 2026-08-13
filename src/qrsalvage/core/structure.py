"""Was der QR-Standard festlegt, bevor ein einziges Datenbit gelesen wird.

Diese Zellen sind das Eichmass des ganzen Verfahrens: ihr Wert ist bekannt, also laesst sich
an ihnen messen, ob Gitter, Version und Helligkeitsmodell stimmen. Ohne sie muesste man raten
und haette kein Mass dafuer, wie gut man geraten hat.
"""

from __future__ import annotations

import numpy as np

# Zentren der Alignment-Patterns je Version (ISO/IEC 18004, Tabelle E.1).
ALIGNMENT_CENTERS: dict[int, tuple[int, ...]] = {
    1: (),
    2: (6, 18),
    3: (6, 22),
    4: (6, 26),
    5: (6, 30),
    6: (6, 34),
    7: (6, 22, 38),
    8: (6, 24, 42),
    9: (6, 26, 46),
    10: (6, 28, 50),
}


def modules_for_version(version: int) -> int:
    """Kantenlaenge in Modulen."""
    return 4 * version + 17


def version_for_modules(modules: int) -> int:
    """Umkehrung von :func:`modules_for_version`."""
    return (modules - 17) // 4


def is_valid_size(modules: int) -> bool:
    version = version_for_modules(modules)
    return version >= 1 and modules_for_version(version) == modules


def structure_mask(modules: int) -> tuple[np.ndarray, np.ndarray]:
    """Liefert (bekannt_dunkel, bekannt_hell) fuer eine Codegroesse.

    Enthalten sind Finder, Separatoren, beide Timing-Reihen, die Alignment-Patterns und das
    feste dunkle Modul. Format- und Versionsinformation bleiben aussen vor: die tragen Inhalt
    und duerfen deshalb nicht als bekannt gelten.
    """
    n = modules
    dark = np.zeros((n, n), dtype=bool)
    light = np.zeros((n, n), dtype=bool)

    for r0, c0 in ((0, 0), (0, n - 7), (n - 7, 0)):
        for i in range(7):
            for j in range(7):
                ring = i in (0, 6) or j in (0, 6)
                core = 2 <= i <= 4 and 2 <= j <= 4
                target = dark if (ring or core) else light
                target[r0 + i, c0 + j] = True
        # Separator: der L-foermige helle Streifen rund um den Finder
        for r in range(r0 - 1, r0 + 8):
            for c in range(c0 - 1, c0 + 8):
                if not (0 <= r < n and 0 <= c < n):
                    continue
                if r0 <= r < r0 + 7 and c0 <= c < c0 + 7:
                    continue
                light[r, c] = True

    for idx in range(8, n - 8):
        target = dark if idx % 2 == 0 else light
        target[6, idx] = True
        target[idx, 6] = True

    version = version_for_modules(n)
    centers = ALIGNMENT_CENTERS.get(version, ())
    for ar in centers:
        for ac in centers:
            # Die drei Ecken liegen unter den Findern und werden nicht gezeichnet.
            if (ar, ac) in ((6, 6), (6, n - 7), (n - 7, 6)):
                continue
            for i in range(-2, 3):
                for j in range(-2, 3):
                    edge = max(abs(i), abs(j)) == 2
                    target = dark if (edge or (i == 0 and j == 0)) else light
                    target[ar + i, ac + j] = True

    dark[4 * version + 9, 8] = True  # das immer dunkle Modul
    return dark, light


def timing_score(matrix: np.ndarray) -> float:
    """Anteil korrekt alternierender Module in den beiden Timing-Reihen.

    Der ehrlichste Einzeltest fuer den Gittersitz: eine halbe Modulbreite Versatz laesst
    diesen Wert sofort einbrechen, waehrend das Bild noch plausibel aussieht.
    """
    n = matrix.shape[0]
    hits = total = 0
    for idx in range(8, n - 8):
        expected = idx % 2 == 0
        hits += int(bool(matrix[6, idx]) == expected)
        hits += int(bool(matrix[idx, 6]) == expected)
        total += 2
    return hits / max(total, 1)
