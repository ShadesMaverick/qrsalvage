"""The export formats, and the physical size they promise.

Whether a printed code can be read is decided by the size of a module in millimetres. An export
that silently gets that wrong produces something that looks right and does not scan, which is
the worst failure this project can have.
"""

from __future__ import annotations

import json
import re

import pytest

from qrsalvage.core.decoding import reencode
from qrsalvage.core.pipeline import solve
from qrsalvage.export import (
    Layout,
    matter_fields,
    payload_fields,
    to_catalog_pdf,
    to_html_report,
    to_json,
    to_pdf,
    to_svg,
    wifi_fields,
    zigbee_fields,
)
from qrsalvage.synth import Damage, render_photo

TEXT = "QRSALVAGE-EXPORT-TEST-0815"
MATRIX = reencode(TEXT)


@pytest.fixture(scope="module")
def result():
    photo = render_photo(MATRIX, Damage(contrast=0.24, curvature=0.25), seed=0)
    outcome = solve(photo)
    assert outcome.solved
    return outcome


def test_layout_divides_the_page_including_the_quiet_zone():
    layout = Layout(modules=29, quiet=4, size_mm=40.0)
    assert layout.total_modules == 37
    assert layout.module_mm * 37 == pytest.approx(40.0)


def test_svg_declares_the_size_in_millimetres():
    svg = to_svg(MATRIX, size_mm=35.0)
    assert 'width="35.0mm"' in svg
    assert 'height="35.0mm"' in svg
    # The viewBox has to match the physical size, or the units are decorative.
    assert 'viewBox="0 0 35.0 35.0"' in svg
    assert svg.count("<rect") > 20


def test_svg_rectangles_stay_inside_the_page():
    size = 40.0
    svg = to_svg(MATRIX, size_mm=size)
    for x, y, w, h in re.findall(
        r'<rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)"/>', svg
    ):
        assert float(x) + float(w) <= size + 1e-6
        assert float(y) + float(h) <= size + 1e-6


def test_pdf_is_structurally_valid():
    """No PDF library here, so the structure is checked by hand.

    The one thing a hand-written PDF gets wrong is the cross-reference table: every entry is a
    byte offset into the file, and a reader that finds the wrong bytes there rejects the whole
    document. So the offsets are followed and required to land on their object headers.
    """
    pdf = to_pdf(MATRIX, size_mm=40.0)
    assert pdf.startswith(b"%PDF-1.4")
    assert pdf.rstrip().endswith(b"%%EOF")

    trailer = re.search(rb"startxref\s+(\d+)", pdf)
    assert trailer is not None
    start = int(trailer.group(1))
    assert pdf[start : start + 4] == b"xref"

    offsets = [int(m) for m in re.findall(r"^(\d{10}) 00000 n $", pdf[start:].decode(), re.M)]
    assert len(offsets) == 4
    for number, offset in enumerate(offsets, start=1):
        assert pdf[offset:].startswith(f"{number} 0 obj".encode()), f"object {number} misplaced"

    # The page has to be exactly the requested size: 40 mm is 113.386 points.
    assert re.search(rb"/MediaBox \[0 0 113\.38\d+ 113\.38\d+\]", pdf)


def test_pdf_size_scales_with_the_request():
    small = re.search(rb"/MediaBox \[0 0 ([\d.]+)", to_pdf(MATRIX, size_mm=20.0))
    large = re.search(rb"/MediaBox \[0 0 ([\d.]+)", to_pdf(MATRIX, size_mm=80.0))
    assert small is not None and large is not None
    assert float(large.group(1)) == pytest.approx(float(small.group(1)) * 4, rel=1e-6)


def test_json_carries_the_evidence_not_only_the_answer(result):
    data = json.loads(to_json(result))
    assert data["recovered"] is True
    assert data["payload"] == TEXT
    # Without these a reader cannot judge the answer, which is the point of the format.
    for key in ("known_cells_wrong", "known_cells_total", "timing_pattern_percent", "version"):
        assert data[key] is not None, key


def test_the_pairing_secret_stays_out_unless_asked_for(result):
    zigbee_text = "Z:AABBCCDDEEFF0011$I:00112233445566778899AABBCCDDEEFF1234%M:0007"

    plain = json.loads(to_json(result))
    assert "zigbee" not in plain

    fields = zigbee_fields(zigbee_text)
    assert fields is not None
    assert fields["eui64"] == "AABBCCDDEEFF0011"
    assert fields["eui64_colons"] == "AA:BB:CC:DD:EE:FF:00:11"
    assert fields["install_code_crc"] == "1234"
    assert fields["model"] == "0007"
    assert "secret" in fields["warning"]


def test_zigbee_parsing_declines_anything_else():
    assert zigbee_fields("https://example.com") is None
    assert zigbee_fields("MT:-0PK4KKN16RN.L6EB3P00SOV0E7TI") is None


def test_matter_payload_yields_the_manual_pairing_code():
    """Anchored to the canonical Matter test vector, not to this implementation.

    MT:Y.K9042C00KA0648G00 is the payload every chip-tool tutorial uses; its passcode
    (20202021), discriminator (0xF00) and manual pairing code (34970112332) are published
    values. Three independent anchors -- the manual code exercises the whole chain including
    the Verhoeff check digit -- make a quietly transposed lookup table loud.
    """
    fields = matter_fields("MT:Y.K9042C00KA0648G00")
    assert fields is not None
    assert fields["setup_passcode"] == "20202021"
    assert fields["discriminator"] == 0xF00
    assert fields["manual_pairing_code"] == "3497-011-2332"
    assert fields["vendor_id"] == 0xFFF1
    assert fields["product_id"] == 0x8000
    assert fields["commissioning_flow"] == "standard"
    assert "BLE" in fields["discovery"]
    assert "key" in fields["warning"]

    assert matter_fields("MT:NOT-BASE38!!") is None
    assert matter_fields("WIFI:S:x;;") is None


def test_wifi_payload_honours_the_escaping():
    fields = wifi_fields("WIFI:S:My\;Home;T:WPA;P:pa\\ss word;H:true;;")
    assert fields is not None
    assert fields["ssid"] == "My;Home"
    assert fields["password"] == "pass word"
    assert fields["security"] == "WPA"
    assert fields["hidden"] is True
    assert wifi_fields("plain text") is None


def test_payload_kinds_are_recognised_and_split_only_on_request(result):
    parsed = payload_fields("MT:Y.K9042C00KA0648G00")
    assert parsed is not None
    kind, fields = parsed
    assert kind == "matter" and "manual_pairing_code" in fields
    assert payload_fields("QRSALVAGE-PLAIN") is None


def test_html_report_is_self_contained(result):
    page = to_html_report(result, b"\x89PNG-fake", b"\x89PNG-fake", b"\x89PNG-fake")
    assert page.startswith("<!doctype html>")
    assert TEXT in page
    assert "data:image/png;base64," in page
    # A report that fetches anything is a report that stops working offline, and one that could
    # leak the payload through a URL.
    assert "http://" not in page
    assert "https://" not in page.replace('<html lang="en">', "")


def test_catalog_pdf_puts_three_entries_on_a_page():
    """The catalogue: A4, three rows, title and payload next to each code."""
    entry = {"title": "LED Lampe Badezimmer", "text": "CATALOG-TEST-0815", "matrix": MATRIX}
    pdf = to_catalog_pdf([dict(entry) for _ in range(4)], size_mm=50.0)

    assert pdf.startswith(b"%PDF-")
    assert pdf.count(b"/Type /Page ") == 2, "four entries at three per page are two pages"
    # A4 in points, i.e. the entries did not inherit the single-code square page.
    assert b"/MediaBox [0 0 595.2756 841.8898]" in pdf
    # The title reaches the page, umlaut-safe via WinAnsi.
    assert b"(LED Lampe Badezimmer)" in pdf
    assert pdf.count(b"(CATALOG-TEST-0815)") == 4

    # The cross-reference table has to be honest here too.
    import re as regex

    trailer = regex.search(rb"startxref\s+(\d+)", pdf)
    assert trailer is not None
    start = int(trailer.group(1))
    assert pdf[start : start + 4] == b"xref"


def test_catalog_pdf_escapes_what_would_break_a_pdf_string():
    backslash = chr(92)
    entry = {
        "title": f"Heizung (Keller) {backslash} Haupthaus",
        "text": "PAREN(THESES)",
        "matrix": MATRIX,
    }
    pdf = to_catalog_pdf([entry])
    # Parentheses escape to backslash-paren, a backslash doubles.
    expected = b"(Heizung " + rb"\(Keller\) \\ " + b"Haupthaus)"
    assert expected in pdf
    assert rb"(PAREN\(THESES\))" in pdf


def test_catalog_pdf_refuses_to_be_empty():
    import pytest as _pytest

    with _pytest.raises(ValueError):
        to_catalog_pdf([])


def test_catalog_codes_survive_the_round_trip():
    """The catalogue's reason to exist: every printed code must scan back to its text.

    The PDF's content stream is uncompressed and every dark module is a filled `re` rectangle,
    so the page can be rasterised from the file itself -- no PDF library, no dependence on a
    viewer. What zxing reads out of that raster is exactly what a phone will read off the
    printed page, minus the printer.
    """
    import re as regex

    import numpy as np
    import zxingcpp

    from qrsalvage.export import A4_HEIGHT, A4_WIDTH

    texts = ["CATALOG-ROUNDTRIP-A-01", "CATALOG-ROUNDTRIP-B-02", "CATALOG-ROUNDTRIP-C-03"]
    entries = [
        {"title": f"entry {i}", "text": t, "matrix": reencode(t)} for i, t in enumerate(texts)
    ]
    pdf = to_catalog_pdf(entries, size_mm=50.0)

    scale = 3.0  # pixels per point; about 216 dpi, an ordinary office printer
    page = np.full((int(A4_HEIGHT * scale) + 1, int(A4_WIDTH * scale) + 1), 255, dtype=np.uint8)
    stream = pdf.split(b"stream\n", 1)[1].split(b"\nendstream", 1)[0].decode("ascii")
    for x, y, w, h in regex.findall(r"([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+) re", stream):
        x, y, w, h = float(x), float(y), float(w), float(h)
        top = int(round((A4_HEIGHT - y - h) * scale))
        left = int(round(x * scale))
        page[top : top + int(round(h * scale)), left : left + int(round(w * scale))] = 0

    hits = {hit.text for hit in zxingcpp.read_barcodes(page) if hit.text}
    assert hits == set(texts), f"scanned back {hits}"
