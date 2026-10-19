"""Contracts for files that publish the project rather than run it."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


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
