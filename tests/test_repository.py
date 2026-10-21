"""Contracts for files that publish the project rather than run it."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


@dataclass
class _Element:
    tag: str
    attrs: dict[str, str | None] = field(default_factory=dict)
    children: list[_Element | str] = field(default_factory=list)

    @property
    def text(self) -> str:
        parts = [child.text if isinstance(child, _Element) else child for child in self.children]
        return " ".join(" ".join(parts).split())

    def elements(self, tag: str | None = None) -> list[_Element]:
        descendants: list[_Element] = []
        for child in self.children:
            if not isinstance(child, _Element):
                continue
            if tag is None or child.tag == tag:
                descendants.append(child)
            descendants.extend(child.elements(tag))
        return descendants

    def direct_elements(self, tag: str | None = None) -> list[_Element]:
        return [
            child
            for child in self.children
            if isinstance(child, _Element) and (tag is None or child.tag == tag)
        ]

    def has_class(self, name: str) -> bool:
        return name in (self.attrs.get("class") or "").split()


class _DocumentParser(HTMLParser):
    _VOID_ELEMENTS = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Element("document")
        self._stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        element = _Element(tag, dict(attrs))
        self._stack[-1].children.append(element)
        if tag not in self._VOID_ELEMENTS:
            self._stack.append(element)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._stack[-1].children.append(_Element(tag, dict(attrs)))

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self._stack) - 1, 0, -1):
            if self._stack[index].tag == tag:
                del self._stack[index:]
                return

    def handle_data(self, data: str) -> None:
        self._stack[-1].children.append(data)


def _document(path: str) -> _Element:
    parser = _DocumentParser()
    parser.feed(_text(path))
    parser.close()
    return parser.root


def _only(elements: list[_Element], description: str) -> _Element:
    assert len(elements) == 1, f"expected one {description}, found {len(elements)}"
    return elements[0]


def test_companion_sprite_has_six_square_transparent_frames():
    from PIL import Image

    path = ROOT / "src" / "qrsalvage" / "web" / "axolotl-companion.png"
    with Image.open(path) as image:
        assert image.mode == "RGBA"
        assert image.width == image.height * 6
        assert image.getchannel("A").getextrema()[0] == 0


def test_pages_builds_only_the_exact_successful_main_ci_commit():
    workflow = _text(".github/workflows/pages.yml")

    assert "workflow_run:" in workflow
    assert "workflows: [CI]" in workflow
    assert "types: [completed]" in workflow
    assert "workflow_dispatch:" not in workflow
    assert "github.event.workflow_run.conclusion == 'success'" in workflow
    assert "github.event.workflow_run.event == 'push'" in workflow
    assert "github.event.workflow_run.head_branch == 'main'" in workflow
    assert "ref: ${{ github.event.workflow_run.head_sha }}" in workflow


def test_installation_uses_a_source_that_exists_today():
    readme = _text("README.md")

    assert "pip install qrsalvage\n" not in readme
    assert "pip install git+https://github.com/ShadesMaverick/qrsalvage.git" in readme


def test_package_metadata_points_back_to_the_public_project():
    metadata = tomllib.loads(_text("pyproject.toml"))["project"]

    assert metadata["urls"] == {
        "Homepage": "https://shadesmaverick.github.io/qrsalvage/",
        "Repository": "https://github.com/ShadesMaverick/qrsalvage",
        "Issues": "https://github.com/ShadesMaverick/qrsalvage/issues",
    }


def _meta_csp(path: str) -> str:
    page = _text(path)
    match = re.search(
        r'<meta http-equiv="Content-Security-Policy" content="([^"]+)"',
        page,
        flags=re.DOTALL,
    )
    assert match is not None, f"missing meta CSP in {path}"
    return match.group(1)


def test_static_pages_do_not_claim_header_only_csp_directives():
    for path in (
        "src/qrsalvage/web/index.html",
        "src/qrsalvage/web/method.html",
        "src/qrsalvage/web/legal.html",
    ):
        assert "frame-ancestors" not in _meta_csp(path), path


def test_privacy_explanation_credits_code_audit_and_policy_together():
    legal = _text("src/qrsalvage/web/legal.html")

    assert "Der Anwendungscode enthält keinen Uploadpfad" in legal
    assert "Der Build prüft die ausgelieferten Textdateien" in legal
    assert "weshalb Ihr Browser einen Upload gar nicht erst zuließe" not in legal


def test_method_and_legal_load_exactly_the_locale_script_and_no_other_code():
    for name in ("method.html", "legal.html"):
        document = _document(f"src/qrsalvage/web/{name}")
        assert any(element.has_class("site-nav") for element in document.elements("nav"))
        assert {element.attrs.get("data-locale") for element in document.elements("button")} == {
            "de",
            "en",
        }

        scripts = document.elements("script")
        assert [script.attrs.get("src") for script in scripts] == ["locale.js"]
        assert all(not script.text for script in scripts), "secondary pages must not embed script"


def test_signal_manual_preserves_ordered_bilingual_chapters_and_technical_evidence():
    document = _document("src/qrsalvage/web/method.html")
    article = _only(
        [
            element
            for element in document.elements("article")
            if element.has_class("manual-content")
        ],
        "manual article",
    )
    sections = article.direct_elements("section")
    expected_ids = ("known", "levels", "posterior", "grid", "search", "probe", "rs", "limits")
    assert tuple(section.attrs.get("id") for section in sections) == expected_ids

    expected_shapes = {
        "known": (0, ("fig-known.svg",)),
        "levels": (0, ("fig-levels.svg",)),
        "posterior": (0, ("fig-posterior.svg",)),
        "grid": (0, ("fig-objective.svg",)),
        "search": (0, ()),
        "probe": (0, ("fig-probe.svg",)),
        "rs": (0, ("fig-rs.svg",)),
        "limits": (1, ()),
    }
    expected_language_blocks = {
        "known": ("en", "de", "en", "de"),
        "levels": ("en", "de", "en", "de"),
        "posterior": ("en", "de", "en", "de"),
        "grid": ("en", "de", "en", "de", "en", "de"),
        "search": ("en", "de"),
        "probe": ("en", "de", "en", "de", "en", "de"),
        "rs": ("en", "de", "en", "de"),
        "limits": ("en", "de", "en", "de"),
    }
    expected_formulas = {
        "known": (),
        "levels": (
            (
                "D(r,c) = a₀ + a₁r + a₂c + a₃r² + a₄c² + a₅rc",
                "L(r,c) = b₀ + b₁r + b₂c + b₃r² + b₄c² + b₅rc",
                "a = argmin Σ known dark ( D(r,c) − mean(r,c) )²",
            ),
            ("T(r,c) = ( D + L ) / 2 C(r,c) = max( L − D , ε )",),
        ),
        "posterior": (
            (
                "ℓ(r,c) = [ (x − L̂)² − (x − D̂)² ] / ( 2σ(r,c)² )",
                "P(dark) = 1 / ( 1 + e −ℓ )",
            ),
            ("σ(r,c) = √( σ₀² + ( k · max(0, s(r,c) − s̄) / C )² )",),
        ),
        "grid": (
            (
                "m(r,c) = ± ( T(r,c) − mean(r,c) ) / C(r,c)",
                "Q = mean known tanh( 4 · m )",
            ),
        ),
        "search": (),
        "probe": (("cost(r,c) = log( max(p, 1−p) / min(p, 1−p) )",),),
        "rs": (("2·e unknown + e located ≤ t",),),
        "limits": (),
    }
    evidence = {
        "known": ("244 of 841 cells", "244 von 841 Zellen", "about 29 %"),
        "levels": (
            "roughly 120 known cells",
            "sixteen grey values out of 255",
            "ungefähr 120 bekannten Zellen",
        ),
        "posterior": (
            "k = 1.5",
            "0.02 of the local contrast against 0.09",
            "±0.15",
            "zero wrong known cells and zero uncertain cells",
        ),
        "grid": (
            "δ starts at 3 px and stops below 0.05 px",
            "18 wrong known cells to 2",
            "free 3×3 control lattice — eighteen parameters",
        ),
        "search": (
            "2 of 244 cells wrong and the runner-up 69",
            "roughly nine pixels per module",
            "six discrete possibilities",
        ),
        "probe": (
            "a cell at p = 0.5 is free to flip",
            "0.22 against 5.6",
            "a factor of twenty-five",
        ),
        "rs": (
            "primitive polynomial 0x11D",
            "three states rather than two",
            "{2,4,6,8,10,12,14,16,18}",
            "covering rank 18 costs 18 of 15 symbols — while the exact set costs 9",
        ),
        "limits": (
            "6.0 5 / 5",
            "4.0 1 / 5",
            "3.0 0 / 5",
            "thirteen genuinely damaged codes",
            "recovers six and places the grid cleanly on nine",
        ),
    }

    all_figure_sources: list[str | None] = []
    for section in sections:
        section_id = section.attrs.get("id")
        assert section_id is not None
        language_blocks = [
            child
            for child in section.direct_elements()
            if child.attrs.get("data-lang") in {"en", "de"}
        ]
        assert language_blocks
        assert (
            tuple(block.attrs["data-lang"] for block in language_blocks)
            == (expected_language_blocks[section_id])
        )
        assert all(block.text for block in language_blocks)

        formula_blocks = [
            element for element in section.elements("div") if element.has_class("formula")
        ]
        formula_signatures = expected_formulas[section_id]
        assert len(formula_blocks) == len(formula_signatures)
        for formula_block, signature in zip(formula_blocks, formula_signatures, strict=True):
            for literal in signature:
                assert literal in formula_block.text, (
                    f"{section_id} has the wrong formula block: {literal}"
                )

        table_count, figure_sources = expected_shapes[section_id]
        assert len(section.elements("table")) == table_count
        actual_sources = tuple(image.attrs.get("src") for image in section.elements("img"))
        assert actual_sources == figure_sources
        assert len(section.elements("figure")) == len(figure_sources)
        all_figure_sources.extend(actual_sources)

        for literal in evidence[section_id]:
            assert literal in section.text, f"{section_id} lost technical evidence: {literal}"

    assert all_figure_sources == [
        "fig-known.svg",
        "fig-levels.svg",
        "fig-posterior.svg",
        "fig-objective.svg",
        "fig-probe.svg",
        "fig-rs.svg",
    ]


def test_secondary_pages_use_the_exact_local_only_policy_and_metadata_hooks():
    expected = (
        "default-src 'self'; img-src 'self' data: blob:; style-src 'self'; "
        "script-src 'self'; connect-src 'none'; object-src 'none'; base-uri 'none'; "
        "form-action 'none'"
    )
    for name in ("method.html", "legal.html"):
        path = f"src/qrsalvage/web/{name}"
        page = _text(path)
        assert " ".join(_meta_csp(path).split()) == expected
        for hook in (
            "data-title-en=",
            "data-title-de=",
            "data-description-en=",
            "data-description-de=",
        ):
            assert hook in page


def test_bilingual_legal_page_preserves_authoritative_facts_in_both_languages():
    document = _document("src/qrsalvage/web/legal.html")
    main = _only(
        [element for element in document.elements("main") if element.has_class("legal-page")],
        "legal main",
    )
    sections = main.direct_elements("section")
    assert [section.attrs.get("data-lang") for section in sections] == ["de", "en"]
    german, english = sections
    assert "The German version is authoritative." in english.text

    privacy_url = "https://docs.github.com/de/site-policy/privacy-policies/github-privacy-statement"
    repository_url = "https://github.com/ShadesMaverick/qrsalvage"
    for block in sections:
        for fact in (
            "Fabian Marius Freitag",
            "Wilhelmstraße 9/1",
            "73779 Deizisau",
            "f.freitag@ik.me",
        ):
            assert fact in block.text
        links = {link.attrs.get("href") for link in block.elements("a")}
        assert privacy_url in links
        assert repository_url in links
        for article in ("§ 5 DDG", "Art. 6", "Art. 46 DSGVO", "Art. 15 bis 21 DSGVO"):
            assert article in block.text

    for obligation in (
        "verlassen Ihr Gerät nicht",
        "Die gesamte Rekonstruktion läuft in Ihrem Browser",
        "GitHub Pages",
        "IP-Adresse, Datum und Uhrzeit",
        "nicht dauerhaft gespeichert",
        "verschwinden mit dem Schließen des Tabs",
        "Ohne Klick wird zu diesen Anbietern keinerlei Verbindung aufgebaut",
        "Auskunft, Berichtigung, Löschung",
        "Beschwerderecht bei einer Datenschutz-Aufsichtsbehörde",
        "naturgemäß nicht garantieren",
        "Haftung für Schäden",
    ):
        assert obligation in german.text
    for obligation in (
        "do not leave your device",
        "entire reconstruction runs in your browser",
        "GitHub Pages",
        "IP address, date and time",
        "are not stored permanently",
        "disappear when the tab is closed",
        "Without a click, no connection to these providers is made",
        "access, rectification, erasure",
        "right to lodge a complaint",
        "cannot guarantee that recovered content is the original content",
        "Liability for damage",
    ):
        assert obligation in english.text

    assert "TODO" not in german.text
    assert "TODO" not in english.text


def test_ci_requirements_are_the_recorded_toolchain():
    lines = {
        line.strip()
        for line in _text("requirements.txt").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert lines == {
        'numpy==2.4.6; python_version < "3.12"',
        'numpy==2.5.4; python_version >= "3.12"',
        "opencv-python==5.0.0.93",
        "pillow==12.3.0",
        "zxing-cpp==3.1.1",
        "pytest==9.1.1",
        "ruff==0.17.1",
        "mypy==2.4.0",
    }


def test_workflows_pin_actions_to_reviewed_commits():
    workflows = _text(".github/workflows/ci.yml") + _text(".github/workflows/pages.yml")
    expected = {
        "actions/checkout": "11d5960a326750d5838078e36cf38b85af677262",
        "actions/setup-python": "a26af69be951a213d495a4c3e4e4022e16d87065",
        "actions/cache": "0057852bfaa89a56745cba8c7296529d2fc39830",
        "actions/upload-pages-artifact": "56afc609e74202658d3ffba0e8f6dda462b719fa",
        "actions/deploy-pages": "d6db90164ac5ed86f2b6aed7e0febac5b3c0c03e",
    }

    uses = re.findall(r"uses: (actions/[^@\s]+)@([^\s#]+)", workflows)

    assert {action for action, _ref in uses} == expected.keys()
    for action, ref in uses:
        assert ref == expected[action]


def test_wheel_install_uses_the_recorded_runtime_constraints():
    ci = _text(".github/workflows/ci.yml")

    assert (
        '.venv/bin/pip install --constraint "$GITHUB_WORKSPACE/requirements.txt" '
        '"$GITHUB_WORKSPACE"/dist/*.whl'
    ) in ci


def test_pages_privacy_comment_credits_all_three_safeguards():
    pages = _text(".github/workflows/pages.yml")

    assert "application code has no upload path" in pages
    assert "build audits shipped text files for unexplained absolute URLs" in pages
    assert "same-origin CSP restricts programmatic connections" in pages
    assert "enforced by connect-src 'self'" not in pages


def test_release_identity_checks_leave_existing_history_unchanged():
    releasing = _text("docs/RELEASING.md")
    prerequisites = releasing.split("## Voraussetzungen", 1)[1].split("## Reihenfolge", 1)[0]
    sequence = releasing.split("## Reihenfolge", 1)[1].split("## GitHub-Einstellungen", 1)[0]

    assert "GitHub ordnet den Release-Commit dem vorgesehenen Konto zu" in prerequisites
    assert "Bestehende historische Commits bleiben unverändert" in prerequisites
    assert "GitHub erkennt die Signatur des Release-Tags an" in sequence
    assert "GitHub ordnet die Commits der vorgesehenen Identität zu" not in releasing


def test_python_build_tools_are_pinned():
    project = tomllib.loads(_text("pyproject.toml"))
    ci = _text(".github/workflows/ci.yml")

    assert project["build-system"]["requires"] == ["setuptools==84.0.0"]
    assert "pip install build==1.6.1" in ci


def test_internal_status_no_longer_calls_pages_unpublished():
    vision = _text("docs/VISION.md")
    issues = _text("docs/ISSUES.md")

    assert "GitHub Pages einschalten" not in vision
    assert "GitHub Pages einschalten" not in issues
    assert "Rest bis Veröffentlichung" not in vision
    assert "später auf HTTPS" not in vision
    assert "morgen statisch im Browser" not in vision
    assert "Einträge, fertig zum Anlegen als GitHub-Issues, sobald" not in issues
    assert "Muss vor der ersten Veröffentlichung fertig sein" not in issues
    assert "## 1. Dokumentation und Code ins Englische übersetzen — ERLEDIGT" in issues
    assert "https://shadesmaverick.github.io/qrsalvage/" in vision


def test_github_templates_warn_against_publishing_secrets():
    bug = _text(".github/ISSUE_TEMPLATE/bug_report.yml")
    feature = _text(".github/ISSUE_TEMPLATE/feature_request.yml")
    pull_request = _text(".github/pull_request_template.md")

    for template in (bug, feature, pull_request):
        assert "real photographs" in template.lower()
        assert "recovered payload" in template.lower()
    assert "before" in pull_request.lower() and "after" in pull_request.lower()
