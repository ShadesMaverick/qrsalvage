"""Assemble the published site: one directory that answers every request from itself.

The question this instrument answers: *what has to sit next to the page so that a visitor's
browser can run the recovery with no server and no second host?* The page itself has no build
step and never will -- markup, style and script are shipped as they are written. What cannot be
shipped as written is the runtime: CPython on WebAssembly, NumPy, OpenCV and the zxing oracle
are some fifteen megabytes of binaries that have no business in a git history. So they are
fetched at build time, pinned to exact versions, cached, and laid out where worker.js expects
them. That is all this script is: a vendoring step, not a bundler.

Build time is the only time anything is downloaded. The shipped result must reach no remote
host at runtime, and that is not a preference -- the whole claim of this project is that the
photograph never leaves the machine. A page that pulls a WASM blob off a CDN has already told
that CDN who is recovering a code, and a CDN that goes away takes the tool with it. So the
script ends by auditing what it just wrote for absolute URLs and printing what it found.

Two of those URLs had to be removed by hand, and both are worth knowing about:

  - zxing-wasm's default `locateFile` points at fastly.jsdelivr.net. It is a sensible default
    for a CDN-first library and exactly wrong here, so the vendored copy is patched to resolve
    its .wasm next to itself.
  - Pyodide's loader would default to a CDN indexURL, but worker.js passes an explicit local
    one, so nothing needs patching there -- only the packages it will ask for have to be
    present locally, resolved from pyodide-lock.json rather than guessed.

Usage:
    python scripts/build_site.py [--refresh]

    --refresh  ignore the download cache and fetch the pinned files again
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "src" / "qrsalvage" / "web"
SITE = ROOT / "site"
CACHE = ROOT / "vendor-cache"

# Exact versions, never ranges. A static site is a frozen artefact: the visitor gets whatever
# was vendored the day it was built, so the build has to be able to produce that same artefact
# again. 0.28.0 is the version the spike in spike/pyodide measured, and it carries NumPy 2.2
# and OpenCV 4.11 as prebuilt wasm wheels. zxing-wasm 2.2.4 is the newest 2.x -- the same major
# the spike probed, and the one whose synchronous embind surface worker.js arms.
PYODIDE_VERSION = "0.28.0"
ZXING_VERSION = "2.2.4"

# The core tarball is the runtime without the package library: five megabytes instead of three
# hundred and thirty. The full release tarball carries every wheel Pyodide ever built, and this
# site needs two of them. So the runtime comes from the release, and the two wheels (plus
# whatever pyodide-lock.json says they depend on) come one by one from the distribution CDN --
# both at build time, both pinned, both cached.
PYODIDE_CORE_URL = (
    f"https://github.com/pyodide/pyodide/releases/download/{PYODIDE_VERSION}"
    f"/pyodide-core-{PYODIDE_VERSION}.tar.bz2"
)
PYODIDE_FILE_URL = f"https://cdn.jsdelivr.net/pyodide/v{PYODIDE_VERSION}/full/"
ZXING_URL = f"https://registry.npmjs.org/zxing-wasm/-/zxing-wasm-{ZXING_VERSION}.tgz"

# What loadPyodide actually reads from indexURL. The type stubs, the UMD build and the npm
# package manifest ride along in the tarball and are of no use to a browser.
PYODIDE_RUNTIME = (
    "pyodide.mjs",
    "pyodide.asm.js",
    "pyodide.asm.wasm",
    "python_stdlib.zip",
    "pyodide-lock.json",
)

# Exactly what worker.js hands to pyodide.loadPackage. Their dependencies are read from the
# lock file, not listed here -- a guess would be wrong the day a package gains one.
PYODIDE_PACKAGES = ("numpy", "opencv-python")

# The page, file by file. Named rather than globbed for the same reason server.py names them:
# a build that silently ships whatever happens to lie in the source directory is a build that
# one day ships a scratch file.
PAGE_FILES = (
    "index.html",
    "method.html",
    "legal.html",
    "app.js",
    "worker.js",
    "style.css",
    "axolotl.png",
    "fig-known.svg",
    "fig-levels.svg",
    "fig-objective.svg",
    "fig-posterior.svg",
    "fig-probe.svg",
    "fig-rs.svg",
)

# Namespaces, not addresses. An SVG names its dialect with a URL and no browser ever fetches
# it; counting those as network access would drown the audit that matters.
AUDIT_IGNORED = re.compile(r"^https?://(www\.)?w3\.org/")
AUDIT_URL = re.compile(rb"""https?://[^\s"'`<>)\\]+""")
AUDIT_SUFFIXES = {".js", ".mjs", ".html", ".json", ".css", ".svg"}

# The URLs that survive the audit for a reason, each with the reason. Anything the audit finds
# that is not on this list is unexplained and has to be looked at before publishing -- that is
# the whole value of keeping the list short and written down.
AUDIT_EXPLAINED: tuple[tuple[str, str], ...] = (
    (
        "cdn.jsdelivr.net/pyodide",
        "Pyodide's fallback index, reached only if loadPyodide runs without an indexURL; "
        "worker.js always passes the local one",
    ),
    (
        "paypal.me|ko-fi.com|liberapay.com",
        "a donation link a visitor may click, never fetched by the page",
    ),
)


def _download(url: str, cached: Path, refresh: bool) -> bytes:
    """Fetch a pinned file, once. Re-runs of the build must work offline."""
    if cached.exists() and not refresh:
        return cached.read_bytes()
    print(f"  downloading {url}")
    request = urllib.request.Request(url, headers={"User-Agent": "qrsalvage-build"})
    with urllib.request.urlopen(request, timeout=300) as response:
        body: bytes = response.read()
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_bytes(body)
    return body


def build_wheel(target: Path) -> str:
    """Build the project wheel and put it where worker.js fetches it.

    Pure Python by construction: the wheel carries no compiled extension, because the two
    native dependencies of the command line -- OpenCV and zxing-cpp -- are supplied by Pyodide
    and by the oracle seam respectively. That is what lets a browser install it by unpacking a
    zip.
    """
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            [sys.executable, "-m", "pip", "wheel", ".", "--no-deps", "-w", tmp],
            cwd=ROOT,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        wheels = sorted(Path(tmp).glob("qrsalvage-*.whl"))
        if len(wheels) != 1:
            raise SystemExit(f"expected exactly one qrsalvage wheel, got {wheels}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(wheels[0], target)
        return wheels[0].name


def _resolve_packages(lock: dict, wanted: tuple[str, ...]) -> list[dict]:
    """Close the wanted packages over their dependencies, as the lock file records them.

    loadPackage resolves dependencies itself at runtime and will fetch them from indexURL --
    which is local here, so a dependency left unvendored is not a remote request but a 404 in
    the middle of the boot. Reading the same graph the loader reads is the only way to be sure
    the set is complete.
    """
    packages = lock["packages"]
    seen: set[str] = set()
    queue = deque(wanted)
    while queue:
        name = queue.popleft()
        if name in seen:
            continue
        if name not in packages:
            raise SystemExit(f"{name} is not in pyodide-lock.json for {PYODIDE_VERSION}")
        seen.add(name)
        queue.extend(packages[name]["depends"])
    return [packages[name] for name in sorted(seen)]


def vendor_pyodide(target: Path, refresh: bool) -> list[str]:
    """Lay out the Python runtime and the two package wheels under vendor/pyodide/."""
    target.mkdir(parents=True, exist_ok=True)
    archive = _download(
        PYODIDE_CORE_URL, CACHE / f"pyodide-core-{PYODIDE_VERSION}.tar.bz2", refresh
    )
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:bz2") as tar:
        members = {Path(member.name).name: member for member in tar.getmembers()}
        for name in PYODIDE_RUNTIME:
            member = members.get(name)
            if member is None:
                raise SystemExit(f"{name} is missing from the pyodide core tarball")
            source = tar.extractfile(member)
            if source is None:
                raise SystemExit(f"{name} is not a regular file in the pyodide core tarball")
            (target / name).write_bytes(source.read())

    lock = json.loads((target / "pyodide-lock.json").read_text(encoding="utf-8"))
    shipped = []
    for package in _resolve_packages(lock, PYODIDE_PACKAGES):
        file_name = package["file_name"]
        wheel = _download(
            PYODIDE_FILE_URL + file_name, CACHE / f"pyodide-{PYODIDE_VERSION}" / file_name, refresh
        )
        digest = hashlib.sha256(wheel).hexdigest()
        if digest != package["sha256"]:
            # The lock file states the hash, so the download can be checked instead of trusted.
            raise SystemExit(f"{file_name} does not match the hash in pyodide-lock.json")
        (target / file_name).write_bytes(wheel)
        shipped.append(f"{package['name']} {package['version']}")
    return shipped


def vendor_zxing(target: Path, refresh: bool) -> None:
    """Lay out the oracle as a plain ES module whose .wasm sits beside it.

    The npm tarball rather than a CDN bundle: a bundle is rewritten by whoever built it, and
    what it rewrites URLs to is precisely the thing that must not be left to chance here. The
    published package ships three flavours; only the ES build of the `full` entry point is
    needed, and it imports one shared module and one .wasm.
    """
    target.mkdir(parents=True, exist_ok=True)
    archive = _download(ZXING_URL, CACHE / f"zxing-wasm-{ZXING_VERSION}.tgz", refresh)
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:

        def read(name: str) -> bytes:
            source = tar.extractfile(f"package/{name}")
            if source is None:
                raise SystemExit(f"{name} is missing from the zxing-wasm package")
            return source.read()

        index = read("dist/es/full/index.js").decode("utf-8")
        share = read("dist/es/share.js").decode("utf-8")
        (target / "zxing_full.wasm").write_bytes(read("dist/full/zxing_full.wasm"))

    # Flattened from dist/es/full/ into one directory, so the import has to be flattened too.
    index, moved = re.subn(r'"\.\./share\.js"', '"./share.js"', index)
    if not moved:
        raise SystemExit("zxing-wasm's index no longer imports ../share.js -- check the pin")

    # The one remote URL in the whole site, removed at its source. The default asks a CDN for
    # the .wasm; the vendored copy resolves it next to this module instead. import.meta.url is
    # available because this file is only ever loaded as an ES module.
    share, patched = re.subn(
        r"`https?://[^`]*zxing-wasm[^`]*`", "new URL(e, import.meta.url).href", share
    )
    if patched != 1:
        raise SystemExit(f"expected one CDN URL in zxing-wasm's share.js, found {patched}")

    (target / "index.mjs").write_text(index, encoding="utf-8", newline="")
    (target / "share.js").write_text(share, encoding="utf-8", newline="")


def copy_page(target: Path) -> None:
    """Copy the page as it is written, and pick the backend that has no server behind it.

    backend.js is the single seam between the two deployments: the local server writes
    backend-server.js there and talks HTTP to itself, the static build writes backend-worker.js
    there and talks to a worker. The page loads one name and never learns which it got.
    """
    target.mkdir(parents=True, exist_ok=True)
    for name in PAGE_FILES:
        source = WEB / name
        if not source.is_file():
            raise SystemExit(f"{source} is missing")
        shutil.copyfile(source, target / name)
    shutil.copyfile(WEB / "backend-worker.js", target / "backend.js")

    # Everything the page references is relative, so the site works from a domain root, from a
    # project subpath and straight off a filesystem alike. That rules out the obvious trick of
    # serving the method page from a directory of its own for a prettier URL: inside
    # /method/ the relative figure and stylesheet references would climb one level too few.
    # A second URL for one page would have been a duplicate to explain to search engines
    # anyway, so method.html is simply the address.


def write_domains(target: Path) -> None:
    """Write the Codeberg Pages domain file, with a placeholder that has to be replaced."""
    (target / ".domains").write_text(
        "qrsalvage.example.org\n"
        "# Codeberg Pages reads this file: one domain per line, the first one canonical.\n"
        "# Replace the placeholder above with the domain you own before publishing, and add\n"
        "# <user>.codeberg.page on a line of its own if the default address should keep\n"
        "# working. A domain listed here without the matching DNS record does nothing.\n",
        encoding="utf-8",
        newline="\n",
    )


def update_gitignore() -> None:
    """Keep the built site and the download cache out of the history."""
    path = ROOT / ".gitignore"
    text = path.read_text(encoding="utf-8")
    entries = {line.strip() for line in text.splitlines()}
    missing = [entry for entry in ("site/", "vendor-cache/") if entry not in entries]
    if not missing:
        return
    block = (
        "\n# The built site and the download cache of its runtime: both reproducible from\n"
        "# scripts/build_site.py, both far too large for the history.\n"
        + "".join(f"{entry}\n" for entry in missing)
    )
    path.write_text(text.rstrip("\n") + "\n" + block, encoding="utf-8", newline="")
    print(f"  .gitignore: added {', '.join(missing)}")


def audit(target: Path) -> list[tuple[Path, str]]:
    """Find every absolute URL left in the shipped text assets.

    This is the check the whole exercise stands on, so it is part of the build rather than a
    thing to remember to do. It cannot tell a link a visitor may click from an address the page
    fetches on its own -- that judgement stays with a reader -- but it can guarantee that no
    such address goes unnoticed.
    """
    findings: list[tuple[Path, str]] = []
    for path in sorted(target.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in AUDIT_SUFFIXES:
            continue
        for match in AUDIT_URL.findall(path.read_bytes()):
            url = match.decode("utf-8", "replace").rstrip(".,;")
            if not AUDIT_IGNORED.match(url):
                findings.append((path.relative_to(target), url))
    return findings


def _tree_size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _mb(size: int) -> str:
    return f"{size / 1_000_000:8.2f} MB"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the self-contained static site.")
    parser.add_argument(
        "--refresh", action="store_true", help="re-download the pinned runtime files"
    )
    args = parser.parse_args()

    if SITE.exists():
        shutil.rmtree(SITE)
    print(f"building {SITE}")

    print("wheel")
    wheel_name = build_wheel(SITE / "vendor" / "qrsalvage.whl")
    print(f"  {wheel_name}")

    print(f"pyodide {PYODIDE_VERSION}")
    packages = vendor_pyodide(SITE / "vendor" / "pyodide", args.refresh)
    print(f"  runtime plus {', '.join(packages)}")

    print(f"zxing-wasm {ZXING_VERSION}")
    vendor_zxing(SITE / "vendor" / "zxing", args.refresh)
    print("  patched to resolve its wasm locally")

    print("page")
    copy_page(SITE)
    write_domains(SITE)
    update_gitignore()

    print("\nsize")
    parts = (
        ("page", SITE, True),
        ("pyodide runtime", SITE / "vendor" / "pyodide", False),
        ("zxing-wasm", SITE / "vendor" / "zxing", False),
        ("qrsalvage wheel", SITE / "vendor" / "qrsalvage.whl", False),
    )
    vendored = _tree_size(SITE / "vendor")
    total = _tree_size(SITE)
    for label, path, is_page in parts:
        size = total - vendored if is_page else _tree_size(path)
        print(f"  {label:<20} {_mb(size)}")
    print(f"  {'total':<20} {_mb(total)}")

    print("\nself-containment")
    unexplained = 0
    for path, url in dict.fromkeys(audit(SITE)):
        note = next((why for pattern, why in AUDIT_EXPLAINED if re.search(pattern, url)), None)
        unexplained += note is None
        print(f"  {path}: {url}\n      {note or 'UNEXPLAINED -- look at this before publishing'}")
    print(
        f"  {unexplained} unexplained absolute URL(s) in the shipped scripts, pages and data"
        if unexplained
        else "  every absolute URL left in the build is accounted for above"
    )

    print("\nserve it locally to test:")
    print("  .venv\\Scripts\\python.exe -m http.server 8833 --directory site --bind 127.0.0.1")
    print("  then open http://127.0.0.1:8833/")
    print("\npublishing: push the contents of site/ to the pages branch, edit site/.domains,")
    print("and point DNS at Codeberg -- a CNAME from your domain to <user>.codeberg.page")
    print("(an apex domain needs A/AAAA records instead). Without that record the .domains")
    print("file is inert.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
