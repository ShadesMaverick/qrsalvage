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
from .core.ensemble import DEFAULT_FUSION, FUSION_RULES
from .core.pipeline import DEFAULT_SIZES, solve, solve_many
from .export import to_catalog_pdf, to_html_report, to_json, to_pdf, to_svg
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
    if result.ecc:
        print(f"error correction:  level {result.ecc}")
    if result.inverted:
        print("polarity:          inverted (light modules on a dark ground)")
    # Before the cell counts, because with several photographs those counts are properties of
    # the fusion and the reader needs to know what went into it first.
    _report_fusion(result.fusion)
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


def _png_bytes(matrix, scale: int = 8) -> bytes:
    ok, buffer = cv2.imencode(".png", render(matrix, scale=scale))
    return buffer.tobytes() if ok else b""


def _write_exports(args, result, image) -> None:
    """Write whichever of the export formats were asked for."""
    wanted = set(args.export or [])
    if not wanted:
        return

    # The code that gets exported is the re-encoded one wherever possible: that is guaranteed
    # to be a valid code, where the reconstruction is one that happened to pass. Its error
    # correction defaults to the level the original carried, so reproducing a label reproduces
    # it rather than inventing a new one.
    ecc = None if args.ecc == "same" else args.ecc
    matrix = (
        reencode(result.text, ecc=ecc or result.ecc) if result.solved else result.decoded_matrix
    )

    if "svg" in wanted and matrix is not None:
        path = args.out / "code.svg"
        path.write_text(to_svg(matrix, size_mm=args.size_mm), encoding="utf-8")
        print(f"svg  -> {path}  ({args.size_mm:g} mm square)")
    if "pdf" in wanted and matrix is not None:
        path = args.out / "code.pdf"
        path.write_bytes(to_pdf(matrix, size_mm=args.size_mm))
        print(f"pdf  -> {path}  ({args.size_mm:g} mm square)")
    if "json" in wanted:
        path = args.out / "result.json"
        path.write_text(to_json(result, split_payload=args.split), encoding="utf-8")
        print(f"json -> {path}" + ("  (with the secrets split out)" if args.split else ""))
    if "html" in wanted:
        ok, encoded = cv2.imencode(".png", image)
        path = args.out / "report.html"
        path.write_text(
            to_html_report(
                result,
                encoded.tobytes() if ok else b"",
                _png_bytes(result.decoded_matrix) if result.decoded_matrix is not None else b"",
                _png_bytes(matrix, scale=10) if result.solved and matrix is not None else b"",
            ),
            encoding="utf-8",
        )
        print(f"html -> {path}")


def _report_fusion(fusion) -> None:
    """What the photographs agreed on -- the evidence for trusting a fused result."""
    if fusion is None:
        return
    print(f"\nfused {fusion.members} photograph(s)")
    agreement = ", ".join(f"{a:.1%}" for a in fusion.agreement[1:])
    if agreement:
        print(f"  agreement with the best image: {agreement}")
    print(f"  cells the photographs disagree on: {fusion.disagreeing}")
    if fusion.mirrored:
        print(f"  mirrored, and flipped back: image(s) {', '.join(map(str, fusion.mirrored))}")
    if fusion.rejected:
        print(f"  dropped as a different code: image(s) {', '.join(map(str, fusion.rejected))}")


def cmd_solve(args: argparse.Namespace) -> int:
    images = []
    for path in args.image:
        image = cv2.imread(str(path))
        if image is None:
            print(f"cannot read image: {path}")
            return 1
        images.append(image)
    args.out.mkdir(parents=True, exist_ok=True)

    crop = tuple(args.crop) if args.crop else None
    sizes = args.sizes or DEFAULT_SIZES
    if len(images) == 1:
        result = solve(images[0], crop=crop, sizes=sizes, budget=args.budget)
    else:
        print(f"{len(images)} photographs of one code\n")
        result = solve_many(
            images, crop=crop, sizes=sizes, budget=args.budget, band=args.band, rule=args.fuse
        )
    _report(result, args.out, args.band)
    image = images[0]

    if result.decoded_matrix is not None:
        cv2.imwrite(str(args.out / "reconstructed.png"), render(result.decoded_matrix))
    if result.solved:
        assert result.text is not None
        cv2.imwrite(str(args.out / "clean.png"), render(reencode(result.text)))
        print(f"clean code -> {args.out / 'clean.png'}")
    _write_exports(args, result, image)
    return 0 if result.solved else 2


def cmd_catalog(args: argparse.Namespace) -> int:
    """Recover a pile of different codes and bind them into one printable A4 catalogue.

    The opposite assumption from `solve` with several images: there, all photographs show one
    code and are fused; here, every photograph is its own code and gets its own entry. Titles
    come from --titles in order, or from the file names -- which is what people name their
    photos anyway ("led-lampe-bad.jpg").
    """
    args.out.mkdir(parents=True, exist_ok=True)
    titles = list(args.titles or [])

    entries = []
    failed: list[str] = []
    seen: dict[str, str] = {}
    for index, path in enumerate(args.image):
        image = cv2.imread(str(path))
        if image is None:
            print(f"{path.name:35s} cannot be read as an image")
            failed.append(path.name)
            continue
        result = solve(image, budget=args.budget)
        title = titles[index] if index < len(titles) else path.stem.replace("-", " ")
        if not result.solved:
            print(f"{path.name:35s} not recovered — {result.failure}")
            failed.append(path.name)
            continue
        assert result.text is not None
        if result.text in seen:
            # A wild pile of photographs regularly holds two shots of the same label. The
            # catalogue is a register of codes, not of photographs, so the duplicate folds in.
            print(f"{path.name:35s} duplicate of {seen[result.text]}, folded into one entry")
            continue
        seen[result.text] = path.name
        note = f"version {result.version}"
        if result.ecc:
            note += f" · error correction {result.ecc}"
        note += f" · {len(result.text)} characters"
        entries.append(
            {
                "title": title,
                "text": result.text,
                "matrix": reencode(result.text, ecc=result.ecc),
                "note": note,
            }
        )
        print(f"{path.name:35s} recovered — {title}")

    if not entries:
        print("\nnothing recovered, no catalogue to write")
        return 2

    path = args.out / "catalog.pdf"
    path.write_bytes(to_catalog_pdf(entries, size_mm=args.size_mm))
    print(
        f"\n{len(entries)} entr{'y' if len(entries) == 1 else 'ies'}, "
        f"{(len(entries) + 2) // 3} page(s) -> {path}"
    )
    if failed:
        print(f"not in the catalogue: {', '.join(failed)}")
        print("stubborn ones often yield to several photographs: qrsalvage solve a.jpg b.jpg")
    return 0 if not failed else 2


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

    solver = sub.add_parser("solve", help="recover a QR code from one or more photographs")
    solver.add_argument(
        "image",
        type=Path,
        nargs="+",
        help="one photograph, or several of the same code. Several are fused: photographs taken "
        "at different angles get different cells wrong, and that disagreement is what the "
        "search needs. See scripts/multi_image.py for what it is worth",
    )
    solver.add_argument(
        "--crop",
        nargs=4,
        type=int,
        metavar=("X0", "Y0", "X1", "Y1"),
        help="applies to every image given, so crop mixed framings beforehand",
    )
    solver.add_argument("--sizes", nargs="*", type=int, help="candidate sizes in modules")
    solver.add_argument("--budget", type=int, default=4000, help="max decode attempts when probing")
    solver.add_argument("--band", type=float, default=0.15, help="uncertainty band for the grid")
    solver.add_argument("--out", type=Path, default=Path("out"))
    solver.add_argument(
        "--export",
        nargs="*",
        choices=["svg", "pdf", "json", "html"],
        help="extra formats to write; svg and pdf carry a real physical size",
    )
    solver.add_argument(
        "--size-mm",
        type=float,
        default=40.0,
        dest="size_mm",
        help="edge length for svg and pdf, in millimetres (default 40)",
    )
    solver.add_argument(
        "--ecc",
        choices=["same", "L", "M", "Q", "H"],
        default="same",
        help="error correction for the exported code. Default: the level the original carried. "
        "Raising it adds modules, so at a fixed printed size they get smaller",
    )
    solver.add_argument(
        "--split-payload",
        "--zigbee",
        dest="split",
        action="store_true",
        help="split a recognised payload (Zigbee, Matter, Wi-Fi) into fields in the json "
        "export. Off by default: install codes, passcodes and network keys are secrets",
    )
    solver.add_argument(
        "--fuse",
        choices=list(FUSION_RULES),
        default=DEFAULT_FUSION,
        help="how to combine several photographs. Default: average the probabilities, which is "
        "the conservative choice when the posterior is overconfident -- a disagreement then "
        "lands near a half instead of being averaged away in log-odds",
    )
    solver.set_defaults(func=cmd_solve)

    catalog = sub.add_parser(
        "catalog",
        help="recover many different codes and print them as an A4 catalogue",
    )
    catalog.add_argument(
        "image",
        type=Path,
        nargs="+",
        help="one photograph per code. For a code that needs several photographs, recover it "
        "with `solve` first and photograph the clean reprint",
    )
    catalog.add_argument(
        "--titles",
        nargs="*",
        help="one title per photograph, in order; file names fill the gaps",
    )
    catalog.add_argument(
        "--size-mm",
        type=float,
        default=50.0,
        dest="size_mm",
        help="printed edge length of each code in the catalogue (default 50)",
    )
    catalog.add_argument("--budget", type=int, default=4000)
    catalog.add_argument("--out", type=Path, default=Path("out"))
    catalog.set_defaults(func=cmd_catalog)

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
