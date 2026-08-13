"""Misst die Erfolgsquote gegen den Schadensgrad -- mit Fehlerbalken.

Warum die Fehlerbalken noetig sind: bei vier Bildern je Stufe reicht das Konfidenzintervall
einer beobachteten Quote von 4/4 hinunter bis etwa 40 Prozent. Solche Zahlen sehen eindeutig
aus und tragen keine Aussage. Gemessen wird deshalb ueber viele Bilder je Stufe, und das
Intervall wird mit ausgegeben, damit sichtbar bleibt, was die Zahl aushaelt.

Variiert wird immer nur eine Schadensart, sonst ist eine gefundene Schwelle nicht zuzuordnen.

Aufruf:
    .venv\\Scripts\\python.exe scripts\\schwierigkeit.py
    .venv\\Scripts\\python.exe scripts\\schwierigkeit.py --achse kontrast --proben 24
"""

from __future__ import annotations

import argparse
import math
import time
from dataclasses import replace

from qrsalvage.core.decoding import reencode
from qrsalvage.core.pipeline import solve
from qrsalvage.synth import Damage, render_photo

TEXT = "Z:0123456789ABCDEF$I:00112233445566778899AABBCCDDEEFF1234%M:1189$D:008A454020"

BASIS = Damage(contrast=0.20, curvature=0.30, module_px=8.0, stain=0.0)

ACHSEN: dict[str, tuple[str, tuple[float, ...]]] = {
    "kontrast": ("contrast", (0.30, 0.24, 0.20, 0.16, 0.13, 0.11, 0.09)),
    "woelbung": ("curvature", (0.20, 0.35, 0.50, 0.65, 0.80, 0.95)),
    "aufloesung": ("module_px", (9.0, 8.0, 7.0, 6.0, 5.0, 4.0)),
    "fleck": ("stain", (0.0, 0.10, 0.20, 0.30, 0.40, 0.50)),
}


def wilson(erfolge: int, versuche: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson-Intervall fuer eine Binomialquote.

    Der Schulansatz p +/- z*sqrt(p(1-p)/n) versagt genau dort, wo wir am haeufigsten landen:
    bei Quoten nahe null oder eins liefert er Intervalle, die aus dem gueltigen Bereich
    hinauslaufen, und bei 0/n oder n/n eine Breite von null.
    """
    if versuche == 0:
        return (0.0, 1.0)
    p = erfolge / versuche
    nenner = 1 + z**2 / versuche
    mitte = (p + z**2 / (2 * versuche)) / nenner
    rand = z * math.sqrt(p * (1 - p) / versuche + z**2 / (4 * versuche**2)) / nenner
    return (max(0.0, mitte - rand), min(1.0, mitte + rand))


def messe(damage: Damage, proben: int, budget: int):
    """Loest `proben` unabhaengige Bilder desselben Schadensgrades."""
    matrix = reencode(TEXT)
    erfolge = 0
    falsche_zellen: list[int] = []
    versuche_gesamt = 0
    start = time.perf_counter()
    for seed in range(proben):
        photo = render_photo(matrix, damage, seed=seed)
        ergebnis = solve(photo, budget=budget)
        erfolge += int(ergebnis.solved)
        versuche_gesamt += ergebnis.candidates_tried
        if ergebnis.wrong_known is not None:
            falsche_zellen.append(ergebnis.wrong_known)
    dauer = time.perf_counter() - start
    mittel = sum(falsche_zellen) / len(falsche_zellen) if falsche_zellen else float("nan")
    return erfolge, mittel, versuche_gesamt, dauer


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--achse", choices=sorted(ACHSEN), default=None)
    ap.add_argument("--proben", type=int, default=20)
    ap.add_argument("--budget", type=int, default=4000)
    args = ap.parse_args()

    achsen = [args.achse] if args.achse else sorted(ACHSEN)
    print(f"Nutzlast {len(TEXT)} Zeichen, {args.proben} Bilder je Stufe, Budget {args.budget}")

    for name in achsen:
        feld, werte = ACHSEN[name]
        print(f"\n--- {name} (uebrige Schaeden fest auf Basiswert) ---")
        print(
            f"{name:>12} {'geloest':>10} {'Quote':>7} {'95%-Intervall':>16} "
            f"{'falsche Zellen':>15} {'Versuche':>9} {'Sek.':>6}"
        )
        for wert in werte:
            damage = replace(BASIS, **{feld: wert})
            erfolge, mittel, versuche, dauer = messe(damage, args.proben, args.budget)
            lo, hi = wilson(erfolge, args.proben)
            quote = erfolge / args.proben
            print(
                f"{wert:12.2f} {erfolge:5d}/{args.proben:<4d} {quote:7.0%} "
                f"{f'[{lo:.0%}, {hi:.0%}]':>16} {mittel:15.1f} {versuche:9d} {dauer:6.0f}",
                flush=True,  # sonst haengt bei Umleitung in eine Datei alles im Puffer
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
