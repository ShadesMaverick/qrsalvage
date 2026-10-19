"""Contracts for files that publish the project rather than run it."""

from __future__ import annotations

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
