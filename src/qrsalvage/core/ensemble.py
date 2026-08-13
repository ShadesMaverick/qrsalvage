"""Mehrere Durchlaeufe je Zelle statt eines einzigen.

Eine einzelne Vorverarbeitung liefert eine Wahrscheinlichkeit je Modul, aber keine Auskunft
darueber, wie belastbar diese Wahrscheinlichkeit ist. Ein einzelner Lauf kann sich sehr sicher
und dabei sehr falsch sein -- etwa wenn eine Glaettungsstufe zufaellig ueber einen Schmutzfleck
mittelt.

Deshalb wird dieselbe Zelle unter mehreren Bedingungen gemessen: anderer Farbkanal, andere
Kontrastspreizung, andere Glaettung, anderes Zellinnenmass, minimal verschobene Eckpunkte. Wo
die Laeufe uebereinstimmen, ist die Zelle sicher. Wo sie streiten, ist sie es nicht -- und
genau das braucht der Solver, um zuerst an der richtigen Stelle zu tasten.

Das Gitter selbst wird dabei *nicht* neu bestimmt. Version und Eckpunkte stehen fest, sonst
zeigten die Laeufe auf verschiedene Zellen und liessen sich nicht mitteln.

MESSERGEBNIS: Genau diese Entscheidung macht das Verfahren wirkungslos. Im A/B-Vergleich ueber
vier Schadensstufen mit je zwoelf Bildern loeste der Konsens kein einziges Bild zusaetzlich
(12/12, 10/12, 9/12, 1/12 -- identisch mit dem Einzellauf). Der Grund: die dominierende
Fehlerquelle ist das Gitter, weil eine Homographie die Zylinderwoelbung nicht abbilden kann.
Alle Bedingungen teilen es sich, also teilen sie sich auch den Fehler -- zehn korrelierte
Messungen desselben systematischen Fehlers ergeben ihn erneut, nur mit falscher Sicherheit.
Der Jitter von 0,5 px sollte das auffangen, ist bei knapp 9 px Modulbreite aber zu klein.

Deshalb standardmaessig abgeschaltet.

ZWEITER VERSUCH, ueber Geometrien (siehe geometry_consensus weiter unten): Der trifft die
richtige Varianz -- neun unabhaengig angepasste Gitter liefern am echten Foto 1 bis 3 falsche
Zellen statt neunmal derselben Zahl, und auf der haertesten synthetischen Stufe faellt der
Median falsch abgetasteter bekannter Zellen von 7 auf 4. Die Abtastung wird also messbar
besser.

Geloest wird davon trotzdem kein einziges Bild zusaetzlich (10/12, 9/12, 1/12 -- identisch),
bei doppelter Laufzeit. Der Grund liegt nicht mehr an der Abtastung, sondern an dem, was
danach kommt: die Tastsuche kippt hoechstens 22 Zellen und kann selbst mit perfekt geeichter
Unsicherheit nicht reparieren, was auf dieser Stufe an echten Fehlern vorliegt.

Damit zeigt die Messung auf den naechsten Hebel: ein eigener Reed-Solomon-Decoder mit
Erasure-Unterstuetzung. Erst der verbraucht die verbesserte Unsicherheit wirklich -- er nimmt
die unzuverlaessigsten Zellen als Auslassung entgegen, statt sie kombinatorisch durchzuprobieren.
Bis dahin bleiben beide Ensembles abgeschaltet, aber erhalten: geometry_consensus ist genau
die Vorstufe, die ein Erasure-Decoder braucht.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .geometry import GridFit, refine_corners
from .preprocess import prepare
from .sampling import estimate_levels, posterior_dark, sample_cells, warp
from .structure import timing_score

EPS = 1e-9


@dataclass(frozen=True)
class SamplingConfig:
    """Eine Messbedingung. Bewusst grob gestreut, nicht fein abgestimmt."""

    channel: int = 0
    clip_limit: float = 3.0
    blur_sigma: float = 1.5
    inset: float = 0.30
    jitter: float = 0.0
    jitter_seed: int = 0


DEFAULT_CONFIGS: tuple[SamplingConfig, ...] = (
    SamplingConfig(channel=0, clip_limit=3.0, blur_sigma=1.5, inset=0.30),
    SamplingConfig(channel=0, clip_limit=2.0, blur_sigma=1.2, inset=0.25),
    SamplingConfig(channel=0, clip_limit=4.0, blur_sigma=2.0, inset=0.35),
    SamplingConfig(channel=1, clip_limit=3.0, blur_sigma=1.5, inset=0.30),
    SamplingConfig(channel=2, clip_limit=3.0, blur_sigma=1.5, inset=0.30),
    SamplingConfig(
        channel=0, clip_limit=3.0, blur_sigma=1.5, inset=0.30, jitter=0.5, jitter_seed=1
    ),
    SamplingConfig(
        channel=0, clip_limit=3.0, blur_sigma=1.5, inset=0.30, jitter=0.5, jitter_seed=2
    ),
    SamplingConfig(
        channel=0, clip_limit=3.0, blur_sigma=1.5, inset=0.30, jitter=0.5, jitter_seed=3
    ),
    SamplingConfig(
        channel=0, clip_limit=2.5, blur_sigma=1.8, inset=0.30, jitter=0.5, jitter_seed=4
    ),
    SamplingConfig(
        channel=1, clip_limit=4.0, blur_sigma=1.2, inset=0.35, jitter=0.5, jitter_seed=5
    ),
)


@dataclass
class Consensus:
    """Ergebnis der Zusammenfuehrung mehrerer Messbedingungen."""

    posterior: np.ndarray
    disagreement: np.ndarray
    votes_dark: np.ndarray
    runs: int
    wrong_per_run: list[int]

    @property
    def contested(self) -> np.ndarray:
        """Zellen, bei denen die Laeufe im Urteil auseinandergehen.

        Gezaehlt wird die Uneinigkeit im Vorzeichen, nicht die Streuung der Log-Odds: deren
        Betraege reichen bis in die Zehner, weshalb dort fast jede Zelle als strittig gaelte.
        Uneins sind die Laeufe erst, wenn sie sich nicht auf hell oder dunkel einigen.
        """
        return (self.votes_dark > 0) & (self.votes_dark < self.runs)


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-12, 1 - 1e-12)
    return np.log(p / (1 - p))


def consensus_posterior(
    bgr: np.ndarray,
    corners: np.ndarray,
    modules: int,
    scale: int,
    known_dark: np.ndarray,
    known_light: np.ndarray,
    configs: tuple[SamplingConfig, ...] = DEFAULT_CONFIGS,
) -> Consensus:
    """Misst jede Zelle unter allen Bedingungen und fuehrt die Urteile zusammen.

    Gemittelt wird in Log-Odds, nicht in Wahrscheinlichkeiten. Der Unterschied ist nicht
    kosmetisch: der Mittelwert von 0.99 und 0.01 waere 0.5 und damit eine Zelle, die zwei
    Laeufe fuer voellig eindeutig halten -- in entgegengesetzter Richtung. In Log-Odds hebt
    sich das ebenfalls auf, aber die Streuung bleibt erhalten und macht den Streit sichtbar.
    """
    log_odds: list[np.ndarray] = []
    wrong_per_run: list[int] = []
    known = known_dark | known_light

    for cfg in configs:
        gray, _ = prepare(
            bgr, channel=cfg.channel, clip_limit=cfg.clip_limit, blur_sigma=cfg.blur_sigma
        )
        pts = np.array(corners, dtype=np.float64)
        if cfg.jitter:
            rng = np.random.default_rng(cfg.jitter_seed)
            pts = pts + rng.normal(0.0, cfg.jitter, pts.shape)

        warped = warp(gray, pts, modules, scale)
        means, _ = sample_cells(warped, modules, scale, inset_frac=cfg.inset)
        fit = estimate_levels(means, known_dark, known_light)
        posterior = posterior_dark(means, fit)

        log_odds.append(_logit(posterior))
        hard = posterior >= 0.5
        wrong_per_run.append(int((hard[known] != known_dark[known]).sum()))

    stack = np.stack(log_odds)
    mittel = stack.mean(axis=0)
    streit = stack.std(axis=0)
    votes_dark = (stack > 0).sum(axis=0)

    # Schrumpfung: wo die Laeufe streiten, wird das gemittelte Urteil zurueckgenommen.
    # Ohne diesen Schritt waere der Konsens selbstsicherer als seine Bestandteile -- der
    # klassische Fehler beim Mitteln korrelierter Messungen.
    gedaempft = mittel / np.sqrt(1.0 + (streit / 2.0) ** 2)
    posterior = 1.0 / (1.0 + np.exp(-np.clip(gedaempft, -60.0, 60.0)))

    return Consensus(
        posterior=posterior,
        disagreement=streit,
        votes_dark=votes_dark,
        runs=len(configs),
        wrong_per_run=wrong_per_run,
    )


# --------------------------------------------------------------------------------------
# Der harte Weg: ueber Geometrien mitteln statt ueber Vorverarbeitungen.
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class GeometryConfig:
    """Ein eigenstaendiger Anlauf auf das Gitter.

    Der Startpunkt wird kraeftig gestoert -- deutlich staerker als beim Abtast-Ensemble, wo
    0,5 px nur ein Sechstel Modul waren. Der Koordinatenabstieg laeuft danach frei und landet
    in seinem eigenen Optimum. Erst diese Unabhaengigkeit macht die Streuung aussagekraeftig.
    """

    channel: int = 0
    clip_limit: float = 3.0
    blur_sigma: float = 1.5
    corner_jitter: float = 2.0
    scale: int = 12
    seed: int = 0


DEFAULT_GEOMETRIES: tuple[GeometryConfig, ...] = (
    GeometryConfig(corner_jitter=0.0, seed=0),
    GeometryConfig(corner_jitter=2.0, seed=1),
    GeometryConfig(corner_jitter=2.0, seed=2),
    GeometryConfig(corner_jitter=3.5, seed=3),
    GeometryConfig(corner_jitter=3.5, seed=4),
    GeometryConfig(channel=1, corner_jitter=2.0, seed=5),
    GeometryConfig(channel=2, corner_jitter=2.0, seed=6),
    GeometryConfig(clip_limit=2.0, blur_sigma=1.2, corner_jitter=2.0, seed=7),
    GeometryConfig(clip_limit=4.0, blur_sigma=2.0, corner_jitter=2.0, seed=8),
)


@dataclass
class GeometryConsensus:
    """Zusammenfuehrung mehrerer unabhaengig angepasster Gitter."""

    posterior: np.ndarray
    disagreement: np.ndarray
    votes_dark: np.ndarray
    kept: int
    discarded: int
    wrong_per_member: list[int]
    weights: list[float]

    @property
    def contested(self) -> np.ndarray:
        return (self.votes_dark > 0) & (self.votes_dark < self.kept)


def geometry_consensus(
    bgr: np.ndarray,
    base_corners: np.ndarray,
    modules: int,
    known_dark: np.ndarray,
    known_light: np.ndarray,
    configs: tuple[GeometryConfig, ...] = DEFAULT_GEOMETRIES,
    max_extra_wrong: int = 6,
) -> GeometryConsensus | None:
    """Passt mehrere Gitter unabhaengig an und fuehrt ihre Zellurteile gewichtet zusammen.

    Zwei Vorkehrungen, ohne die das Mitteln schadet statt hilft:

    Aussortieren. Ein Anlauf kann in ein Optimum laufen, das um ein ganzes Modul verschoben
    ist. So ein Gitter ist nicht ungenauer, sondern falsch -- es zeigt auf andere Zellen. Wer
    es mitmittelt, verdirbt alle uebrigen. Erkennbar ist es an den bekannten Zellen und am
    Timing, und beides wird geprueft, bevor ein Mitglied zaehlt.

    Gewichten. Ein Anlauf mit zwei falschen bekannten Zellen weiss mehr als einer mit zwoelf.
    Gleichgewichtung waere die stille Annahme, alle Anlaeufe seien gleich gut -- sie sind es
    nachweislich nicht, und wir koennen es messen.
    """
    fits: list[GridFit] = []

    for cfg in configs:
        gray, _ = prepare(
            bgr, channel=cfg.channel, clip_limit=cfg.clip_limit, blur_sigma=cfg.blur_sigma
        )
        start = np.array(base_corners, dtype=np.float64)
        if cfg.corner_jitter:
            rng = np.random.default_rng(cfg.seed)
            start = start + rng.normal(0.0, cfg.corner_jitter, start.shape)
        fits.append(refine_corners(gray, start, modules, cfg.scale, known_dark, known_light))

    bestes = min(f.wrong_known for f in fits)
    brauchbar = [
        f
        for f in fits
        if f.wrong_known <= bestes + max_extra_wrong and timing_score(f.posterior >= 0.5) == 1.0
    ]
    if not brauchbar:
        return None

    # Gewicht faellt exponentiell mit der Zahl falscher bekannter Zellen. Die Skala von zwei
    # Zellen ist so gewaehlt, dass ein deutlich schlechteres Gitter mitreden darf, aber leise.
    gewichte = np.array([np.exp(-(f.wrong_known - bestes) / 2.0) for f in brauchbar])
    gewichte = gewichte / gewichte.sum()

    stack = np.stack([_logit(f.posterior) for f in brauchbar])
    mittel = np.tensordot(gewichte, stack, axes=(0, 0))
    streit = np.sqrt(np.tensordot(gewichte, (stack - mittel) ** 2, axes=(0, 0)))
    votes_dark = (stack > 0).sum(axis=0)

    gedaempft = mittel / np.sqrt(1.0 + (streit / 2.0) ** 2)
    posterior = 1.0 / (1.0 + np.exp(-np.clip(gedaempft, -60.0, 60.0)))

    return GeometryConsensus(
        posterior=posterior,
        disagreement=streit,
        votes_dark=votes_dark,
        kept=len(brauchbar),
        discarded=len(fits) - len(brauchbar),
        wrong_per_member=[int(f.wrong_known) for f in brauchbar],
        weights=[float(w) for w in gewichte],
    )
