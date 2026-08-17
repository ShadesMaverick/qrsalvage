"""Arithmetic in GF(256) and Reed-Solomon decoding with erasures.

The reason this module exists is in ensemble.py: a better uncertainty estimate is worthless
unless the decoder can accept it. zxing only takes finished matrices -- a cell is either dark
or light. Reed-Solomon can do more. A cell you describe as "I don't know the value, but I know
where it is" costs only half the correction budget of a wrongly guessed one: with t check
symbols you can repair t erasures but only t/2 errors.

That factor of two is the lever the whole project rests on.

QR uses the primitive polynomial 0x11D and a generator whose roots start at alpha^0.
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
        raise ZeroDivisionError("division by zero in GF(256)")
    if a == 0:
        return 0
    return GF_EXP[(GF_LOG[a] + 255 - GF_LOG[b]) % 255]


def gf_pow(a: int, power: int) -> int:
    return GF_EXP[(GF_LOG[a] * power) % 255]


def gf_inverse(a: int) -> int:
    return GF_EXP[255 - GF_LOG[a]]


# --- Polynomials, coefficients in descending order of degree ---------------------------


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
        log_qj = GF_LOG[qj]
        for i, pi in enumerate(p):
            if pi:
                out[i + j] ^= GF_EXP[GF_LOG[pi] + log_qj]
    return out


def poly_eval(p: list[int], x: int) -> int:
    y = p[0]
    for c in p[1:]:
        y = gf_mul(y, x) ^ c
    return y


# --- Reed-Solomon ----------------------------------------------------------------------


class ReedSolomonError(Exception):
    """The block could not be repaired. Not a crash, an answer."""


def calc_syndromes(msg: list[int], nsym: int) -> list[int]:
    """Syndromes of the received block.

    If they are all zero the block is intact -- and that is a statement about the block, not
    about our hopes. It is what makes Reed-Solomon usable as an exact oracle.
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
    """Strip the already known erasures out of the syndromes.

    Without this step Berlekamp-Massey would go looking for the erasures again as if they were
    unknown errors, and fail because their number exceeds the correction limit. This removal is
    precisely why an erasure costs half of what an error costs: its position is accounted for
    before the search even starts.
    """
    reversed_positions = [msg_len - 1 - p for p in positions]
    forney = list(synd[1:])
    for position in reversed_positions:
        x = gf_pow(2, position)
        for j in range(len(forney) - 1):
            forney[j] = gf_mul(forney[j], x) ^ forney[j + 1]
    return forney


def _correct_errata(msg: list[int], synd: list[int], positions: list[int]) -> list[int]:
    """Forney's algorithm: determine the error values at known positions and subtract them."""
    coefficient_positions = [len(msg) - 1 - p for p in positions]
    locator = _errata_locator(coefficient_positions)
    evaluator = _error_evaluator(synd[::-1], locator, len(locator) - 1)[::-1]

    # Error positions as powers of alpha. The exponent is the coefficient position itself,
    # not its reciprocal -- that sign error cost an afternoon the first time round.
    roots = [gf_pow(2, c % 255) for c in coefficient_positions]

    magnitudes = [0] * len(msg)
    for i, xi in enumerate(roots):
        xi_inv = gf_inverse(xi)
        # Derivative of the locator polynomial as a product over the remaining roots
        derivative = 1
        for j, xj in enumerate(roots):
            if j != i:
                derivative = gf_mul(derivative, 1 ^ gf_mul(xi_inv, xj))
        if derivative == 0:
            raise ReedSolomonError("zero denominator in the Forney step")

        y = gf_mul(xi, poly_eval(evaluator[::-1], xi_inv))
        magnitudes[positions[i]] = gf_div(y, derivative)

    return [m ^ e for m, e in zip(msg, magnitudes, strict=True)]


def _find_error_locator(synd: list[int], nsym: int, erase_count: int = 0) -> list[int]:
    """Berlekamp-Massey, to locate the errors whose positions are not known."""
    locator, previous = [1], [1]
    shift = max(0, len(synd) - nsym)

    for i in range(nsym - erase_count):
        k = i + shift
        delta = synd[k]
        for j in range(1, len(locator)):
            delta ^= gf_mul(locator[len(locator) - 1 - j], synd[k - j])
        previous = [*previous, 0]
        if delta != 0:
            if len(previous) > len(locator):
                scaled = poly_scale(previous, delta)
                previous = poly_scale(locator, gf_inverse(delta))
                locator = scaled
            locator = poly_add(locator, poly_scale(previous, delta))

    while locator and locator[0] == 0:
        locator.pop(0)
    errors = len(locator) - 1
    if (errors - erase_count) * 2 + erase_count > nsym:
        raise ReedSolomonError("too many errors for the available redundancy")
    return locator


def _find_errors(locator: list[int], msg_len: int) -> list[int]:
    """Chien search: at which positions does the locator polynomial vanish?"""
    roots = [i for i in range(msg_len) if poly_eval(locator, gf_pow(2, i)) == 0]
    found = [msg_len - 1 - i for i in roots]
    if len(found) != len(locator) - 1:
        raise ReedSolomonError("error positions are not uniquely determined")
    return sorted(found)


def correct_block(
    msg: list[int], nsym: int, erasures: list[int] | None = None
) -> tuple[list[int], list[int], list[int]]:
    """Repair one codeword block. Returns (repaired, error positions, erasures used).

    `erasures` are positions whose value is unknown but whose location is certain -- exactly
    the information an uncertain module cell produces. They consume one check symbol instead of
    two, which doubles the reach of the decoder.
    """
    erasures = sorted(set(erasures or []))
    if len(erasures) > nsym:
        raise ReedSolomonError(f"{len(erasures)} erasures but only {nsym} check symbols")

    work = list(msg)
    for p in erasures:
        work[p] = 0

    synd = calc_syndromes(work, nsym)
    if max(synd) == 0:
        return work, [], erasures

    # First remove the known erasures from the syndromes, then search for whatever is left.
    # That order is the entire advantage of knowing where the damage is.
    forney = _forney_syndromes(synd, erasures, len(work))
    locator = _find_error_locator(forney, nsym, erase_count=len(erasures))
    error_positions = _find_errors(locator[::-1], len(work)) if len(locator) > 1 else []

    positions = sorted(set(erasures) | set(error_positions))
    repaired = _correct_errata(work, synd, positions)

    if max(calc_syndromes(repaired, nsym)) != 0:
        raise ReedSolomonError("the repair did not make the block valid")
    return repaired, error_positions, erasures
