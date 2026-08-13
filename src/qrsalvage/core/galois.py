"""Rechnen im Galois-Koerper GF(256) und Reed-Solomon-Decodierung mit Auslassungen.

Der Grund fuer dieses Modul steht in ensemble.py: Eine bessere Unsicherheitsschaetzung nuetzt
nichts, solange der Decoder sie nicht entgegennehmen kann. zxing kennt nur fertige Matrizen --
entweder eine Zelle ist hell oder dunkel. Reed-Solomon selbst kann mehr: Eine Zelle, von der
man sagt "ich weiss es nicht, aber ich weiss wo", kostet nur halb so viel Korrekturbudget wie
eine falsch geratene. Bei t Pruefzeichen sind t Auslassungen reparierbar, aber nur t/2 Fehler.

Genau diese Haelfte ist der Hebel des ganzen Projekts.

QR verwendet das Primitivpolynom 0x11D und einen Generator, dessen Nullstellen bei
alpha^0 beginnen.
"""

from __future__ import annotations

PRIMITIVE = 0x11D
GF_EXP = [0] * 512
GF_LOG = [0] * 256


def _build_tables() -> None:
    x = 1
    for i in range(255):
        GF_EXP[i] = x
        GF_LOG[x] = i
        x <<= 1
        if x & 0x100:
            x ^= PRIMITIVE
    for i in range(255, 512):
        GF_EXP[i] = GF_EXP[i - 255]


_build_tables()


def gf_mul(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return GF_EXP[GF_LOG[a] + GF_LOG[b]]


def gf_div(a: int, b: int) -> int:
    if b == 0:
        raise ZeroDivisionError("Division durch null in GF(256)")
    if a == 0:
        return 0
    return GF_EXP[(GF_LOG[a] + 255 - GF_LOG[b]) % 255]


def gf_pow(a: int, power: int) -> int:
    return GF_EXP[(GF_LOG[a] * power) % 255]


def gf_inverse(a: int) -> int:
    return GF_EXP[255 - GF_LOG[a]]


# --- Polynome, Koeffizienten absteigend nach Grad -------------------------------------


def poly_scale(p: list[int], x: int) -> list[int]:
    return [gf_mul(c, x) for c in p]


def poly_add(p: list[int], q: list[int]) -> list[int]:
    out = [0] * max(len(p), len(q))
    for i, c in enumerate(p):
        out[i + len(out) - len(p)] = c
    for i, c in enumerate(q):
        out[i + len(out) - len(q)] ^= c
    return out


def poly_mul(p: list[int], q: list[int]) -> list[int]:
    out = [0] * (len(p) + len(q) - 1)
    for j, qj in enumerate(q):
        if qj == 0:
            continue
        lq = GF_LOG[qj]
        for i, pi in enumerate(p):
            if pi:
                out[i + j] ^= GF_EXP[GF_LOG[pi] + lq]
    return out


def poly_eval(p: list[int], x: int) -> int:
    y = p[0]
    for c in p[1:]:
        y = gf_mul(y, x) ^ c
    return y


# --- Reed-Solomon ---------------------------------------------------------------------


class ReedSolomonError(Exception):
    """Der Block liess sich nicht reparieren. Kein Grund zur Panik, sondern eine Auskunft."""


def calc_syndromes(msg: list[int], nsym: int) -> list[int]:
    """Syndrome des empfangenen Blocks.

    Sind alle null, ist der Block fehlerfrei -- und das ist eine Aussage ueber den Block, nicht
    ueber unsere Hoffnung. Genau deshalb taugt Reed-Solomon als exaktes Orakel.
    """
    return [0] + [poly_eval(msg, gf_pow(2, i)) for i in range(nsym)]


def _errata_locator(positions: list[int]) -> list[int]:
    locator = [1]
    for p in positions:
        locator = poly_mul(locator, poly_add([1], [gf_pow(2, p), 0]))
    return locator


def _error_evaluator(synd: list[int], locator: list[int], nsym: int) -> list[int]:
    remainder = poly_mul(synd, locator)
    return remainder[len(remainder) - (nsym + 1) :]


def _forney_syndromes(synd: list[int], positions: list[int], msg_len: int) -> list[int]:
    """Syndrome von den bereits bekannten Auslassungen bereinigen.

    Ohne diesen Schritt sucht Berlekamp-Massey die Auslassungen als vermeintlich unbekannte
    Fehler noch einmal -- und scheitert, weil deren Anzahl die Korrekturgrenze sprengt. Die
    Bereinigung ist genau der Grund, warum eine Auslassung nur halb so teuer ist wie ein
    Fehler: ihr Ort ist schon verrechnet, bevor die eigentliche Suche beginnt.
    """
    umgekehrt = [msg_len - 1 - p for p in positions]
    fsynd = list(synd[1:])
    for pos in umgekehrt:
        x = gf_pow(2, pos)
        for j in range(len(fsynd) - 1):
            fsynd[j] = gf_mul(fsynd[j], x) ^ fsynd[j + 1]
    return fsynd


def _correct_errata(msg: list[int], synd: list[int], positions: list[int]) -> list[int]:
    """Forney-Algorithmus: Fehlerwerte an bekannten Stellen bestimmen und abziehen."""
    coef_pos = [len(msg) - 1 - p for p in positions]
    locator = _errata_locator(coef_pos)
    evaluator = _error_evaluator(synd[::-1], locator, len(locator) - 1)[::-1]

    # Fehlerstellen als Potenzen von alpha. Der Exponent ist die Koeffizientenposition
    # selbst -- nicht ihr Kehrwert, das war der Vorzeichenfehler beim ersten Anlauf.
    stellen = [gf_pow(2, c % 255) for c in coef_pos]

    magnitudes = [0] * len(msg)
    for i, xi in enumerate(stellen):
        xi_inv = gf_inverse(xi)
        # Ableitung des Lokatorpolynoms als Produkt ueber die uebrigen Stellen
        ableitung = 1
        for j, xj in enumerate(stellen):
            if j != i:
                ableitung = gf_mul(ableitung, 1 ^ gf_mul(xi_inv, xj))
        if ableitung == 0:
            raise ReedSolomonError("Nenner null im Forney-Schritt")

        y = gf_mul(xi, poly_eval(evaluator[::-1], xi_inv))
        magnitudes[positions[i]] = gf_div(y, ableitung)

    return [m ^ e for m, e in zip(msg, magnitudes, strict=True)]


def _find_error_locator(synd: list[int], nsym: int, erase_count: int = 0) -> list[int]:
    """Berlekamp-Massey, um die Stellen unbekannter Fehler zu finden."""
    locator, old = [1], [1]
    synd_shift = max(0, len(synd) - nsym)

    for i in range(nsym - erase_count):
        k = i + synd_shift
        delta = synd[k]
        for j in range(1, len(locator)):
            delta ^= gf_mul(locator[len(locator) - 1 - j], synd[k - j])
        old = [*old, 0]
        if delta != 0:
            if len(old) > len(locator):
                new = poly_scale(old, delta)
                old = poly_scale(locator, gf_inverse(delta))
                locator = new
            locator = poly_add(locator, poly_scale(old, delta))

    while locator and locator[0] == 0:
        locator.pop(0)
    errors = len(locator) - 1
    if (errors - erase_count) * 2 + erase_count > nsym:
        raise ReedSolomonError("zu viele Fehler fuer die vorhandene Redundanz")
    return locator


def _find_errors(locator: list[int], msg_len: int) -> list[int]:
    """Chien-Suche: an welchen Stellen hat das Lokatorpolynom eine Nullstelle?"""
    errors = [i for i in range(msg_len) if poly_eval(locator, gf_pow(2, i)) == 0]
    found = [msg_len - 1 - i for i in errors]
    if len(found) != len(locator) - 1:
        raise ReedSolomonError("Fehlerstellen nicht eindeutig bestimmbar")
    return sorted(found)


def correct_block(msg: list[int], nsym: int, erasures: list[int] | None = None):
    """Repariert einen Codewort-Block. Liefert (repariert, Fehlerstellen, Auslassungen).

    `erasures` sind Positionen, deren Wert unbekannt ist, deren Ort aber feststeht -- genau
    die Information, die aus einer unsicheren Modulzelle entsteht. Sie kosten ein Pruefzeichen
    statt zweier, und das verdoppelt die Reichweite des Decoders.
    """
    erasures = sorted(set(erasures or []))
    if len(erasures) > nsym:
        raise ReedSolomonError(f"{len(erasures)} Auslassungen bei nur {nsym} Pruefzeichen")

    work = list(msg)
    for p in erasures:
        work[p] = 0

    synd = calc_syndromes(work, nsym)
    if max(synd) == 0:
        return work, [], erasures

    # Erst die bekannten Auslassungen aus den Syndromen herausrechnen, dann nach dem suchen,
    # was uebrig bleibt. Diese Reihenfolge ist der ganze Vorteil der Ortskenntnis.
    fsynd = _forney_syndromes(synd, erasures, len(work))
    locator = _find_error_locator(fsynd, nsym, erase_count=len(erasures))
    error_pos = _find_errors(locator[::-1], len(work)) if len(locator) > 1 else []

    positions = sorted(set(erasures) | set(error_pos))
    repaired = _correct_errata(work, synd, positions)

    if max(calc_syndromes(repaired, nsym)) != 0:
        raise ReedSolomonError("Reparatur hat den Block nicht gueltig gemacht")
    return repaired, error_pos, erasures
