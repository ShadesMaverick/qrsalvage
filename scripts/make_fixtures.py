"""Generate the public regression corpus from synthetic cases.

Why synthetic: real photographs of damaged QR codes are almost always personal. They show
hands, rooms or equipment labels, and the decoded content is frequently a secret -- on a Zigbee
lamp, for instance, the pairing code. A public project cannot ship an image like that, not even
"just for testing".

Synthetic cases solve this completely: the answer is known because the case was generated from
it, the content is harmless, and anyone can reproduce the corpus with a single command. Private
photographs belong in fixtures-local/ and stay there.

Usage:
    python scripts/make_fixtures.py
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import cv2

from qrsalvage.core.decoding import reencode
from qrsalvage.synth import Damage, render_photo

TARGET = Path(__file__).resolve().parents[1] / "fixtures"

# The damage profiles are modelled on the real cases; the contents are not.
CASES: tuple[tuple[str, str, Damage, int], ...] = (
    (
        "engraved-curved-easy",
        "QRSALVAGE-SYNTHETIC-CASE-001",
        Damage(contrast=0.24, curvature=0.25, module_px=9.0),
        0,
    ),
    (
        "engraved-curved-medium",
        "QRSALVAGE-SYNTHETIC-CASE-002-LONGER-PAYLOAD",
        Damage(contrast=0.16, curvature=0.40, module_px=8.0, stain=0.10),
        1,
    ),
    (
        "engraved-curved-hard",
        "QRSALVAGE-SYNTHETIC-CASE-003-EVEN-LONGER-PAYLOAD-HERE",
        Damage(contrast=0.13, curvature=0.45, module_px=7.0, stain=0.15),
        2,
    ),
    (
        "low-resolution",
        "QRSALVAGE-SYNTHETIC-CASE-004",
        Damage(contrast=0.20, curvature=0.20, module_px=5.5, blur=0.9),
        3,
    ),
    (
        # Regression for a failure that is easy to miss because it looks like the opposite of a
        # problem: a photograph that is too *good*. At 22 px per module the adaptive threshold
        # block spans barely two modules and starts thresholding the code instead of the
        # illumination. Before the scale pyramid, the finder search found one finder here and
        # none at 26 px, while the same code at 9 px solved without trouble.
        "high-resolution",
        "QRSALVAGE-SYNTHETIC-CASE-005-HIGH-RESOLUTION",
        Damage(contrast=0.18, curvature=0.30, module_px=22.0),
        5,
    ),
    (
        # Light modules on a dark ground, as on a laser-etched metal part or dark plastic.
        # Everything downstream assumes dark modules, so before polarity was handled this
        # case was not merely hard, it was invisible.
        "inverted-polarity",
        "QRSALVAGE-SYNTHETIC-CASE-006-INVERTED",
        Damage(contrast=0.18, curvature=0.35, stain=0.10, inverted=True),
        6,
    ),
)


def main() -> int:
    TARGET.mkdir(parents=True, exist_ok=True)
    for name, text, damage, seed in CASES:
        matrix = reencode(text)
        photo = render_photo(matrix, damage, seed=seed)
        cv2.imwrite(str(TARGET / f"{name}.png"), photo)

        meta = {
            "source": "synthetically generated, see scripts/make_fixtures.py",
            "expected_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "expected_length": len(text),
            # For synthetic cases the plain text is harmless and may stay -- it makes debugging
            # far easier. For a real photograph this field would be a leak.
            "expected_prefix": text,
            "crop": None,
            "qr_modules": int(matrix.shape[0]),
            "damage": asdict(damage),
            "seed": seed,
            "synthetic": True,
        }
        (TARGET / f"{name}.json").write_text(
            json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"{name}: {photo.shape[1]}x{photo.shape[0]} px, {matrix.shape[0]} modules")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
