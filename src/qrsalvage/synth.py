"""Kuenstlich verdorbene QR-Codes mit bekannter Antwort.

Der Weg rueckwaerts loest das Grundproblem der Entwicklung: ein Korpus aus einem einzigen Foto
misst nichts. Wer den Klartext kennt, kann beliebig viele Faelle erzeugen, deren Loesung
feststeht -- und damit jede Aenderung am Verfahren beziffern statt sie zu glauben.

Nachgebildet werden die vier Schaeden aus dem echten Bild: Woelbung, Punktraster der
Lasergravur, Glanzverlauf und Verschmutzung.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .core.decoding import reencode


@dataclass(frozen=True)
class Damage:
    """Wie stark ein synthetischer Fall verdorben wird. Alles in Bildeinheiten."""

    module_px: float = 9.0
    curvature: float = 0.25
    raster_period: float = 3.0
    raster_depth: float = 0.55
    contrast: float = 0.28
    glare: float = 0.35
    stain: float = 0.0
    blur: float = 1.2
    noise: float = 4.0
    rotation_deg: float = 0.0


def _cylinder_map(shape: tuple[int, int], curvature: float):
    """Bildet eine ebene Flaeche auf einen Zylindermantel ab.

    Genau diese Verzerrung bringt Homographien an ihre Grenze: sie ist nichtlinear, staucht
    zum Rand hin und laesst ein sonst perfektes Gitter um eine halbe Modulbreite auswandern.
    """
    h, w = shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    u = (xx - w / 2.0) / (w / 2.0)
    # Rueckwaertsabbildung: wo im Original liegt der Zielpixel?
    src_u = np.arcsin(np.clip(u * np.sin(curvature * np.pi / 2), -1, 1)) / (
        curvature * np.pi / 2 + 1e-9
    )
    map_x = (src_u * (w / 2.0) + w / 2.0).astype(np.float32)
    map_y = yy
    return map_x, map_y


def render_photo(matrix: np.ndarray, damage: Damage, seed: int = 0) -> np.ndarray:
    """Erzeugt aus einer Modulmatrix ein Bild, das einem echten Foto aehnelt."""
    rng = np.random.default_rng(seed)
    px = int(round(damage.module_px))
    quiet = 5

    cells = np.where(matrix, np.float32(0.0), np.float32(1.0))
    plane = np.kron(cells, np.ones((px, px), dtype=np.float32))
    plane = np.pad(plane, quiet * px, constant_values=1.0)
    h, w = plane.shape

    # Punktraster: die Gravur ist kein Fleck, sondern ein Muster aus Einzelpunkten.
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    raster = np.sin(xx * np.pi / damage.raster_period) * np.sin(yy * np.pi / damage.raster_period)
    raster = (raster > 0).astype(np.float32)
    engraved = np.where(plane < 0.5, 1.0 - damage.raster_depth * raster, plane)

    # Kontrast: die Gravur ist nur wenig dunkler als der weisse Kunststoff.
    img = 1.0 - damage.contrast * (1.0 - engraved)

    if damage.rotation_deg:
        rot = cv2.getRotationMatrix2D((w / 2, h / 2), damage.rotation_deg, 1.0)
        img = cv2.warpAffine(img, rot, (w, h), borderValue=1.0)

    if damage.curvature > 0:
        map_x, map_y = _cylinder_map((h, w), damage.curvature)
        img = cv2.remap(img, map_x, map_y, cv2.INTER_LINEAR, borderValue=1.0)

    # Glanzverlauf: eine breite helle Keule ueber dem Bild.
    gy, gx = np.mgrid[0:h, 0:w].astype(np.float32)
    glare = np.exp(-(((gx - w * 0.35) ** 2 + (gy - h * 0.2) ** 2) / (2 * (w * 0.6) ** 2)))
    img = np.clip(img * (1.0 - damage.glare * 0.5) + damage.glare * glare * 0.5, 0, 1)

    if damage.stain > 0:
        cy, cx = rng.uniform(0.2, 0.8, size=2) * np.array([h, w])
        radius = rng.uniform(0.12, 0.25) * w
        blob = np.exp(-(((gx - cx) ** 2 + (gy - cy) ** 2) / (2 * radius**2)))
        img = np.clip(img - damage.stain * blob, 0, 1)

    if damage.blur > 0:
        img = cv2.GaussianBlur(img, (0, 0), damage.blur)

    out = np.clip(img * 255.0 + rng.normal(0, damage.noise, img.shape), 0, 255).astype(np.uint8)
    return cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)


def make_case(text: str, damage: Damage | None = None, seed: int = 0):
    """Kodiert den Text, verdirbt ihn und liefert (Foto, wahre Matrix)."""
    matrix = reencode(text)
    return render_photo(matrix, damage or Damage(), seed=seed), matrix
