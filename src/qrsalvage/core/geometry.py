"""Finder finden, Gitter aufspannen, Gitter nachjustieren.

Hier steckt die eigentliche Suche des Verfahrens. Der Raum ist stetig (acht Eckkoordinaten),
das Signal aus den bekannten Zellen ist dicht -- deshalb funktioniert hier Bergsteigen, waehrend
es auf der Bitebene nichts zu besteigen gibt.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .sampling import estimate_levels, posterior_dark, sample_cells, warp


@dataclass(frozen=True)
class GridFit:
    """Ergebnis einer Gitteranpassung fuer eine angenommene Codegroesse."""

    modules: int
    corners: np.ndarray
    quality: float
    wrong_known: int
    known_total: int
    means: np.ndarray
    posterior: np.ndarray


def find_finders(binary: np.ndarray, min_size: int = 20) -> list[tuple[float, float, float]]:
    """Sucht Finder-Patterns. Liefert (cx, cy, Aussenbreite), groesste zuerst.

    Ein Finder ist drei ineinanderliegende Quadrate, also eine Kontur mit zwei
    Verschachtelungsebenen. Kandidaten am selben Ort werden zusammengefasst.
    """
    contours, hierarchy = cv2.findContours(binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None:
        return []
    hierarchy = hierarchy[0]

    raw: list[tuple[float, float, float]] = []
    for i, cnt in enumerate(contours):
        depth, child = 0, hierarchy[i][2]
        while child != -1 and depth < 3:
            depth += 1
            child = hierarchy[child][2]
        if depth < 2:
            continue
        x, y, w, h = cv2.boundingRect(cnt)
        if w < min_size or h < min_size or not 0.75 <= w / h <= 1.33:
            continue
        raw.append((x + w / 2.0, y + h / 2.0, (w + h) / 2.0))

    merged: list[tuple[float, float, float]] = []
    for cx, cy, size in sorted(raw, key=lambda t: -t[2]):
        if any(abs(cx - mx) < size / 2 and abs(cy - my) < size / 2 for mx, my, _ in merged):
            continue
        merged.append((cx, cy, size))
    return merged


def order_finders(finders):
    """Ordnet drei Finder zu (oben-links, oben-rechts, unten-links).

    Oben-links ist der Finder am rechten Winkel; welcher der beiden anderen oben-rechts ist,
    entscheidet die Orientierung des Kreuzprodukts.
    """
    pts = [np.array([x, y], dtype=np.float64) for x, y, _ in finders]
    best, best_score = None, np.inf
    for i in range(3):
        j, k = (m for m in range(3) if m != i)
        v1, v2 = pts[j] - pts[i], pts[k] - pts[i]
        norm = float(np.linalg.norm(v1) * np.linalg.norm(v2)) + 1e-9
        score = abs(float(np.dot(v1, v2))) / norm
        if score < best_score:
            best_score, best = score, (i, j, k)
    i, j, k = best
    tl, a, b = pts[i], pts[j], pts[k]
    cross = (a - tl)[0] * (b - tl)[1] - (a - tl)[1] * (b - tl)[0]
    return (tl, a, b) if cross > 0 else (tl, b, a)


def initial_corners(tl: np.ndarray, tr: np.ndarray, bl: np.ndarray, modules: int) -> np.ndarray:
    """Codeecken aus den Finder-Zentren: 3,5 Module nach aussen in beide Richtungen."""
    ex = (tr - tl) / max(float(np.linalg.norm(tr - tl)), 1e-9)
    ey = (bl - tl) / max(float(np.linalg.norm(bl - tl)), 1e-9)
    span = (float(np.linalg.norm(tr - tl)) + float(np.linalg.norm(bl - tl))) / 2.0
    off = 3.5 * span / (modules - 7)
    return np.array(
        [
            tl - ex * off - ey * off,
            tr + ex * off - ey * off,
            bl - ex * off + ey * off,
            tr + bl - tl + ex * off + ey * off,
        ]
    )


def evaluate(gray, corners, modules, scale, known_dark, known_light) -> GridFit:
    """Misst eine Eckpunktlage an den Zellen, deren Wert der Standard festlegt."""
    warped = warp(gray, corners, modules, scale)
    means, _ = sample_cells(warped, modules, scale)
    fit = estimate_levels(means, known_dark, known_light)
    posterior = posterior_dark(means, fit)

    known = known_dark | known_light
    # Guete: mittlerer, auf den Kontrast normierter Abstand zur Schwelle. Glatt genug, um
    # daran zu optimieren -- anders als die ganzzahlige Fehlerzahl.
    margin = np.where(known_dark, fit.threshold - means, means - fit.threshold) / fit.contrast
    quality = float(np.tanh(margin[known] * 4.0).mean())
    hard = means < fit.threshold
    wrong = int((hard[known] != known_dark[known]).sum())

    return GridFit(
        modules=modules,
        corners=np.asarray(corners, dtype=np.float64),
        quality=quality,
        wrong_known=wrong,
        known_total=int(known.sum()),
        means=means,
        posterior=posterior,
    )


def refine_corners(
    gray, corners, modules, scale, known_dark, known_light, start_delta: float = 3.0
) -> GridFit:
    """Ruettelt die vier Eckpunkte nach, bis die bekannten Zellen bestmoeglich sitzen.

    Eine Homographie kann eine gewoelbte Flaeche nicht exakt abbilden. Die beste erreichbare
    Naeherung ist nicht analytisch bestimmbar, wohl aber auffindbar: Koordinatenabstieg mit
    schrumpfender Schrittweite, bewertet an den bekannten Zellen.
    """
    current = np.array(corners, dtype=np.float64)
    best = evaluate(gray, current, modules, scale, known_dark, known_light)
    delta = start_delta
    while delta > 0.05:
        improved = False
        for corner in range(4):
            for axis in range(2):
                for step in (delta, -delta):
                    cand = current.copy()
                    cand[corner, axis] += step
                    trial = evaluate(gray, cand, modules, scale, known_dark, known_light)
                    if trial.quality > best.quality:
                        best, current, improved = trial, cand, True
        if not improved:
            delta /= 2.0
    return best
