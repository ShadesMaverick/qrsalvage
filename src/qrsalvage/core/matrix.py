"""Das Modulraster mit drei Zustaenden: dunkel, hell, unbekannt.

Die dritte Moeglichkeit ist keine Bequemlichkeit, sondern der Kern des Verfahrens. Wer eine
unsichere Zelle zu einer Entscheidung zwingt, verbraucht doppelt so viel Korrekturbudget wie
jemand, der sich ehrlich enthaelt -- und verliert die Information, wo nachzutasten waere.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

DARK, LIGHT, UNKNOWN = 1, 0, -1


@dataclass
class ModuleMatrix:
    """Wahrscheinlichkeiten je Modul plus die vom Standard festgelegten Zellen."""

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
        """Beste Einzelschaetzung: Struktur gesetzt, Rest nach Wahrscheinlichkeit."""
        out = self.posterior >= 0.5
        locked = self.locked
        out[locked] = self.known_dark[locked]
        return out

    def confidence(self) -> np.ndarray:
        """Abstand zur Unentschiedenheit, 0 = auf der Kippe, 0.5 = eindeutig."""
        conf = np.abs(self.posterior - 0.5)
        conf[self.locked] = 0.5
        return conf

    def uncertain_cells(self, band: float = 0.15) -> np.ndarray:
        """Indizes der Zellen, deren Wert offen ist -- nach Unsicherheit sortiert."""
        conf = self.confidence()
        flat = np.argsort(conf, axis=None)
        return np.array([i for i in flat if conf.flat[i] < band], dtype=int)

    def states(self, band: float = 0.15) -> np.ndarray:
        """Dreiwertige Sicht: DARK, LIGHT oder UNKNOWN je Zelle."""
        conf = self.confidence()
        out = np.where(self.posterior >= 0.5, DARK, LIGHT).astype(np.int8)
        out[conf < band] = UNKNOWN
        locked = self.locked
        out[locked] = np.where(self.known_dark[locked], DARK, LIGHT)
        return out

    def to_ascii(self, band: float = 0.15) -> str:
        """Textdarstellung fuer das Agenteninterface: '#' dunkel, '.' hell, '?' unbekannt."""
        symbols = {DARK: "#", LIGHT: ".", UNKNOWN: "?"}
        rows = self.states(band)
        return "\n".join("".join(symbols[int(v)] for v in row) for row in rows)

    def flip_cost(self) -> np.ndarray:
        """Kosten, eine Zelle gegen ihre wahrscheinlichere Deutung zu kippen.

        Das ist das Log-Wahrscheinlichkeitsverhaeltnis: eine Zelle bei P=0.5 kostet nichts,
        eine eindeutige kostet viel. Genau diese Reihenfolge tastet der Solver ab.
        """
        p = np.clip(self.posterior, 1e-9, 1 - 1e-9)
        kept = np.maximum(p, 1 - p)
        flipped = np.minimum(p, 1 - p)
        cost = np.log(kept / flipped)
        cost[self.locked] = np.inf  # Struktur wird nicht angetastet
        return cost
