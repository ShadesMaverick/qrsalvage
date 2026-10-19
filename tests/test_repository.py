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
