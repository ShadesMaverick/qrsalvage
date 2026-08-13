"""Vom entzerrten Bild zur Wahrscheinlichkeit je Modul.

Kein Schwellwert entscheidet hier etwas endgueltig. Jede Zelle bekommt eine Wahrscheinlichkeit,
dunkel zu sein -- das ist die Voraussetzung dafuer, dass der Solver spaeter gezielt an den
unsichersten Stellen tasten kann statt blind zu probieren.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class LevelFit:
    """Das geschaetzte Helligkeitsmodell einer Codeflaeche."""

    dark: np.ndarray
    light: np.ndarray
    sigma: float

    @property
    def threshold(self) -> np.ndarray:
        return (self.dark + self.light) / 2.0

    @property
    def contrast(self) -> np.ndarray:
        return np.maximum(self.light - self.dark, 1e-6)


def sample_cells(warped: np.ndarray, modules: int, scale: int, inset_frac: float = 0.3):
    """Mittelwert und Streuung je Modulzelle.

    Gemessen wird nur der Kern der Zelle. Die Raender tragen das Uebersprechen der Nachbarn,
    das die zur Rasterfusion noetige Weichzeichnung zwangslaeufig hineingetragen hat.
    """
    inset = max(1, int(scale * inset_frac))
    # Das Raster ist regelmaessig, also laesst sich die Schleife exakt gleichwertig durch eine
    # Umformung ersetzen. Das ist hier kein Feinschliff: die Gitteranpassung ruft diese
    # Funktion einige hundert Mal je Bild auf.
    grid = warped.reshape(modules, scale, modules, scale).transpose(0, 2, 1, 3)
    core = grid[:, :, inset : scale - inset, inset : scale - inset].astype(np.float64)
    return core.mean(axis=(2, 3)), core.std(axis=(2, 3))


def _fit_quadratic(means: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Passt ein quadratisches Feld an die markierten Zellen an und wertet es ueberall aus."""
    n = means.shape[0]
    rr, cc = np.mgrid[0:n, 0:n].astype(np.float64)
    terms = np.stack([np.ones_like(rr), rr, cc, rr * rr, cc * cc, rr * cc], axis=-1)
    coef, *_ = np.linalg.lstsq(terms[mask], means[mask], rcond=None)
    return terms @ coef


def estimate_levels(means: np.ndarray, known_dark: np.ndarray, known_light: np.ndarray) -> LevelFit:
    """Schaetzt Dunkel- und Hellniveau als getrennte Felder aus den bekannten Zellen.

    Getrennt, weil sich ueber eine gewoelbte Flaeche beide Niveaus unterschiedlich verschieben:
    eine einzelne Schwelle kann das nicht abbilden, zwei Felder schon.
    """
    dark = _fit_quadratic(means, known_dark)
    light = _fit_quadratic(means, known_light)
    contrast = np.maximum(light - dark, 1e-6)
    residuals = np.concatenate(
        [
            ((means - dark) / contrast)[known_dark],
            ((means - light) / contrast)[known_light],
        ]
    )
    sigma = float(np.std(residuals)) or 0.1
    return LevelFit(dark=dark, light=light, sigma=max(sigma, 0.02))


def posterior_dark(means: np.ndarray, fit: LevelFit) -> np.ndarray:
    """P(Modul ist dunkel) aus zwei Gaussmodellen mit gemeinsamer Streuung.

    Die Streuung stammt aus den bekannten Zellen -- das Modell eicht sich also an Messwerten,
    deren wahre Antwort feststeht, statt an einer gesetzten Konstante.
    """
    contrast = fit.contrast
    x = means / contrast
    d = fit.dark / contrast
    ell = fit.light / contrast
    log_odds = ((x - ell) ** 2 - (x - d) ** 2) / (2.0 * fit.sigma**2)
    return 1.0 / (1.0 + np.exp(-np.clip(log_odds, -60.0, 60.0)))


def warp(gray: np.ndarray, corners: np.ndarray, modules: int, scale: int) -> np.ndarray:
    """Entzerrt die vier Eckpunkte auf ein quadratisches Modulraster."""
    dst = np.array(
        [
            [0, 0],
            [modules * scale, 0],
            [0, modules * scale],
            [modules * scale, modules * scale],
        ],
        dtype=np.float32,
    )
    h = cv2.getPerspectiveTransform(np.asarray(corners, dtype=np.float32), dst)
    return cv2.warpPerspective(
        gray,
        h,
        (modules * scale, modules * scale),
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=255,
    )
