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

**This script is behind its own outputs, and re-running it would undo work.** In September 2026
the drop shadow and the speckles under the creature were removed -- reworked by hand at 256 px
and propagated from there to every asset: the mark in all four sizes, the page axolotl, the
social card and the lockup. The draft in idea_for_icon/ still carries the shadow, so a re-run
regenerates it. Before using this script again, fix the draft; otherwise the assets in
docs/logo/ are the newer truth and this file is only the record of how they were framed.

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


def _fit(image: Image.Image, width: int, height: int, coverage: float) -> Image.Image:
    """Scale so the drawing takes `coverage` of whichever canvas edge constrains it first.

    Written in terms of how much of the canvas the artwork should occupy rather than a maximum
    size, because a maximum silently becomes a full bleed the moment the artwork is wider than
    it is tall -- which is how the first cut of these files ended up with a six percent margin
    on one axis and none at all on the other.
    """
    scale = min(width * coverage / image.width, height * coverage / image.height)
    return image.resize(
        (max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.LANCZOS
    )


def _centre(image: Image.Image, width: int, height: int, coverage: float) -> Image.Image:
    """Place the drawing on a transparent canvas of the given shape, with air around it."""
    scaled = _fit(image, width, height, coverage)
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    canvas.paste(scaled, ((width - scaled.width) // 2, (height - scaled.height) // 2), scaled)
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
    # The drawing is half again as wide as it is tall, so a square will always carry more air
    # above and below than beside -- but it must not be pressed against the left and right
    # edges to hide that, which only reads as cramped.
    for size in (1024, 512, 256, 128):
        path = OUT / f"qrsalvage-mark-{size}.png"
        _centre(creature_img, size, size, 0.78).save(path)
        written.append(path)

    # The lockup, transparent, for a README header on either a light or a dark background.
    # A transparent PNG has no margin of its own, so whatever is placed next to it sits flush
    # against the drawing. The breathing room has to be baked in.
    inner = _fit(lockup_img, 1000, 1000, 1.0)
    pad = round(inner.width * 0.08)
    lockup = Image.new("RGBA", (inner.width + 2 * pad, inner.height + 2 * pad), (0, 0, 0, 0))
    lockup.paste(inner, (pad, pad), inner)
    lockup.save(OUT / "qrsalvage-lockup.png")
    written.append(OUT / "qrsalvage-lockup.png")

    # The social preview, opaque and in the ratio every platform crops to: 1.91:1. This is the
    # one that has a background, because a transparent PNG on someone else's timeline is a
    # lottery between white and black. Laid out across rather than stacked: the draft's own
    # arrangement is nearly square and leaves a third of this canvas empty on either side,
    # where a preview is read at thumbnail size and wants to fill the space it is given.
    card = Image.new("RGBA", (1200, 628), SITE_BG + (255,))
    beast = _fit(creature_img, 470, 440, 1.0)
    words = _fit(Image.fromarray(_tight(wordmark)), 470, 165, 1.0)
    line = _fit(Image.fromarray(_tight(tagline)), 470, 74, 1.0)

    # Composed from a stated margin outwards rather than from maximum sizes inwards, so the
    # content cannot creep up on the edges the way it did before.
    lead = round(words.height * 0.34)
    text_height = words.height + lead + line.height
    gap = round(beast.width * 0.20)
    total = beast.width + gap + max(words.width, line.width)
    left = (1200 - total) // 2
    card.paste(beast, (left, (628 - beast.height) // 2), beast)
    text_top = (628 - text_height) // 2
    text_left = left + beast.width + gap
    card.paste(words, (text_left, text_top), words)
    card.paste(line, (text_left, text_top + words.height + lead), line)
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
