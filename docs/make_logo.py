"""Build the logo artwork: a real QR code that disintegrates, and the small mark.

The draft logo had a drawn QR code in it. For this project of all projects that is the wrong
detail to fake -- correctness is the entire pitch, and the people most likely to look closely
are exactly the ones who would notice.

Making it real and making it look destroyed are not in conflict, provided the destruction goes
in the right direction. Modules are *added* outside the code rather than removed from inside
it, beyond a clean four-module quiet zone. The code stays perfectly scannable while appearing
to break apart, and the script decodes its own output before writing it, so a broken logo
cannot ship quietly.

Usage:
    python docs/make_logo.py --text "https://github.com/you/qrsalvage"
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np
import zxingcpp

from qrsalvage.core.decoding import reencode, render
from qrsalvage.export import to_svg

ROOT = Path(__file__).resolve().parents[1]

INK = "#f2f4f5"
ACCENT = "#f07ea3"
GROUND = "#1b252e"

QUIET = 4  # modules of clean space the standard wants, and scanners rely on
SCATTER = 7  # modules of debris beyond that, where nothing can interfere


def disintegrate(matrix: np.ndarray, seed: int = 0, reach: float = 3.2):
    """Place the code on a larger canvas and scatter debris off its left and top edges.

    Returns (canvas, accent mask). Density falls off exponentially with distance, which is what
    makes it read as disintegration rather than as noise: near the code the fragments are dense
    enough to look like they came from it, and they thin out rather than stopping at a line.
    """
    rng = np.random.default_rng(seed)
    n = matrix.shape[0]
    pad = QUIET + SCATTER
    size = n + 2 * pad

    canvas = np.zeros((size, size), dtype=bool)
    canvas[pad : pad + n, pad : pad + n] = matrix

    accent = np.zeros_like(canvas)
    for r in range(size):
        for c in range(size):
            # Distance out of the code, in modules, but only counting left and upward.
            left = max(0, pad - c)
            up = max(0, pad - r)
            depth = max(left, up)
            if depth <= QUIET:
                continue  # the quiet zone stays clear, which is what keeps this scannable
            density = float(np.exp(-(depth - QUIET) / reach))
            if rng.random() < density * 0.55:
                canvas[r, c] = True
                # A third of the debris takes the accent colour, so the eye follows the
                # dissolution rather than reading it as dirt.
                accent[r, c] = rng.random() < 0.34
    return canvas, accent


def to_two_colour_svg(canvas: np.ndarray, accent: np.ndarray, size_px: int = 512) -> str:
    """Render the canvas as SVG with the debris picked out in the accent colour."""
    n = canvas.shape[0]
    unit = size_px / n
    rects = []
    for r in range(n):
        for c in range(n):
            if not canvas[r, c]:
                continue
            colour = ACCENT if accent[r, c] else INK
            rects.append(
                f'<rect x="{c * unit:.3f}" y="{r * unit:.3f}" '
                f'width="{unit:.3f}" height="{unit:.3f}" fill="{colour}"/>'
            )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size_px}" height="{size_px}" '
        f'viewBox="0 0 {size_px} {size_px}" shape-rendering="crispEdges">'
        f"{''.join(rects)}</svg>\n"
    )


MARK = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="16" height="16">
<rect width="16" height="16" fill="{GROUND}"/>
<rect x="8" y="3" width="7" height="7" fill="none" stroke="{INK}" stroke-width="1"/>
<rect x="10" y="5" width="3" height="3" fill="{INK}"/>
<rect x="5" y="4" width="2" height="2" fill="{ACCENT}"/>
<rect x="2" y="7" width="2" height="2" fill="{ACCENT}"/>
<rect x="5" y="10" width="2" height="2" fill="{INK}"/>
<rect x="1" y="12" width="1" height="1" fill="#93a3b0"/>
<rect x="7" y="1" width="1" height="1" fill="#93a3b0"/>
</svg>
"""


def extract_axolotl(source: Path, target: Path, height: int = 132) -> bool:
    """Cut the creature out of the draft artwork and key its background to transparency.

    The draft is a flat image on a solid ground with a generator's watermark in the corner.
    What the interface needs is the creature alone, at header size, on whatever background the
    page happens to have. The ground is keyed by colour distance rather than by a hard
    threshold, so the anti-aliased pixels along the outline fade instead of leaving a halo --
    which is what makes a cut-out look pasted on.
    """
    art = cv2.imread(str(source))
    if art is None:
        return False

    h, w = art.shape[:2]
    # The creature occupies the middle of the draft; the wordmark below and the watermark in
    # the corner are not wanted.
    crop = art[int(h * 0.12) : int(h * 0.64), int(w * 0.31) : int(w * 0.69)]

    ground = np.median(
        np.concatenate([crop[:6].reshape(-1, 3), crop[:, :6].reshape(-1, 3)]), axis=0
    )
    distance = np.linalg.norm(crop.astype(np.float32) - ground, axis=2)
    alpha = np.clip((distance - 26.0) / 34.0, 0.0, 1.0)

    scale = height / crop.shape[0]
    resized = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    alpha_resized = cv2.resize(alpha, (resized.shape[1], resized.shape[0]), cv2.INTER_AREA)

    rgba = np.dstack([resized, (alpha_resized * 255).astype(np.uint8)])
    cv2.imwrite(str(target), rgba)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--text",
        default="qrsalvage - recover QR codes from what's left of them",
        help="what the logo's code encodes. Use the project URL once it exists",
    )
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", type=Path, default=ROOT / "docs")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    matrix = reencode(args.text)
    canvas, accent = disintegrate(matrix, seed=args.seed)

    # Prove it before writing it. A logo that stopped scanning would be the one defect this
    # project cannot afford, and it would be invisible to review.
    check = render(canvas, scale=8, quiet=2)
    hits = [h.text for h in zxingcpp.read_barcodes(check) if h.text]
    if args.text not in hits:
        print(f"the disintegrated code does not scan back: {hits}")
        return 1

    (args.out / "logo-code.svg").write_text(to_two_colour_svg(canvas, accent), encoding="utf-8")
    cv2.imwrite(str(args.out / "logo-code.png"), render(canvas, scale=16, quiet=0))
    (args.out / "mark.svg").write_text(MARK, encoding="utf-8")
    (args.out / "code-plain.svg").write_text(to_svg(matrix, size_mm=40.0), encoding="utf-8")

    web = ROOT / "src" / "qrsalvage" / "web"
    web.mkdir(parents=True, exist_ok=True)
    draft = ROOT / "idea.png"
    if extract_axolotl(draft, web / "axolotl.png"):
        print(f"  -> {web / 'axolotl.png'}  (cut from {draft.name}, background keyed out)")
    else:
        print(f"  !! {draft.name} not found, the interface keeps the abstract mark")

    print(f"encodes: {args.text!r}")
    print(f"code    : version {(matrix.shape[0] - 17) // 4}, {matrix.shape[0]} modules")
    print(f"canvas  : {canvas.shape[0]} modules, {int(canvas.sum() - matrix.sum())} of debris")
    print("scans back: yes")
    for name in ("logo-code.svg", "logo-code.png", "mark.svg", "code-plain.svg"):
        print(f"  -> {args.out / name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
