# Publication Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the public installation, deployment, privacy and repository claims match the state that GitHub actually serves.

**Architecture:** Keep CI and Pages as separate workflows, but let Pages consume only a successful `CI` workflow run and check out that run's exact SHA. Add one repository-contract test module for non-Python publication files, then harden installation metadata, browser policies, dependency pins and contributor-facing repository files in independent commits.

**Tech Stack:** GitHub Actions YAML, Python 3.11/3.12, pytest, TOML via `tomllib`, static HTML, Markdown.

**Spec:** `docs/superpowers/specs/2026-10-19-publication-hardening-design.md`

## Global Constraints

- Do not add a dependency or install anything into `.venv` or `.venv312`.
- Do not change recovery behavior or files under `src/qrsalvage/core/`.
- All code, test names, workflow comments and public program output stay in English; internal `docs/` files stay German.
- Real photographs and recovered payloads must never enter tracked files, tests, issues or templates.
- Do not push, merge, publish, tag, delete a remote branch, change GitHub settings or rewrite history.
- Use the existing interpreters from the main checkout. In the worktree, targeted tests run as:
  `$env:PYTHONPATH = (Resolve-Path 'src').Path` followed by `& '..\..\.venv\Scripts\python.exe' -m pytest ...`.
- Every production/configuration change follows an observed failing repository-contract test first.
- Each task ends in its own commit and an independent task review before the next task starts.

---

### Task 1: Gate Pages on the exact successful CI commit

**Files:**
- Create: `tests/test_repository.py`
- Modify: `.github/workflows/pages.yml`

**Interfaces:**
- Consumes: workflow name `CI` from `.github/workflows/ci.yml` and default branch `main`.
- Produces: a Pages workflow triggered only by a completed successful push-CI run on `main`, building `github.event.workflow_run.head_sha`; `tests/test_repository.py` becomes the shared contract-test location for later tasks.

- [ ] **Step 1: Write the failing workflow contract test**

Create `tests/test_repository.py` with this foundation and test:

```python
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
```

- [ ] **Step 2: Run the test and verify the expected failure**

Run:

```powershell
$env:PYTHONPATH = (Resolve-Path 'src').Path
& '..\..\.venv\Scripts\python.exe' -m pytest tests/test_repository.py::test_pages_builds_only_the_exact_successful_main_ci_commit -q
```

Expected: FAIL because `pages.yml` still contains `push`/`workflow_dispatch` and no `workflow_run` SHA binding.

- [ ] **Step 3: Replace the Pages trigger and bind checkout to the CI SHA**

In `.github/workflows/pages.yml`, replace the trigger with:

```yaml
on:
  workflow_run:
    workflows: [CI]
    types: [completed]
```

Put this exact gate on the `build` job:

```yaml
    if: >-
      github.event.workflow_run.conclusion == 'success' &&
      github.event.workflow_run.event == 'push' &&
      github.event.workflow_run.head_branch == 'main'
```

Give the checkout step this input:

```yaml
        with:
          ref: ${{ github.event.workflow_run.head_sha }}
```

Update nearby comments so they say the deployment follows a successful CI run rather than every push. Do not alter the build, vendoring, cache, artifact or deploy behavior otherwise.

- [ ] **Step 4: Run the targeted test and fast suite**

Run:

```powershell
$env:PYTHONPATH = (Resolve-Path 'src').Path
& '..\..\.venv\Scripts\python.exe' -m pytest tests/test_repository.py -q
& '..\..\.venv\Scripts\python.exe' -m pytest -m "not regression" -q
```

Expected: both commands PASS.

- [ ] **Step 5: Commit the deployment gate**

```powershell
git add -- .github/workflows/pages.yml tests/test_repository.py
git commit -m "ci: gate Pages on successful CI"
```

---

### Task 2: Make installation and release metadata truthful

**Files:**
- Modify: `tests/test_repository.py`
- Modify: `README.md`
- Modify: `pyproject.toml`
- Create: `docs/RELEASING.md`

**Interfaces:**
- Consumes: public repository URL and Pages URL already used by the README.
- Produces: a currently working GitHub installation command, standard project URLs in wheel metadata and a manual checklist for the external release actions deliberately excluded from this branch.

- [ ] **Step 1: Add failing README and metadata tests**

Append:

```python
import tomllib


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
```

- [ ] **Step 2: Verify both tests fail for the intended reasons**

Run:

```powershell
$env:PYTHONPATH = (Resolve-Path 'src').Path
& '..\..\.venv\Scripts\python.exe' -m pytest tests/test_repository.py::test_installation_uses_a_source_that_exists_today tests/test_repository.py::test_package_metadata_points_back_to_the_public_project -q
```

Expected: FAIL because the README names nonexistent PyPI distribution and `project.urls` is absent.

- [ ] **Step 3: Correct README and package URLs**

Replace the first install block with:

````markdown
Install the current version directly from GitHub:

```text
pip install git+https://github.com/ShadesMaverick/qrsalvage.git
```
````

Keep the existing clone/editable instructions, relabelled `For development from source:`.

Add after `dependencies` in `[project]`:

```toml
[project.urls]
Homepage = "https://shadesmaverick.github.io/qrsalvage/"
Repository = "https://github.com/ShadesMaverick/qrsalvage"
Issues = "https://github.com/ShadesMaverick/qrsalvage/issues"
```

- [ ] **Step 4: Add the German manual release checklist**

Create `docs/RELEASING.md` with these explicit sections and decisions:

- `# Veröffentlichung eines Releases`
- `## Voraussetzungen`: clean branch, full verification, benchmark evidence, GitHub-recognized commit identity; `[verified]` in a subject is not a signature.
- `## Reihenfolge`: choose version, update `pyproject.toml`, run verification, signed `vX.Y.Z` tag, push branch/tag, create GitHub release with wheel and sdist, publish the same artifacts to PyPI, test installation in a fresh environment, only then change README to `pip install qrsalvage`.
- `## GitHub-Einstellungen`: protect `main` with PR and required CI; prohibit force-push/deletion; delete `harden-declared-invariants` only after confirming it contains no unique commits.
- `## Abbruch`: if any artifact digest, clean install, signature or CI check differs/fails, do not publish the next channel and do not advertise PyPI.

Do not include credentials, account addresses, tokens or recovered payload examples.

- [ ] **Step 5: Run repository tests and metadata build check**

Run:

```powershell
$env:PYTHONPATH = (Resolve-Path 'src').Path
& '..\..\.venv\Scripts\python.exe' -m pytest tests/test_repository.py -q
& '..\..\.venv\Scripts\python.exe' -c "import tomllib, pathlib; tomllib.loads(pathlib.Path('pyproject.toml').read_text(encoding='utf-8'))"
```

Expected: PASS.

- [ ] **Step 6: Commit installation truth**

```powershell
git add -- README.md pyproject.toml docs/RELEASING.md tests/test_repository.py
git commit -m "docs: make installation and release claims truthful"
```

---

### Task 3: Correct the static-site privacy boundary

**Files:**
- Modify: `tests/test_repository.py`
- Modify: `src/qrsalvage/web/index.html`
- Modify: `src/qrsalvage/web/legal.html`
- Modify: `scripts/build_site.py`

**Interfaces:**
- Consumes: the existing response-header CSP in `qrsalvage.server`, which still legitimately carries `frame-ancestors 'none'` and must not change.
- Produces: meta policies containing only directives browsers honor there, plus explanations that credit the code path, audit and CSP together.

- [ ] **Step 1: Add failing static-policy tests**

Append:

```python
import re


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
```

- [ ] **Step 2: Verify the tests fail on index/legal and the old legal claim**

Run the two tests directly. Expected: FAIL for `frame-ancestors` in `index.html`/`legal.html` and the missing replacement explanation.

- [ ] **Step 3: Remove ineffective meta directives and narrow the claims**

In `index.html`:

- remove `frame-ancestors 'none'` from the meta CSP;
- rewrite the preceding English comment to say `connect-src 'self'` restricts programmatic connections and works together with the audited code/build; do not say CSP alone enforces that the photograph cannot leave.

In `legal.html`:

- remove `frame-ancestors 'none'` from the meta CSP;
- replace the paragraph ending in „Upload gar nicht erst zuließe“ with text containing these exact two sentences:
  `Der Anwendungscode enthält keinen Uploadpfad für Fotos oder wiederhergestellte Inhalte.`
  `Der Build prüft die ausgelieferten Textdateien auf unerklärte externe Adressen.`
- follow them by explaining that the same-origin CSP additionally restricts programmatic connections, while GitHub receives ordinary page requests as already documented below.

In `scripts/build_site.py`, change only publication comments/printed guidance that still says every push deploys. State that a successful main CI run triggers Pages. Preserve URL audit behavior.

- [ ] **Step 4: Run policy, server and build-audit tests**

Run:

```powershell
$env:PYTHONPATH = (Resolve-Path 'src').Path
& '..\..\.venv\Scripts\python.exe' -m pytest tests/test_repository.py tests/test_server.py -q
& '..\..\.venv\Scripts\python.exe' -m pytest tests/test_contracts.py -q
```

Expected: PASS. In particular, the local server header test must still assert `frame-ancestors 'none'`.

- [ ] **Step 5: Commit the privacy-boundary correction**

```powershell
git add -- src/qrsalvage/web/index.html src/qrsalvage/web/legal.html scripts/build_site.py tests/test_repository.py
git commit -m "docs: state the browser privacy boundary precisely"
```

---

### Task 4: Pin the declared CI toolchain and GitHub Actions

**Files:**
- Modify: `tests/test_repository.py`
- Modify: `requirements.txt`
- Modify: `pyproject.toml`
- Modify: `.github/workflows/ci.yml`
- Modify: `.github/workflows/pages.yml`

**Interfaces:**
- Consumes: versions observed in the existing `.venv`/`.venv312` and current GitHub major-tag targets on 2026-10-19.
- Produces: deterministic direct requirements for Python 3.11 versus 3.12+, a pinned build frontend/backend and immutable Action references.

- [ ] **Step 1: Add failing dependency and Action-reference tests**

Append:

```python
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

    assert not re.search(r"uses: actions/[^@\s]+@v\d", workflows)
    for action, sha in expected.items():
        assert f"uses: {action}@{sha}" in workflows


def test_python_build_tools_are_pinned():
    project = tomllib.loads(_text("pyproject.toml"))
    ci = _text(".github/workflows/ci.yml")

    assert project["build-system"]["requires"] == ["setuptools==84.0.0"]
    assert "pip install build==1.6.1" in ci
```

- [ ] **Step 2: Run the three tests and observe range/tag failures**

Expected: FAIL on every contract because requirements use `>=`, Actions use major tags and build tools are not pinned.

- [ ] **Step 3: Pin requirements and build tools**

Replace the non-comment requirement lines with the exact eight entries asserted above. Keep short German comments explaining the Python 3.11/NumPy split and that `pyproject.toml` retains compatibility floors while this file records the tested development/CI environment.

Change the build backend requirement to `setuptools==84.0.0`. Change the CI wheel step to `pip install build==1.6.1`.

Update the mypy comment from NumPy 2.5.2 to NumPy 2.5.4 and retain the measured Python-grammar rationale.

- [ ] **Step 4: Replace every Action major tag with its immutable SHA**

Use the five exact mappings from the test. Add an inline comment after each reference, for example:

```yaml
      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4
```

Update the lint comment: requirements now record the tested toolchain; package compatibility floors remain in `pyproject.toml`.

- [ ] **Step 5: Run repository tests, fast tests, Ruff and Python-3.12 mypy**

Run:

```powershell
$env:PYTHONPATH = (Resolve-Path 'src').Path
& '..\..\.venv\Scripts\python.exe' -m pytest tests/test_repository.py -q
& '..\..\.venv\Scripts\python.exe' -m pytest -m "not regression" -q
& '..\..\.venv\Scripts\python.exe' -m ruff check .
& '..\..\.venv\Scripts\python.exe' -m ruff format --check .
& '..\..\.venv312\Scripts\python.exe' -m mypy
```

Expected: all commands PASS without installing the newly pinned files.

- [ ] **Step 6: Commit supply-chain pins**

```powershell
git add -- requirements.txt pyproject.toml .github/workflows/ci.yml .github/workflows/pages.yml tests/test_repository.py
git commit -m "ci: pin the tested publication toolchain"
```

---

### Task 5: Reconcile the public roadmap and contribution entry points

**Files:**
- Modify: `tests/test_repository.py`
- Modify: `docs/VISION.md`
- Modify: `docs/ISSUES.md`
- Create: `.github/ISSUE_TEMPLATE/bug_report.yml`
- Create: `.github/ISSUE_TEMPLATE/feature_request.yml`
- Create: `.github/ISSUE_TEMPLATE/config.yml`
- Create: `.github/pull_request_template.md`

**Interfaces:**
- Consumes: privacy/release wording established in Tasks 2–3 and measurement rules from `CONTRIBUTING.md`.
- Produces: current internal status documents and GitHub forms that prevent sensitive uploads and request reproducible evidence.

- [ ] **Step 1: Add failing status and template contracts**

Append:

```python
def test_internal_status_no_longer_calls_pages_unpublished():
    vision = _text("docs/VISION.md")
    issues = _text("docs/ISSUES.md")

    assert "GitHub Pages einschalten" not in vision
    assert "GitHub Pages einschalten" not in issues
    assert "Rest bis Veröffentlichung" not in vision
    assert "Einträge, fertig zum Anlegen als GitHub-Issues, sobald" not in issues
    assert "https://shadesmaverick.github.io/qrsalvage/" in vision


def test_github_templates_warn_against_publishing_secrets():
    bug = _text(".github/ISSUE_TEMPLATE/bug_report.yml")
    feature = _text(".github/ISSUE_TEMPLATE/feature_request.yml")
    pull_request = _text(".github/pull_request_template.md")

    for template in (bug, feature, pull_request):
        assert "real photographs" in template.lower()
        assert "recovered payload" in template.lower()
    assert "before" in pull_request.lower() and "after" in pull_request.lower()
```

- [ ] **Step 2: Verify missing/stale-file failures**

Run both tests. Expected: FAIL because the old publication phrases remain and the GitHub templates do not exist.

- [ ] **Step 3: Update VISION and ISSUES without erasing historical findings**

In `docs/VISION.md`:

- change the target to a static GitHub Pages browser version at the current standard URL; describe a custom domain as optional later work;
- replace claims that CSP alone enforces privacy with the three-part code/audit/CSP explanation from the spec;
- in roadmap step 4, say Pages is live at `https://shadesmaverick.github.io/qrsalvage/`, vendored assets and encode bridge are complete, and only real Safari/iOS testing remains;
- keep step 5 completed and the outreach step open.

In `docs/ISSUES.md`:

- rename the document to `# Technische Befunde und Aufgaben`;
- replace the opening publication/issue-migration instructions with a short description of the file as a durable technical ledger;
- change the browser-version entries at lines around the existing Pages/Vendoring notes to record Pages, self-hosting and encode bridge as completed;
- preserve measured negative findings and open Safari/iOS, structured abrasion and tiny-code limits.

- [ ] **Step 4: Add minimal safe GitHub forms**

Create a bug form with:

- name/description/title/`bug` label;
- a top Markdown warning: do not attach real photographs or recovered payloads; use a synthetic reproduction;
- required textareas for observed behavior, expected behavior, reproduction command and diagnostics;
- required environment inputs for OS, Python and qrsalvage commit/version;
- a checkbox confirming no real photo or recovered payload is included.

Create a feature form with the same warning, required problem/use-case and proposed measurable outcome, plus the same confirmation checkbox.

Create `config.yml` with `blank_issues_enabled: false` and no external contact links.

Create a PR template containing:

- summary and rationale;
- tests run;
- before/after measurements for recovery-path changes;
- checkboxes for English code, three-state preservation, no runtime network access, and no real photographs/recovered payloads.

All template prose is English and links to `../../CONTRIBUTING.md` or the repository-relative `CONTRIBUTING.md` as appropriate.

- [ ] **Step 5: Run repository tests and documentation checks**

Run:

```powershell
$env:PYTHONPATH = (Resolve-Path 'src').Path
& '..\..\.venv\Scripts\python.exe' -m pytest tests/test_repository.py -q
& '..\..\.venv\Scripts\python.exe' -m ruff check tests/test_repository.py
& '..\..\.venv\Scripts\python.exe' -m ruff format --check tests/test_repository.py
git diff --check
```

Expected: PASS.

- [ ] **Step 6: Commit repository hygiene**

```powershell
git add -- docs/VISION.md docs/ISSUES.md .github/ISSUE_TEMPLATE .github/pull_request_template.md tests/test_repository.py
git commit -m "docs: reconcile the public project state"
```

---

## Final integrated verification

After all five reviewed commits, the controller runs fresh commands from the worktree:

```powershell
$env:PYTHONPATH = (Resolve-Path 'src').Path
& '..\..\.venv\Scripts\python.exe' -m pytest
& '..\..\.venv\Scripts\python.exe' -m ruff check .
& '..\..\.venv\Scripts\python.exe' -m ruff format --check .
& '..\..\.venv312\Scripts\python.exe' -m mypy
git diff --check (git merge-base origin/main HEAD) HEAD
```

The final reviewer receives the complete diff from the branch base through `HEAD`, the spec, this plan and all deferred findings. External GitHub/PyPI steps remain unexecuted and are reported to the user from `docs/RELEASING.md`.
