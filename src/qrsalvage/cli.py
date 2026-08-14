"""Text interface. All printing and file writing happens here, never in the core.

This is also the agent-facing path: `solve` writes the ASCII grid and the figures that tell you
whether probing is needed and where.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import cv2

from .core.decoding import reencode, render
from .core.pipeline import DEFAULT_SIZES, solve
from .synth import Damage, make_case


def _report(result, out: Path, band: float) -> None:
    print(f"finder candidates: {len(result.finders)}")
    for fit in result.per_size:
        marker = "<-" if fit.modules == result.modules else "  "
        print(
            f"  version {fit.modules:2d}: {fit.wrong_known:3d}/{fit.known_total} "
            f"known cells wrong, quality {fit.quality:.3f} {marker}"
        )
    if result.modules is None:
        print(f"failed: {result.failure}")
        return

    print(f"\nchosen: version {result.version} ({result.modules} modules)")
    print(f"known cells wrong: {result.wrong_known} of {result.known_total} (grid fit)")
    if result.wrong_sampled != result.wrong_known:
        print(f"                   {result.wrong_sampled} after sampling")
    print(f"timing pattern:    {result.timing * 100:.1f} %")
    if result.inverted:
        print("polarity:          inverted (light modules on a dark ground)")
    print(f"uncertain cells:   {result.uncertain} of {result.modules**2} (band {band})")
    print(f"decode attempts:   {result.candidates_tried}")

    if result.repair is not None:
        detail = result.repair.failure or (
            f"{result.repair.errors_corrected} errors, "
            f"{result.repair.erasures_used} erasures across "
            f"{result.repair.blocks} blocks"
        )
        print(f"reed-solomon:      {detail}")

    if result.matrix is not None:
        (out / "grid.txt").write_text(result.matrix.to_ascii(band), encoding="utf-8")
        print(f"ascii grid -> {out / 'grid.txt'}")

    if result.solved:
        if result.flipped:
            cells = ", ".join(f"({r},{c})" for r, c in result.flipped)
            print(f"probed: flipped {len(result.flipped)} cell(s) -> {cells}")
        digest = hashlib.sha256(result.text.encode()).hexdigest()
        print(f"\nRECOVERED ({len(result.text)} characters, sha256 {digest[:16]}...)")
        print(result.text)
    else:
        print(f"\nfailed: {result.failure}")


def cmd_solve(args: argparse.Namespace) -> int:
    image = cv2.imread(str(args.image))
    if image is None:
        print(f"cannot read image: {args.image}")
        return 1
    args.out.mkdir(parents=True, exist_ok=True)

    crop = tuple(args.crop) if args.crop else None
    result = solve(image, crop=crop, sizes=args.sizes or DEFAULT_SIZES, budget=args.budget)
    _report(result, args.out, args.band)

    if result.decoded_matrix is not None:
        cv2.imwrite(str(args.out / "reconstructed.png"), render(result.decoded_matrix))
    if result.solved:
        cv2.imwrite(str(args.out / "clean.png"), render(reencode(result.text)))
        print(f"clean code -> {args.out / 'clean.png'}")
        return 0
    return 2


def cmd_synth(args: argparse.Namespace) -> int:
    args.out.mkdir(parents=True, exist_ok=True)
    photo, _ = make_case(
        args.text,
        Damage(curvature=args.curvature, contrast=args.contrast, stain=args.stain),
        seed=args.seed,
    )
    path = args.out / f"synth_{args.seed}.png"
    cv2.imwrite(str(path), photo)
    print(f"{path}  ({photo.shape[1]}x{photo.shape[0]})")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from .server import serve

    return serve(port=args.port, open_browser=not args.no_browser)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="qrsalvage", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    solver = sub.add_parser("solve", help="recover a QR code from a photograph")
    solver.add_argument("image", type=Path)
    solver.add_argument("--crop", nargs=4, type=int, metavar=("X0", "Y0", "X1", "Y1"))
    solver.add_argument("--sizes", nargs="*", type=int, help="candidate sizes in modules")
    solver.add_argument("--budget", type=int, default=4000, help="max decode attempts when probing")
    solver.add_argument("--band", type=float, default=0.15, help="uncertainty band for the grid")
    solver.add_argument("--out", type=Path, default=Path("out"))
    solver.set_defaults(func=cmd_solve)

    synth = sub.add_parser("synth", help="generate an artificially degraded test case")
    synth.add_argument("text")
    synth.add_argument("--curvature", type=float, default=0.25)
    synth.add_argument("--contrast", type=float, default=0.28)
    synth.add_argument("--stain", type=float, default=0.0)
    synth.add_argument("--seed", type=int, default=0)
    synth.add_argument("--out", type=Path, default=Path("out"))
    synth.set_defaults(func=cmd_synth)

    ui = sub.add_parser("serve", help="open the local web interface")
    ui.add_argument("--port", type=int, default=8765)
    ui.add_argument("--no-browser", action="store_true", help="do not open a browser window")
    ui.set_defaults(func=cmd_serve)

    args = parser.parse_args(argv)
    return int(args.func(args))
