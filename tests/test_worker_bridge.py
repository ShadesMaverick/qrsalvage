"""The executable Python half of the browser worker's JSON boundary."""

from __future__ import annotations

import json
import re
import sys
import types
from pathlib import Path
from typing import Any

from qrsalvage import api
from qrsalvage.core import oracle

ROOT = Path(__file__).resolve().parents[1]


def _worker_glue() -> str:
    worker = (ROOT / "src" / "qrsalvage" / "web" / "worker.js").read_text(encoding="utf-8")
    match = re.search(r"const GLUE = `\n(.*?)\n`;", worker, flags=re.DOTALL)
    assert match is not None, "worker.js no longer exposes its Python bridge as GLUE"
    return match.group(1)


def test_direct_decode_json_becomes_plain_python_values(monkeypatch):
    """A JavaScript null must reach the API as None, never as Pyodide's JsNull proxy."""
    received = None

    def fake_solve_payload(payload, progress=None, *, trusted_direct_texts=None):
        nonlocal received
        received = trusted_direct_texts
        return {"ok": False, "failure": "test boundary"}

    monkeypatch.setattr(api, "solve_payload", fake_solve_payload)
    monkeypatch.setattr(oracle, "use", lambda *_functions: None)

    js_module = types.ModuleType("js")
    pyodide_module: Any = types.ModuleType("pyodide")
    ffi_module: Any = types.ModuleType("pyodide.ffi")
    ffi_module.to_js = lambda value: value
    pyodide_module.ffi = ffi_module
    monkeypatch.setitem(sys.modules, "js", js_module)
    monkeypatch.setitem(sys.modules, "pyodide", pyodide_module)
    monkeypatch.setitem(sys.modules, "pyodide.ffi", ffi_module)

    namespace: dict[str, Any] = {}
    exec(_worker_glue(), namespace)
    answer = namespace["handle_json"](
        "solve",
        json.dumps({"images": ["first", "second"]}),
        json.dumps([None, "decoded"]),
    )

    assert received == [None, "decoded"]
    assert json.loads(answer) == {"ok": False, "failure": "test boundary"}
