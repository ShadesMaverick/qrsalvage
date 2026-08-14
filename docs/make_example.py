"""Build the before/after illustration used in the README.

Uses a synthetic case from the public corpus, so the image can be shipped and reproduced by
anyone. Run from the repository root:

    python docs/make_example.py
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from qrsalvage.core.decoding import reencode, render
from qrsalvage.core.pipeline import solve

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "fixtures" / "engraved-curved-hard.png"
TARGET = ROOT / "docs" / "example.png"

PANEL = 360
GAP = 24
LABEL_HEIGHT = 34


def _panel(image: np.ndarray, caption: str) -> np.ndarray:
    """Scale an image into a square panel and write a caption underneath."""
    if image.ndim == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    scaled = cv2.resize(image, (PANEL, PANEL), interpolation=cv2.INTER_NEAREST)
    canvas = np.full((PANEL + LABEL_HEIGHT, PANEL, 3), 255, dtype=np.uint8)
    canvas[:PANEL] = scaled
    cv2.putText(
        canvas,
        caption,
        (2, PANEL + 23),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (40, 40, 40),
        1,
        cv2.LINE_AA,
    )
    return canvas


def main() -> int:
    photo = cv2.imread(str(SOURCE))
    if photo is None:
        print(f"cannot read {SOURCE}")
        return 1

    result = solve(photo)
    if not result.solved:
        print(f"the example case did not solve: {result.failure}")
        return 2

    left = _panel(photo, "input: engraved, curved, stained")
    middle = _panel(
        render(result.decoded_matrix, scale=8, quiet=2),
        f"recovered: v{result.version}, {result.wrong_known}/{result.known_total} cells off",
    )
    right = _panel(render(reencode(result.text), scale=8, quiet=2), "re-encoded: standards clean")

    gap = np.full((left.shape[0], GAP, 3), 255, dtype=np.uint8)
    cv2.imwrite(str(TARGET), np.hstack([left, gap, middle, gap, right]))
    print(f"{TARGET.relative_to(ROOT)}  ({PANEL * 3 + GAP * 2}x{left.shape[0]} px)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
