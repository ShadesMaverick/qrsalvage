"""Decisions that steer recovery, kept separate from pipeline orchestration.

The image-processing modules produce evidence. These small policies say how that evidence is
ranked and when an escalation is warranted. Keeping them here gives the choices names and unit
tests without coupling them to CLI, server, progress reporting, or image manipulation.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from .geometry import GridFit


class FusionMember(Protocol):
    wrong_known: int | None
    timing: float | None


def choose_grid(fits: Sequence[GridFit]) -> GridFit:
    """Choose the grid with fewest contradicted witnesses, breaking ties by smooth quality."""
    if not fits:
        raise ValueError("cannot choose a grid from no fits")
    return min(fits, key=lambda fit: (fit.wrong_known, -fit.quality))


def attempt_error_rate(fits: Sequence[GridFit]) -> float:
    """Fraction of known cells contradicted by an attempt's best grid."""
    if not fits:
        return 1.0
    best = choose_grid(fits)
    return best.wrong_known / max(best.known_total, 1)


def should_restart(fit: GridFit, threshold: float) -> bool:
    """Whether a finished grid is too badly seated for a local descent to be trusted."""
    return fit.wrong_known > threshold * max(fit.known_total, 1)


def fusion_rank(member: FusionMember) -> tuple[int, float]:
    """Put the cleanest grid first as the reference for cross-image agreement."""
    if member.wrong_known is None or member.timing is None:
        raise ValueError("a fusion member needs grid diagnostics")
    return member.wrong_known, -member.timing
