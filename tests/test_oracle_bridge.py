"""The encoder, pinned — so the browser build and the native build cannot drift apart.

The browser build does not use zxing-cpp through its Python binding; it calls the same library
compiled to WebAssembly, through a bridge in web/worker.js. Both are supposed to be the same
encoder, but "supposed to" is not a measurement, and a silent divergence here would be
particularly nasty: a re-encoded code is what a person prints on a label or types into a hub,
and a wrong one fails only later, in their hands.

So the two were compared directly. The matrices below were produced by the WASM encoder in a
browser (Chrome, zxing-wasm 2.x) via that bridge -- byte per module, dark below 128, quiet zone
stripped -- and hashed. Every case matched the native encoder exactly, including the default
level, where the encoder rather than the caller chooses.

Keeping the hashes here turns that one-off comparison into a standing guard: if a future
zxing-cpp bump changes what the native side emits, this test fails and the browser bridge has
to be re-measured rather than assumed. If it ever does fail, re-run the comparison in the
browser before touching these numbers -- the point is that both sides move together.
"""

from __future__ import annotations

import hashlib

import pytest

from qrsalvage.core.decoding import reencode

# text, error correction level (None = the encoder's choice), module count, sha256 prefix
BROWSER_MEASURED = [
    ("MT:Y.K9042C00KA0648G00", "M", 25, "68dc673b3a5bba70"),
    ("MT:Y.K9042C00KA0648G00", None, 21, "39d2fd2d5ca7689a"),
    ("HI", "H", 21, "e576996630347c93"),
    ("HI", "L", 21, "766046ec8d6fa82a"),
    ("Z:AABBCCDDEEFF0011$I:12345678901234567890123456789012", "L", 25, "34487c31161d7c7d"),
    ("WIFI:S:MyNetwork;T:WPA;P:secret123;;", "Q", 33, "0ed511a09688aca2"),
]


def _fingerprint(matrix) -> str:
    rows = "\n".join("".join("1" if cell else "0" for cell in row) for row in matrix)
    return hashlib.sha256(rows.encode("ascii")).hexdigest()[:16]


@pytest.mark.parametrize(("text", "ecc", "modules", "digest"), BROWSER_MEASURED)
def test_the_encoder_agrees_with_the_one_compiled_to_webassembly(text, ecc, modules, digest):
    matrix = reencode(text, ecc=ecc)
    assert matrix.shape == (modules, modules)
    assert _fingerprint(matrix) == digest


def test_the_levels_really_are_different_codes():
    """Guards the guard: identical hashes across levels would make the test above vacuous."""
    digests = {ecc: _fingerprint(reencode("HI", ecc=ecc)) for ecc in ("L", "M", "Q", "H")}
    assert len(set(digests.values())) == 4
