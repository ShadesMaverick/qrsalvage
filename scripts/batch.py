"""Run the recovery over a pile of images and print one line each.

The question with a folder full of examples is never "does it work" but "which ones, and what
do the failures have in common". So the table reports the diagnostics next to the outcome:
where the finder search stood, how well the grid seated, and what the repair had to do.

Usage:
    python scripts/batch.py "C:/some/folder"
    python scripts/batch.py photo1.jpg photo2.png --grids out/grids
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import cv2

from qrsalvage.core.pipeline import solve

SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}


def collect(paths: list[Path]) -> list[Path]:
    found: list[Path] = []
    for path in paths:
        if path.is_dir():
            found.extend(sorted(p for p in path.iterdir() if p.suffix.lower() in SUFFIXES))
        elif path.suffix.lower() in SUFFIXES:
            found.append(path)
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--budget", type=int, default=4000)
    parser.add_argument("--grids", type=Path, default=None, help="write each ASCII grid here")
    args = parser.parse_args()

    images = collect(args.paths)
    if not images:
        print("no images found")
        return 1
    if args.grids:
        args.grids.mkdir(parents=True, exist_ok=True)

    print(f"{len(images)} images\n")
    header = (
        f"{'file':<44} {'size':>11} {'fnd':>4} {'ver':>4} "
        f"{'known wrong':>12} {'time':>5} {'sec':>5}  result"
    )
    print(header)
    print("-" * len(header))

    solved = 0
    for path in images:
        image = cv2.imread(str(path))
        name = path.name[:43]
        if image is None:
            print(f"{name:<44} {'unreadable':>11}")
            continue

        start = time.perf_counter()
        result = solve(image, budget=args.budget)
        seconds = time.perf_counter() - start
        solved += int(result.solved)

        size = f"{image.shape[1]}x{image.shape[0]}"
        finders = len(result.finders)
        version = result.version if result.version else "-"
        wrong = (
            f"{result.wrong_known}/{result.known_total}" if result.wrong_known is not None else "-"
        )
        timing = f"{result.timing * 100:.0f}%" if result.timing is not None else "-"
        outcome = (
            f"OK  {len(result.text)} chars, {result.candidates_tried} attempt(s)"
            if result.solved
            else f"--  {result.failure}"
        )
        print(
            f"{name:<44} {size:>11} {finders:>4} {str(version):>4} "
            f"{wrong:>12} {timing:>5} {seconds:5.1f}  {outcome}",
            flush=True,
        )

        if args.grids and result.matrix is not None:
            (args.grids / f"{path.stem}.txt").write_text(result.matrix.to_ascii(), encoding="utf-8")

    print(f"\n{solved} of {len(images)} recovered")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
