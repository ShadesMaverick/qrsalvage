"""Find out why a photograph failed, instead of guessing at it.

When `solve` reports too few finder candidates, the question is always the same: is the code
invisible, or is the preprocessing tuned for the wrong scale? This walks the parameter space
that `prepare` fixes by default and reports how many finder candidates each combination yields,
plus writes the binary images so the failure can be looked at rather than argued about.

Usage:
    python scripts/diagnose.py photo.jpg --out out/diagnose
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2

from qrsalvage.core.geometry import find_finders
from qrsalvage.core.preprocess import prepare

CHANNELS = {0: "blue", 1: "green", 2: "red"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--out", type=Path, default=Path("out/diagnose"))
    parser.add_argument("--scales", nargs="*", type=float, default=[1.0, 0.5, 0.35, 0.25])
    args = parser.parse_args()

    image = cv2.imread(str(args.image))
    if image is None:
        print(f"cannot read {args.image}")
        return 1
    args.out.mkdir(parents=True, exist_ok=True)
    print(f"image: {image.shape[1]} x {image.shape[0]} px\n")

    print(f"{'scale':>6} {'px':>11} {'channel':>8} {'blur':>5} {'finders':>8}  widths")
    best: tuple[int, tuple[float, int, float] | None] = (0, None)
    for scale in args.scales:
        if scale != 1.0:
            resized = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        else:
            resized = image
        size = f"{resized.shape[1]}x{resized.shape[0]}"
        for channel in (0, 1, 2):
            for blur in (1.5, 2.5, 4.0):
                gray, binary = prepare(resized, channel=channel, blur_sigma=blur)
                finders = find_finders(binary)
                widths = " ".join(f"{w:.0f}" for _, _, w in finders[:4])
                print(
                    f"{scale:6.2f} {size:>11} {CHANNELS[channel]:>8} {blur:5.1f} "
                    f"{len(finders):8d}  {widths}"
                )
                if len(finders) >= 3 and len(finders) > best[0]:
                    best = (len(finders), (scale, channel, blur))
                    cv2.imwrite(str(args.out / "binary_best.png"), binary)

    print()
    settings = best[1]
    if settings is None:
        print("No combination found three finder patterns.")
        print("Look at the binary images: if the code is not visible there, the problem is the")
        print("photograph. If it is visible but broken up, the problem is the threshold.")
        gray, binary = prepare(image)
        cv2.imwrite(str(args.out / "binary_default.png"), binary)
        cv2.imwrite(str(args.out / "gray_default.png"), gray)
        print(f"-> {args.out / 'binary_default.png'}")
        return 2

    scale, channel, blur = settings
    print(f"Best: scale {scale}, {CHANNELS[channel]} channel, blur {blur} -> {best[0]} finders")
    print(f"-> {args.out / 'binary_best.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
