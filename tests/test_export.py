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
from qrsalvage.export import Layout, to_html_report, to_json, to_pdf, to_svg, zigbee_fields
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

    start = int(re.search(rb"startxref\s+(\d+)", pdf).group(1))
    assert pdf[start : start + 4] == b"xref"

    offsets = [int(m) for m in re.findall(r"^(\d{10}) 00000 n $", pdf[start:].decode(), re.M)]
    assert len(offsets) == 4
    for number, offset in enumerate(offsets, start=1):
        assert pdf[offset:].startswith(f"{number} 0 obj".encode()), f"object {number} misplaced"

    # The page has to be exactly the requested size: 40 mm is 113.386 points.
    assert re.search(rb"/MediaBox \[0 0 113\.38\d+ 113\.38\d+\]", pdf)


def test_pdf_size_scales_with_the_request():
    small = re.search(rb"/MediaBox \[0 0 ([\d.]+)", to_pdf(MATRIX, size_mm=20.0)).group(1)
    large = re.search(rb"/MediaBox \[0 0 ([\d.]+)", to_pdf(MATRIX, size_mm=80.0)).group(1)
    assert float(large) == pytest.approx(float(small) * 4, rel=1e-6)


def test_json_carries_the_evidence_not_only_the_answer(result):
    data = json.loads(to_json(result))
    assert data["recovered"] is True
    assert data["payload"] == TEXT
    # Without these a reader cannot judge the answer, which is the point of the format.
    for key in ("known_cells_wrong", "known_cells_total", "timing_pattern_percent", "version"):
        assert data[key] is not None, key


def test_the_pairing_secret_stays_out_unless_asked_for(result):
    zigbee_text = "Z:0123456789ABCDEF$I:00112233445566778899AABBCCDDEEFF1234%M:1189"

    plain = json.loads(to_json(result))
    assert "zigbee" not in plain

    fields = zigbee_fields(zigbee_text)
    assert fields["eui64"] == "0123456789ABCDEF"
    assert fields["eui64_colons"] == "F0:D1:B8:00:00:18:84:BB"
    assert fields["install_code_crc"] == "1234"
    assert fields["model"] == "1189"
    assert "secret" in fields["warning"]


def test_zigbee_parsing_declines_anything_else():
    assert zigbee_fields("https://example.com") is None
    assert zigbee_fields("MT:-0PK4KKN16RN.L6EB3P00SOV0E7TI") is None


def test_html_report_is_self_contained(result):
    page = to_html_report(result, b"\x89PNG-fake", b"\x89PNG-fake", b"\x89PNG-fake")
    assert page.startswith("<!doctype html>")
    assert TEXT in page
    assert "data:image/png;base64," in page
    # A report that fetches anything is a report that stops working offline, and one that could
    # leak the payload through a URL.
    assert "http://" not in page
    assert "https://" not in page.replace('<html lang="en">', "")
