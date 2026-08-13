"""A/B-Vergleich: Einzelmessung gegen Konsens aus mehreren Durchlaeufen.

Beide Verfahren sehen exakt dieselben Bilder, erzeugt aus denselben Startwerten. Verglichen
werden Erfolgsquote, Abtastfehler an den bekannten Zellen und der Aufwand des Solvers.

Der Aufwand gehoert dazu: ein Konsens, der die Erfolgsquote nicht hebt, aber die Zahl der
noetigen Tastversuche senkt, hat trotzdem etwas geleistet -- er hat die Reihenfolge verbessert.

Aufruf:
    .venv\\Scripts\\python.exe scripts\\ab_konsens.py --proben 12
"""

from __future__ import annotations

import argparse
import time
from dataclasses import replace

from qrsalvage.core.decoding import reencode
from qrsalvage.core.pipeline import solve
from qrsalvage.synth import Damage, render_photo

TEXT = "Z:0123456789ABCDEF$I:00112233445566778899AABBCCDDEEFF1234%M:1189$D:008A454020"
BASIS = Damage(contrast=0.20, curvature=0.30, module_px=8.0, stain=0.0)

STUFEN = (
    ("leicht", replace(BASIS, contrast=0.24)),
    ("mittel", replace(BASIS, contrast=0.16, curvature=0.40)),
    ("schwer", replace(BASIS, contrast=0.13, curvature=0.45, module_px=7.0, stain=0.15)),
    ("sehr schwer", replace(BASIS, contrast=0.11, curvature=0.55, module_px=6.5, stain=0.25)),
)


def lauf(damage: Damage, proben: int, budget: int, ensemble: str):
    matrix = reencode(TEXT)
    erfolge = 0
    fehler: list[int] = []
    versuche = 0
    start = time.perf_counter()
    for seed in range(proben):
        photo = render_photo(matrix, damage, seed=seed)
        ergebnis = solve(photo, budget=budget, ensemble=ensemble)
        erfolge += int(ergebnis.solved)
        versuche += ergebnis.candidates_tried
        # wrong_sampled, nicht wrong_known: gemessen wird die Abtastung, die wirklich gesucht
        # hat. wrong_known bewertet die Gitteranpassung und ist in allen Modi identisch.
        fehler.append(ergebnis.wrong_sampled if ergebnis.wrong_sampled is not None else -1)
    gueltig = sorted(f for f in fehler if f >= 0)
    median = gueltig[len(gueltig) // 2] if gueltig else float("nan")
    return erfolge, median, versuche, time.perf_counter() - start


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--proben", type=int, default=12)
    ap.add_argument("--budget", type=int, default=4000)
    ap.add_argument("--modi", nargs="*", default=["off", "geometry"])
    ap.add_argument("--stufen", nargs="*", default=None, help="Namen aus STUFEN, sonst alle")
    args = ap.parse_args()

    stufen = [s for s in STUFEN if args.stufen is None or s[0] in args.stufen]
    print(f"{args.proben} Bilder je Stufe, Budget {args.budget}, Modi {args.modi}\n")
    print(
        f"{'Stufe':>12} {'Modus':>10} {'geloest':>10} "
        f"{'falsch (Median)':>16} {'Versuche':>9} {'Sek.':>6}"
    )
    for name, damage in stufen:
        for modus in args.modi:
            erfolge, median, versuche, dauer = lauf(damage, args.proben, args.budget, modus)
            print(
                f"{name:>12} {modus:>10} {erfolge:5d}/{args.proben:<4d} "
                f"{median:16.0f} {versuche:9d} {dauer:6.0f}",
                flush=True,  # sonst haengt bei Umleitung in eine Datei alles im Puffer
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
