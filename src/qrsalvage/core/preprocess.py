"""Vorverarbeitung: aus dem Foto ein Bild machen, in dem Module Flaechen sind.

Zwei Schritte tragen fast alles. Die Beleuchtungskorrektur nimmt Glanzverlauf und Schattierung
der Woelbung heraus, bevor irgendeine Schwelle greift. Die Weichzeichnung verwandelt das
Punktraster der Lasergravur in Graustufen -- ohne sie schwellt man die einzelnen Rasterpunkte
statt der Module.
"""

from __future__ import annotations

import cv2
import numpy as np


def flat_field(channel: np.ndarray) -> np.ndarray:
    """Division durch eine stark weichgezeichnete Kopie."""
    bg = cv2.GaussianBlur(channel, (0, 0), sigmaX=max(channel.shape) / 12.0)
    return np.clip(cv2.divide(channel, bg, scale=192), 0, 255).astype(np.uint8)


def prepare(
    bgr: np.ndarray, channel: int = 0, clip_limit: float = 3.0, blur_sigma: float = 1.5
) -> tuple[np.ndarray, np.ndarray]:
    """Liefert (Graustufenbild zum Abtasten, Binaerbild zur Findersuche).

    Voreingestellt ist der Blaukanal: bei Lasergravur auf weissem Kunststoff traegt er
    erfahrungsgemaess den meisten Kontrast, deutlich mehr als die Luminanz.
    """
    chan = bgr[:, :, channel] if bgr.ndim == 3 else bgr
    flat = flat_field(chan)
    tonal = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(8, 8)).apply(flat)
    gray = cv2.GaussianBlur(tonal, (0, 0), blur_sigma)
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 41, 2
    )
    return gray, binary
