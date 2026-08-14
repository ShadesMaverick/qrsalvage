"""The module grid with three states: dark, light, unknown.

The third state is not a convenience, it is the core of the method. Forcing an uncertain cell
into a decision costs twice as much correction budget as an honest abstention -- Reed-Solomon
repairs twice as many erasures as errors -- and it throws away the very information that tells
the solver where to look.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

DARK, LIGHT, UNKNOWN = 1, 0, -1


@dataclass
class ModuleMatrix:
    """Per-module probabilities plus the cells the standard fixes."""

    posterior: np.ndarray
    known_dark: np.ndarray
    known_light: np.ndarray

    @property
    def modules(self) -> int:
        return int(self.posterior.shape[0])

    @property
    def locked(self) -> np.ndarray:
        return self.known_dark | self.known_light

    def hard(self) -> np.ndarray:
        """Best single estimate: structure fixed, everything else by probability."""
        out = self.posterior >= 0.5
        locked = self.locked
        out[locked] = self.known_dark[locked]
        return out

    def confidence(self) -> np.ndarray:
        """Distance from undecided: 0 means on the fence, 0.5 means unambiguous."""
        conf = np.abs(self.posterior - 0.5)
        conf[self.locked] = 0.5
        return conf

    def uncertain_cells(self, band: float = 0.15) -> np.ndarray:
        """Indices of the cells still in doubt, least confident first."""
        conf = self.confidence()
        order = np.argsort(conf, axis=None)
        return np.array([i for i in order if conf.flat[i] < band], dtype=int)

    def states(self, band: float = 0.15) -> np.ndarray:
        """Three-valued view: DARK, LIGHT or UNKNOWN per cell."""
        conf = self.confidence()
        out = np.where(self.posterior >= 0.5, DARK, LIGHT).astype(np.int8)
        out[conf < band] = UNKNOWN
        locked = self.locked
        out[locked] = np.where(self.known_dark[locked], DARK, LIGHT)
        return out

    def to_ascii(self, band: float = 0.15) -> str:
        """Text rendering for the agent interface: '#' dark, '.' light, '?' unknown."""
        symbols = {DARK: "#", LIGHT: ".", UNKNOWN: "?"}
        return "\n".join("".join(symbols[int(v)] for v in row) for row in self.states(band))

    def flip_cost(self) -> np.ndarray:
        """Cost of flipping a cell against its more likely reading.

        This is the log-likelihood ratio: a cell at P=0.5 is free to flip, an unambiguous one
        is expensive. That ordering is exactly what the solver probes along.
        """
        p = np.clip(self.posterior, 1e-9, 1 - 1e-9)
        kept = np.maximum(p, 1 - p)
        flipped = np.minimum(p, 1 - p)
        cost = np.log(kept / flipped)
        cost[self.locked] = np.inf  # structure is never touched
        return cost
