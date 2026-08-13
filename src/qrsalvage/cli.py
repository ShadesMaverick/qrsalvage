"""Textinterface. Alles Ausgeben und Schreiben passiert hier, nie im Kern.

Das ist zugleich der Agentenweg: `solve` schreibt das ASCII-Grid und die Kennzahlen, an denen
sich ablesen laesst, ob nachgetastet werden muss und wo.
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
    print(f"Finder-Kandidaten: {len(result.finders)}")
    for fit in result.per_size:
        marker = "<-" if fit.modules == result.modules else "  "
        print(
            f"  Version {fit.modules:2d}: {fit.wrong_known:3d}/{fit.known_total} "
            f"bekannte Zellen falsch, Guete {fit.quality:.3f} {marker}"
        )
    if result.modules is None:
        print(f"Gescheitert: {result.failure}")
        return

    print(f"\nGewaehlt: Version {result.version} ({result.modules} Module)")
    print(f"Bekannte Zellen falsch: {result.wrong_known} von {result.known_total} (Gitter)")
    if result.wrong_sampled != result.wrong_known:
        print(f"                        {result.wrong_sampled} nach der Abtastung")
    print(f"Timing-Guete: {result.timing * 100:.1f} %")
    print(f"Unsichere Zellen (Band {band}): {result.uncertain} von {result.modules**2}")
    print(f"Decodier-Versuche: {result.candidates_tried}")

    if result.matrix is not None:
        (out / "grid.txt").write_text(result.matrix.to_ascii(band), encoding="utf-8")
        print(f"ASCII-Grid -> {out / 'grid.txt'}")

    if result.solved:
        if result.flipped:
            cells = ", ".join(f"({r},{c})" for r, c in result.flipped)
            print(f"Nachgetastet: {len(result.flipped)} Zelle(n) gekippt -> {cells}")
        digest = hashlib.sha256(result.text.encode()).hexdigest()
        print(f"\nTREFFER ({len(result.text)} Zeichen, sha256 {digest[:16]}...)")
        print(result.text)
    else:
        print(f"\nGescheitert: {result.failure}")


def cmd_solve(args: argparse.Namespace) -> int:
    img = cv2.imread(str(args.image))
    if img is None:
        print(f"Bild nicht lesbar: {args.image}")
        return 1
    args.out.mkdir(parents=True, exist_ok=True)

    crop = tuple(args.crop) if args.crop else None
    result = solve(img, crop=crop, sizes=args.sizes or DEFAULT_SIZES, budget=args.budget)
    _report(result, args.out, args.band)

    if result.decoded_matrix is not None:
        cv2.imwrite(str(args.out / "rekonstruiert.png"), render(result.decoded_matrix))
    if result.solved:
        cv2.imwrite(str(args.out / "sauber.png"), render(reencode(result.text)))
        print(f"Sauberer Code -> {args.out / 'sauber.png'}")
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="qrsalvage", description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)

    s = sub.add_parser("solve", help="QR-Code aus einem Foto lesen")
    s.add_argument("image", type=Path)
    s.add_argument("--crop", nargs=4, type=int, metavar=("X0", "Y0", "X1", "Y1"))
    s.add_argument("--sizes", nargs="*", type=int, help="Kandidatengroessen in Modulen")
    s.add_argument("--budget", type=int, default=4000, help="max. Decodier-Versuche beim Tasten")
    s.add_argument("--band", type=float, default=0.15, help="Unsicherheitsband fuers ASCII-Grid")
    s.add_argument("--out", type=Path, default=Path("out"))
    s.set_defaults(func=cmd_solve)

    y = sub.add_parser("synth", help="kuenstlich verdorbenen Testfall erzeugen")
    y.add_argument("text")
    y.add_argument("--curvature", type=float, default=0.25)
    y.add_argument("--contrast", type=float, default=0.28)
    y.add_argument("--stain", type=float, default=0.0)
    y.add_argument("--seed", type=int, default=0)
    y.add_argument("--out", type=Path, default=Path("out"))
    y.set_defaults(func=cmd_synth)

    args = ap.parse_args(argv)
    return int(args.func(args))
