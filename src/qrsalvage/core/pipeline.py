"""Der ganze Weg vom Foto zum Klartext, ohne Ausgabe und ohne Dateizugriff.

Diese Schicht entscheidet nichts selbst, sie fuegt zusammen: vorverarbeiten, Gitter suchen,
Version durchprobieren, abtasten, decodieren, notfalls nachtasten. Alles Berichten ist Sache
der Aufrufer -- der Kern bleibt bibliotheksrein.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .decoding import SearchResult, decode_matrix, ordered_search
from .ensemble import Consensus, GeometryConsensus, consensus_posterior, geometry_consensus
from .geometry import GridFit, find_finders, initial_corners, order_finders, refine_corners
from .matrix import ModuleMatrix
from .preprocess import prepare
from .repair import RepairResult, repair_progressive
from .structure import is_valid_size, structure_mask, timing_score, version_for_modules

DEFAULT_SIZES = (21, 25, 29, 33, 37, 41)


@dataclass
class SolveResult:
    """Was ein Loesungsversuch ergeben hat -- auch wenn er gescheitert ist."""

    text: str | None
    modules: int | None = None
    version: int | None = None
    wrong_known: int | None = None
    wrong_sampled: int | None = None
    known_total: int | None = None
    timing: float | None = None
    uncertain: int | None = None
    candidates_tried: int = 0
    flipped: list[tuple[int, int]] = field(default_factory=list)
    matrix: ModuleMatrix | None = None
    decoded_matrix: np.ndarray | None = None
    finders: list[tuple[float, float, float]] = field(default_factory=list)
    per_size: list[GridFit] = field(default_factory=list)
    consensus: Consensus | None = None
    geometry: GeometryConsensus | None = None
    reparatur: RepairResult | None = None
    failure: str | None = None

    @property
    def solved(self) -> bool:
        return self.text is not None


def fit_grid(gray: np.ndarray, binary: np.ndarray, sizes=DEFAULT_SIZES) -> list[GridFit]:
    """Passt fuer jede Kandidatengroesse ein Gitter an und misst es an den bekannten Zellen.

    Die Version wird bewusst nicht aus der Finderbreite geglaubt: bei wenigen Pixeln pro Modul
    liegt diese Schaetzung regelmaessig zwischen zwei Kandidaten, und der Unterschied zwischen
    richtig und falsch ist an den bekannten Zellen sofort sichtbar.
    """
    finders = find_finders(binary)
    if len(finders) < 3:
        return []
    tl, tr, bl = order_finders(finders[:3])

    fits: list[GridFit] = []
    for modules in sizes:
        if not is_valid_size(modules):
            continue
        known_dark, known_light = structure_mask(modules)
        corners = initial_corners(tl, tr, bl, modules)
        fits.append(refine_corners(gray, corners, modules, 12, known_dark, known_light))
    return fits


def solve(
    bgr: np.ndarray,
    crop: tuple[int, int, int, int] | None = None,
    sizes=DEFAULT_SIZES,
    budget: int = 4000,
    band: float = 0.15,
    ensemble: str = "off",
) -> SolveResult:
    """Loest einen QR-Code aus einem Foto. Wirft nicht, sondern berichtet.

    `ensemble` waehlt, worueber wiederholt gemessen wird:

    - ``"off"``       eine Messung, ein Gitter.
    - ``"sampling"``  ein Gitter, mehrere Vorverarbeitungen. Nachweislich wirkungslos --
                      alle Mitglieder teilen sich den Gitterfehler. Details in ensemble.py.
    - ``"geometry"``  mehrere unabhaengig angepasste Gitter. Teurer, aber die Streuung
                      trifft die tatsaechliche Fehlerquelle.
    """
    if ensemble not in ("off", "sampling", "geometry"):
        raise ValueError(f"unbekannter Ensemble-Modus: {ensemble!r}")
    if crop is not None:
        x0, y0, x1, y1 = crop
        bgr = bgr[y0:y1, x0:x1]

    gray, binary = prepare(bgr)
    finders = find_finders(binary)
    if len(finders) < 3:
        return SolveResult(
            text=None, finders=finders, failure=f"nur {len(finders)} Finder-Kandidaten gefunden"
        )

    fits = fit_grid(gray, binary, sizes)
    if not fits:
        return SolveResult(text=None, finders=finders, failure="kein Gitter anpassbar")

    best = min(fits, key=lambda f: (f.wrong_known, -f.quality))
    known_dark, known_light = structure_mask(best.modules)

    consensus: Consensus | None = None
    geometry: GeometryConsensus | None = None
    posterior = best.posterior

    if ensemble == "sampling":
        # Gitter fest, nur die Abtastung variiert. Nachweislich wirkungslos, siehe ensemble.py.
        consensus = consensus_posterior(
            bgr, best.corners, best.modules, 12, known_dark, known_light
        )
        posterior = consensus.posterior
    elif ensemble == "geometry":
        # Jedes Mitglied sucht sein eigenes Gitter. Die Version steht fest, sonst zeigten die
        # Mitglieder auf verschiedene Zellen und liessen sich nicht zusammenfuehren.
        geometry = geometry_consensus(bgr, best.corners, best.modules, known_dark, known_light)
        if geometry is not None:
            posterior = geometry.posterior

    mm = ModuleMatrix(posterior=posterior, known_dark=known_dark, known_light=known_light)

    # Reihenfolge nach Kosten: erst der direkte Versuch, dann Reed-Solomon mit Auslassungen,
    # erst zuletzt die kombinatorische Tastsuche. Der Decoder rechnet die richtigen Werte in
    # einem Schritt aus, wo die Suche tausende Kombinationen durchprobieren muesste.
    reparatur: RepairResult | None = None
    hart = mm.hard()
    text = decode_matrix(hart)
    search = SearchResult(text=text, candidates_tried=1, matrix=hart if text else None)

    if not text:
        reparatur = repair_progressive(
            hart, posterior=posterior, verify=lambda m: decode_matrix(m) is not None
        )
        if reparatur.ok:
            text = decode_matrix(reparatur.matrix)
            if text:
                search = SearchResult(text=text, candidates_tried=2, matrix=reparatur.matrix)

    if not text:
        search = ordered_search(mm, budget=budget)

    # Zwei getrennte Fehlerzahlen, weil sie zwei verschiedene Dinge messen: wrong_known
    # bewertet die Gitteranpassung, wrong_sampled die Abtastung, mit der wirklich gesucht
    # wurde. Wer beide vermengt, kann eine Aenderung an der Abtastung nicht sehen.
    known = known_dark | known_light
    wrong_sampled = int(((posterior >= 0.5)[known] != known_dark[known]).sum())

    return SolveResult(
        text=search.text,
        modules=best.modules,
        version=version_for_modules(best.modules),
        wrong_known=best.wrong_known,
        wrong_sampled=wrong_sampled,
        known_total=best.known_total,
        timing=timing_score(mm.hard()),
        uncertain=int(len(mm.uncertain_cells(band))),
        candidates_tried=search.candidates_tried,
        flipped=search.flipped,
        matrix=mm,
        decoded_matrix=search.matrix,
        finders=finders,
        per_size=fits,
        consensus=consensus,
        geometry=geometry,
        reparatur=reparatur,
        failure=None if search.text else "kein gueltiger Code im abgesuchten Bereich",
    )
