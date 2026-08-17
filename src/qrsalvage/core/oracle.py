"""The outside oracle: decoding and encoding by an independent implementation.

The whole method leans on an oracle that does not advise but rules -- "valid" or "not valid" --
and on re-encoding through an implementation that is not this one, so a wrong reconstruction
cannot certify itself. Natively that oracle is zxing-cpp.

zxing-cpp is also the single native dependency of the entire core, which makes this seam the
one plank between qrsalvage and a browser: CPython on WebAssembly runs everything else as-is,
and zxing-cpp itself compiles to WASM. A runtime without the Python binding calls :func:`use`
once at boot and hands in the same oracle, compiled differently. The core never knows.

The native backend is imported lazily, so importing the core does not require the binding to
exist -- in the browser it never does.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

DecodeFn = Callable[[np.ndarray], str | None]
EncodeFn = Callable[[str, str | None], np.ndarray]

_decode_backend: DecodeFn | None = None
_encode_backend: EncodeFn | None = None


def use(decode: DecodeFn, encode: EncodeFn) -> None:
    """Replace the oracle for this process.

    `decode` takes a two-dimensional uint8 grey image of a rendered, upright code and returns
    its text or None. `encode` takes text and an error correction level ("L", "M", "Q", "H" or
    None for the encoder's choice) and returns a boolean module matrix, dark being True.
    """
    global _decode_backend, _encode_backend
    _decode_backend, _encode_backend = decode, encode


def _native() -> tuple[DecodeFn, EncodeFn]:
    import zxingcpp

    qr = zxingcpp.BarcodeFormat.QRCode
    qr_only = zxingcpp.BarcodeFormats(qr)
    # zxing-cpp's create_barcode takes its own level names.
    levels = {"L": "1", "M": "2", "Q": "3", "H": "4"}

    def decode(image: np.ndarray) -> str | None:
        try:
            hits = zxingcpp.read_barcodes(image, formats=qr_only, try_invert=False)
        except Exception:
            return None
        for hit in hits:
            if hit.text:
                return hit.text
        return None

    def encode(text: str, ec_level: str | None) -> np.ndarray:
        if ec_level is not None:
            barcode = zxingcpp.create_barcode(text, qr, ec_level=levels[ec_level])
        else:
            barcode = zxingcpp.create_barcode(text, qr)
        image = np.asarray(zxingcpp.write_barcode_to_image(barcode, scale=1, add_quiet_zones=False))
        if image.ndim == 3:
            image = image[:, :, 0]
        return image < 128

    return decode, encode


def decode(image: np.ndarray) -> str | None:
    """One decode attempt by the oracle. Never raises; an unreadable image is None."""
    global _decode_backend, _encode_backend
    if _decode_backend is None:
        _decode_backend, _encode_backend = _native()
    return _decode_backend(image)


def encode(text: str, ec_level: str | None = None) -> np.ndarray:
    """Encode afresh through the oracle, at the requested error correction level."""
    global _decode_backend, _encode_backend
    if _encode_backend is None:
        _decode_backend, _encode_backend = _native()
    return _encode_backend(text, ec_level)
