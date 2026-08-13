"""Stufe 0: automatischer Vorverarbeitungs-Sweep mit Decodier-Versuch nach jeder Variante.

Aufruf:
    .venv\\Scripts\\python.exe scripts\\stufe0.py f5150252.png
    .venv\\Scripts\\python.exe scripts\\stufe0.py f5150252.png --crop 270 355 575 665

Schreibt Zwischenstaende nach out/. Nichts davon gehoert ins Repo.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
import zxingcpp

QR = zxingcpp.BarcodeFormat.QRCode
UPSCALE = 3
QUIET = 48  # weisser Rand in Pixeln, entspricht bei ~7 px/Modul rund sieben Modulen


def decode(img: np.ndarray, binarizer: zxingcpp.Binarizer) -> str | None:
    """Ein Decodier-Versuch. Gibt den Klartext zurueck oder None.

    Der weisse Rand ist nicht Kosmetik: der Standard verlangt eine Ruhezone von vier Modulen,
    und ein bis an die Codekante beschnittenes Bild lehnen die Decoder ab.
    """
    padded = cv2.copyMakeBorder(img, QUIET, QUIET, QUIET, QUIET, cv2.BORDER_CONSTANT, value=255)
    big = cv2.resize(padded, None, fx=UPSCALE, fy=UPSCALE, interpolation=cv2.INTER_NEAREST)
    try:
        hits = zxingcpp.read_barcodes(
            big, formats=QR, try_rotate=True, try_invert=True, binarizer=binarizer
        )
    except Exception:
        return None
    for h in hits:
        if h.text:
            return h.text
    return None


def flat_field(gray: np.ndarray) -> np.ndarray:
    """Beleuchtungskorrektur: Division durch eine stark weichgezeichnete Kopie.

    Entfernt Glanzverlauf und die Schattierung der Woelbung, bevor eine Schwelle greift.
    """
    bg = cv2.GaussianBlur(gray, (0, 0), sigmaX=max(gray.shape) / 12.0)
    out = cv2.divide(gray, bg, scale=192)
    return np.clip(out, 0, 255).astype(np.uint8)


def finder_candidates(binary: np.ndarray) -> int:
    """Grobe Diagnose: wie viele Finder-aehnliche Strukturen stecken im Bild?

    Ein Finder-Pattern ist ein Quadrat in einem Quadrat in einem Quadrat. Gezaehlt werden
    Konturen mit zwei Verschachtelungsebenen und annaehernd quadratischer Bounding-Box.
    """
    contours, hierarchy = cv2.findContours(binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None:
        return 0
    hierarchy = hierarchy[0]
    count = 0
    for i, cnt in enumerate(contours):
        depth = 0
        child = hierarchy[i][2]
        while child != -1 and depth < 3:
            depth += 1
            child = hierarchy[child][2]
        if depth < 2:
            continue
        x, y, w, h = cv2.boundingRect(cnt)
        if w < 8 or h < 8:
            continue
        if not 0.7 <= w / h <= 1.4:
            continue
        count += 1
    return count


def variants(crop: np.ndarray):
    """Erzeugt (name, graustufenbild) fuer alle Kanal-, Flatfield-, CLAHE- und Glaettungsstufen.

    Die Glaettung ist der entscheidende Schritt: ein schwarzes Modul der Lasergravur ist ein
    Punktraster, kein Fleck. Ohne Weichzeichnung schwellt man die einzelnen Rasterpunkte statt
    der Module und erzeugt Rauschen. Sigma liegt in der Groessenordnung einer halben Modulbreite.
    """
    channels = {
        "b": crop[:, :, 0],
        "g": crop[:, :, 1],
        "r": crop[:, :, 2],
        "gray": cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY),
    }
    for cname, chan in channels.items():
        for fname, base in (("raw", chan), ("flat", flat_field(chan))):
            tonals = [(f"{cname}-{fname}", base)]
            for clip in (2.0, 3.0, 4.0):
                clahe = cv2.createCLAHE(clipLimit=clip, tileGridSize=(8, 8))
                tonals.append((f"{cname}-{fname}-clahe{clip:g}", clahe.apply(base)))
            for tname, tonal in tonals:
                for sigma in (0.0, 1.0, 1.5, 2.0, 2.5, 3.0):
                    if sigma == 0.0:
                        yield f"{tname}-s0", tonal
                    else:
                        yield f"{tname}-s{sigma:g}", cv2.GaussianBlur(tonal, (0, 0), sigma)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("image", type=Path)
    ap.add_argument("--crop", nargs=4, type=int, metavar=("X0", "Y0", "X1", "Y1"))
    ap.add_argument("--out", type=Path, default=Path("out"))
    args = ap.parse_args()

    img = cv2.imread(str(args.image))
    if img is None:
        print(f"Bild nicht lesbar: {args.image}")
        return 1
    args.out.mkdir(parents=True, exist_ok=True)

    if args.crop:
        x0, y0, x1, y1 = args.crop
        crop = img[y0:y1, x0:x1]
    else:
        crop = img
    cv2.imwrite(str(args.out / "00_crop.png"), crop)
    print(f"Bild {img.shape[1]}x{img.shape[0]}, Ausschnitt {crop.shape[1]}x{crop.shape[0]}")

    attempts = 0
    best_finders = (0, "")
    log: list[dict] = []

    for name, gray in variants(crop):
        # Familie 1: Graustufen direkt an zxing, das binarisiert selbst.
        for bname, binz in (
            ("localavg", zxingcpp.Binarizer.LocalAverage),
            ("globalhist", zxingcpp.Binarizer.GlobalHistogram),
        ):
            attempts += 1
            text = decode(gray, binz)
            if text:
                print(f"\nTREFFER  {name} / {bname}\n{text!r}")
                (args.out / "treffer.txt").write_text(text, encoding="utf-8")
                return 0

        # Familie 2: eigene Schwelle, zxing bekommt fertiges Schwarzweiss.
        # Otsu global (nach Flatfield sinnvoll) plus adaptiv mit Bloecken deutlich
        # groesser als ein Modul -- kleine Bloecke folgen dem Raster statt den Modulen.
        thresholded = [
            ("otsu", cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1])
        ]
        for block in (17, 25, 31, 41):
            for c in (2, 5, 8):
                thresholded.append(
                    (
                        f"adapt{block}c{c}",
                        cv2.adaptiveThreshold(
                            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block, c
                        ),
                    )
                )

        for tname, binary in thresholded:
            for mname, kernel in (("none", None), ("close2", np.ones((2, 2), np.uint8))):
                b = binary if kernel is None else cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
                tag = f"{name}/{tname}/{mname}"

                attempts += 1
                text = decode(b, zxingcpp.Binarizer.BoolCast)
                if text:
                    print(f"\nTREFFER  {tag}\n{text!r}")
                    (args.out / "treffer.txt").write_text(text, encoding="utf-8")
                    cv2.imwrite(str(args.out / "treffer.png"), b)
                    return 0

                n = finder_candidates(b)
                log.append({"tag": tag, "finders": n})
                if n > best_finders[0]:
                    best_finders = (n, tag)
                    cv2.imwrite(str(args.out / "best_finders.png"), b)

    (args.out / "sweep.json").write_text(json.dumps(log, indent=1), encoding="utf-8")
    print(f"\nKein Treffer nach {attempts} Decodier-Versuchen.")
    print(f"Meiste Finder-Kandidaten: {best_finders[0]} bei {best_finders[1]}")
    print(f"-> {args.out / 'best_finders.png'}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
