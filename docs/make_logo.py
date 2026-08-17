"""Cut the logo out of its draft and write it at the sizes it is actually used in.

The artwork began as a generated draft: one 1408x768 picture with the creature, the wordmark
and a tagline arranged on a dark gradient -- plus the generator's watermark in a corner, which
is exactly why that file is gitignored and never shipped. This script is the step from that
draft to assets that can be published: watermark gone, background gone, proportions chosen for
where each file goes rather than inherited from whatever the generator happened to output.

The interesting part is the cut-out. Distance from the background colour alone would have eaten
the black outlines of the pixel art, which are as dark as the backdrop; instead the background
is found by flooding inwards from the border, so anything enclosed by the white keyline stays
opaque no matter how dark it is. The edge then gets a one-pixel ramp from the same distance
measure, because a hard alpha edge on pixel art reads as a jagged halo on a light page.

The input lives in idea_for_icon/, which is gitignored -- so this script cannot be re-run from
a clean checkout, and that is on purpose: the draft carries someone else's watermark. Its
outputs in docs/logo/ are the master copies from here on.

    python docs/make_logo.py
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DRAFT = ROOT / "idea_for_icon" / "frist_idea.png"
OUT = ROOT / "docs" / "logo"

# The page's own background, so a logo placed on an opaque card matches the site exactly.
SITE_BG = (27, 37, 46)

# How far a pixel must sit from the backdrop before it counts as artwork at all.
INK = 60


def _artwork_alpha(rgb: np.ndarray) -> np.ndarray:
    """Alpha for the drawing: everything the outside cannot reach, plus a soft rim."""
    backdrop = np.median(rgb.reshape(-1, 3), axis=0)
    distance = np.abs(rgb.astype(np.int16) - backdrop).sum(axis=2)

    # Flood from every border pixel through backdrop-like colour. What the flood cannot reach
    # is enclosed by the keyline and belongs to the drawing -- including its black outlines,
    # which a plain colour threshold would have punched holes through.
    height, width = distance.shape
    background = (distance <= INK).astype(np.uint8)
    outside = np.zeros((height + 2, width + 2), np.uint8)
    filled = background.copy()
    for x in range(width):
        for y in (0, height - 1):
            if filled[y, x]:
                cv2.floodFill(filled, outside, (x, y), 2)
    for y in range(height):
        for x in (0, width - 1):
            if filled[y, x]:
                cv2.floodFill(filled, outside, (x, y), 2)

    alpha = np.where(filled == 2, 0.0, 1.0)
    # One pixel of ramp where the drawing meets the backdrop, so the edge is not a staircase.
    rim = np.clip((distance - INK * 0.4) / (INK * 0.6), 0.0, 1.0)
    return (np.minimum(alpha, np.maximum(rim, alpha * 0.0 + (filled != 2))) * 255).astype(np.uint8)


def _tight(rgba: np.ndarray) -> np.ndarray:
    rows = np.flatnonzero(rgba[..., 3].any(axis=1))
    cols = np.flatnonzero(rgba[..., 3].any(axis=0))
    return rgba[rows[0] : rows[-1] + 1, cols[0] : cols[-1] + 1]


def _pad_to_square(image: Image.Image, size: int, margin: float = 0.06) -> Image.Image:
    """Centre on a square canvas, scaled to leave a little air on the longest side."""
    inner = int(size * (1 - 2 * margin))
    scale = inner / max(image.size)
    scaled = image.resize(
        (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
        Image.LANCZOS,
    )
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(scaled, ((size - scaled.width) // 2, (size - scaled.height) // 2), scaled)
    return canvas


def main() -> int:
    if not DRAFT.is_file():
        raise SystemExit(f"{DRAFT} is missing -- the draft is gitignored and local to one machine")
    OUT.mkdir(parents=True, exist_ok=True)

    rgb = np.array(Image.open(DRAFT).convert("RGB"))
    alpha = _artwork_alpha(rgb)
    rgba = np.dstack([rgb, alpha])

    # The three bands the draft is built from, measured rather than assumed: the creature, the
    # wordmark under it, and the tagline under that. The fourth thing in the file -- the
    # generator's watermark, alone in the bottom right -- is simply never included in a crop.
    solid = alpha > 8
    profile = solid.sum(axis=1)
    creature = rgba[:500]
    wordmark = rgba[500:605]
    tagline = rgba[605:660]
    print(f"draft {rgb.shape[1]}x{rgb.shape[0]}, opaque pixels {int(solid.sum()):,}")
    print(f"  rows carrying ink: {int((profile > 3).sum())}")

    creature_img = Image.fromarray(_tight(creature))
    lockup_img = Image.fromarray(_tight(np.vstack([creature, wordmark])))

    written = []

    # The mark alone, square: repository avatar, and the source a favicon is generated from.
    for size in (1024, 512, 256, 128):
        path = OUT / f"qrsalvage-mark-{size}.png"
        _pad_to_square(creature_img, size).save(path)
        written.append(path)

    # The lockup, transparent, for a README header on either a light or a dark background.
    lockup = lockup_img.copy()
    lockup.thumbnail((1200, 1200), Image.LANCZOS)
    lockup.save(OUT / "qrsalvage-lockup.png")
    written.append(OUT / "qrsalvage-lockup.png")

    # The social preview, opaque and in the ratio every platform crops to: 1.91:1. This is the
    # one that has a background, because a transparent PNG on someone else's timeline is a
    # lottery between white and black. Laid out across rather than stacked: the draft's own
    # arrangement is nearly square and leaves a third of this canvas empty on either side,
    # where a preview is read at thumbnail size and wants to fill the space it is given.
    card = Image.new("RGBA", (1200, 628), SITE_BG + (255,))
    beast = creature_img.copy()
    beast.thumbnail((520, 470), Image.LANCZOS)
    words = Image.fromarray(_tight(wordmark))
    words.thumbnail((560, 200), Image.LANCZOS)
    line = Image.fromarray(_tight(tagline))
    line.thumbnail((560, 90), Image.LANCZOS)

    text_height = words.height + 18 + line.height
    block_width = max(words.width, line.width)
    gap = 56
    left = (1200 - (beast.width + gap + block_width)) // 2
    card.paste(beast, (left, (628 - beast.height) // 2), beast)
    text_top = (628 - text_height) // 2
    text_left = left + beast.width + gap
    card.paste(words, (text_left, text_top), words)
    card.paste(line, (text_left, text_top + words.height + 18), line)
    card.convert("RGB").save(OUT / "qrsalvage-social.png")
    written.append(OUT / "qrsalvage-social.png")

    # The page header asset, at twice its displayed width so it stays sharp on dense screens.
    header = creature_img.copy()
    header.thumbnail((354, 354), Image.LANCZOS)
    header.save(OUT / "axolotl@2x.png")
    written.append(OUT / "axolotl@2x.png")

    print()
    for path in written:
        with Image.open(path) as check:
            print(
                f"  {path.relative_to(ROOT).as_posix():<34} {check.size[0]:>5}x{check.size[1]:<5}"
                f" {path.stat().st_size / 1024:>7.1f} KB"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
