"""Matrix zeichnen, decodieren, und an den unsichersten Stellen nachtasten.

Der Decoder ist hier kein Ratgeber, sondern ein exaktes Orakel: er sagt nicht "waermer",
sondern "gueltig" oder "nicht gueltig". Deshalb braucht es keine gelernte Bewertungsfunktion,
sondern eine kluge Reihenfolge, in der man ihn befragt -- billigste Zweifel zuerst.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field

import numpy as np
import zxingcpp

from .matrix import ModuleMatrix

QR = zxingcpp.BarcodeFormat.QRCode


def render(matrix: np.ndarray, scale: int = 10, quiet: int = 4) -> np.ndarray:
    """Zeichnet eine Modulmatrix als ideales Schwarzweissbild mit Ruhezone.

    Die Ruhezone ist Pflicht: ein bis an die Codekante beschnittenes Bild weisen die Decoder
    zurueck, egal wie sauber der Code darin ist.
    """
    cells = np.where(matrix, np.uint8(0), np.uint8(255))
    big = np.kron(cells, np.ones((scale, scale), dtype=np.uint8))
    return np.pad(big, quiet * scale, constant_values=255)


def decode_matrix(matrix: np.ndarray, scale: int = 4) -> str | None:
    """Ein Decodier-Versuch auf der gerenderten Matrix."""
    try:
        hits = zxingcpp.read_barcodes(render(matrix, scale=scale), formats=QR, try_invert=False)
    except Exception:
        return None
    for hit in hits:
        if hit.text:
            return hit.text
    return None


@dataclass
class SearchResult:
    """Ergebnis des Nachtastens."""

    text: str | None
    candidates_tried: int
    flipped: list[tuple[int, int]] = field(default_factory=list)
    matrix: np.ndarray | None = None


def _subsets_by_cost(costs: np.ndarray, budget: int):
    """Zaehlt Teilmengen in aufsteigender Gesamtkostenreihenfolge auf.

    Bestensuche ueber einen Halden-Speicher: aus einer bereits ausgegebenen Menge entstehen
    genau zwei Nachfolger -- Element erweitern oder letztes Element weiterschieben. Damit
    kommt jede Teilmenge genau einmal und in der richtigen Reihenfolge heraus.
    """
    m = len(costs)
    if m == 0:
        return
    heap: list[tuple[float, tuple[int, ...]]] = [(float(costs[0]), (0,))]
    seen = 0
    while heap and seen < budget:
        cost, subset = heapq.heappop(heap)
        seen += 1
        yield subset
        last = subset[-1]
        if last + 1 < m:
            heapq.heappush(heap, (cost + float(costs[last + 1]), (*subset, last + 1)))
            heapq.heappush(
                heap,
                (cost - float(costs[last]) + float(costs[last + 1]), (*subset[:-1], last + 1)),
            )


def ordered_search(
    mm: ModuleMatrix, max_cells: int = 22, budget: int = 4000, scale: int = 4
) -> SearchResult:
    """Tastet die Matrix an den unsichersten Zellen ab, billigste Zweifel zuerst.

    Entspricht dem Schlossknacken: nicht alle Stifte gleichzeitig, sondern der schwaechste
    zuerst, und nach jedem Versuch fragt man das Schloss, ob es aufgeht.
    """
    base = mm.hard()
    text = decode_matrix(base, scale=scale)
    if text:
        return SearchResult(text=text, candidates_tried=1, matrix=base)

    cost_field = mm.flip_cost()
    order = np.argsort(cost_field, axis=None)
    order = [int(i) for i in order if np.isfinite(cost_field.flat[i])][:max_cells]
    if not order:
        return SearchResult(text=None, candidates_tried=1)

    costs = np.array([cost_field.flat[i] for i in order], dtype=np.float64)
    n = mm.modules
    tried = 1

    for subset in _subsets_by_cost(costs, budget):
        cand = base.copy()
        for pos in subset:
            flat = order[pos]
            cand.flat[flat] = not cand.flat[flat]
        tried += 1
        text = decode_matrix(cand, scale=scale)
        if text:
            flipped = [(order[p] // n, order[p] % n) for p in subset]
            return SearchResult(text=text, candidates_tried=tried, flipped=flipped, matrix=cand)

    return SearchResult(text=None, candidates_tried=tried)


def reencode(text: str) -> np.ndarray:
    """Kodiert den gefundenen Inhalt neu und liefert eine normgerechte Modulmatrix.

    Besser als die Rekonstruktion zu zeichnen: das Ergebnis ist dann garantiert ein gueltiger
    Code und nicht blosse Rekonstruktion, die zufaellig durchgegangen ist.
    """
    barcode = zxingcpp.create_barcode(text, QR)
    image = np.asarray(zxingcpp.write_barcode_to_image(barcode, scale=1, add_quiet_zones=False))
    if image.ndim == 3:
        image = image[:, :, 0]
    return image < 128
