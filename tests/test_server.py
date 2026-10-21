"""The local web interface: its JSON contract and its refusal to listen to the outside world.

The page is a single static file with no build step, so the only thing that can silently break
between it and the core is the shape of the JSON. That is what these tests pin down.
"""

from __future__ import annotations

import base64
import html
import http.client
import json
import re
import shutil
import subprocess
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import cv2
import numpy as np
import pytest

from qrsalvage.core import pipeline
from qrsalvage.core.decoding import reencode, render
from qrsalvage.server import Handler, catalog_payload, export_payload, solve_payload
from qrsalvage.synth import Damage, render_photo

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "engraved-curved-hard.png"
ROOT = Path(__file__).resolve().parents[1]


def _call_web_module(file_name: str, function: str, *args):
    helper = ROOT / "src" / "qrsalvage" / "web" / file_name
    script = """
const helper = require(process.argv[1]);
const args = JSON.parse(process.argv[3]);
process.stdout.write(JSON.stringify(helper[process.argv[2]](...args)));
"""
    completed = subprocess.run(
        ["node", "-e", script, str(helper), function, json.dumps(args)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def _call_backend_server_probe(probe: str):
    helper = ROOT / "src" / "qrsalvage" / "web" / "backend-server.js"
    script = r"""
const probe = process.argv[2];
const encoder = new TextEncoder();
const chunks = [];
let status = 200;
let ok = true;
let bodyText = "";
if (probe === "terminal") {
  chunks.push(
    encoder.encode('{"type":"grid","modules":21}\n'),
    encoder.encode('{"type":"result","ok":true,"text":"PUBLIC"}')
  );
} else if (probe === "413") {
  status = 413; ok = false; bodyText = '{"failure":"photograph too large"}';
} else if (probe === "503") {
  status = 503; ok = false;
} else {
  throw new Error(`unknown probe: ${probe}`);
}
let index = 0;
const response = {
  ok,
  status,
  body: ok ? { getReader() { return { async read() {
    if (index >= chunks.length) return { done: true, value: undefined };
    return { done: false, value: chunks[index++] };
  } }; } } : null,
  async text() { return bodyText; },
};
global.window = {};
global.fetch = async () => response;
require(process.argv[1]);
const events = [];
window.qrBackend.solve({ images: ["public"] }, (event) => events.push(event))
  .then((answer) => process.stdout.write(JSON.stringify({ resolved: true, answer, events })))
  .catch((error) => process.stdout.write(JSON.stringify({
    resolved: false, name: error.name, message: error.message, events,
  })));
"""
    completed = subprocess.run(
        ["node", "-e", script, str(helper), probe],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def _call_backend_contract_probe():
    web = ROOT / "src" / "qrsalvage" / "web"
    script = r"""
global.window = {};
global.fetch = async () => { throw new Error("not called"); };
require(process.argv[1]);
const server = window.qrBackend;
delete require.cache[require.resolve(process.argv[2])];
global.window = {};
global.document = { baseURI: "https://example.invalid/" };
global.Worker = class Worker {};
require(process.argv[2]);
const worker = window.qrBackend;
process.stdout.write(JSON.stringify({
  server: {
    failurePrefixKey: server.failurePrefixKey,
    rawFailurePrefix: server.failurePrefix,
  },
  worker: {
    failurePrefixKey: worker.failurePrefixKey,
    rawFailurePrefix: worker.failurePrefix,
  },
}));
"""
    completed = subprocess.run(
        [
            "node",
            "-e",
            script,
            str(web / "backend-server.js"),
            str(web / "backend-worker.js"),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def _call_app_runtime_probe(probe: str):
    web = ROOT / "src" / "qrsalvage" / "web"
    script = r"""
const fs = require("fs");
const vm = require("vm");
const probeName = process.argv[5];
const elements = new Map();
const documentListeners = new Map();
let activeLocale = "en";
let backendSolveCalls = 0;
let backendAnswer = { ok: false };

function classList() {
  const names = new Set();
  return {
    add(...values) { values.forEach((value) => names.add(value)); },
    remove(...values) { values.forEach((value) => names.delete(value)); },
    contains(value) { return names.has(value); },
    toggle(value, force) {
      const enabled = force === undefined ? !names.has(value) : Boolean(force);
      if (enabled) names.add(value); else names.delete(value);
      return enabled;
    },
    toString() { return [...names].join(" "); },
  };
}

const context2d = {
  beginPath() {}, arc() {}, stroke() {}, moveTo() {}, lineTo() {}, closePath() {}, fill() {},
  drawImage() {}, strokeText() {}, fillText() {}, quadraticCurveTo() {}, putImageData() {},
  createImageData(width, height) {
    return { data: new Uint8ClampedArray(width * height * 4) };
  },
};

function element(id = "") {
  const listeners = new Map();
  const attributes = new Map();
  const node = {
    id,
    hidden: false,
    disabled: false,
    open: false,
    width: 0,
    height: 0,
    value: "",
    checked: false,
    textContent: "",
    innerHTML: "",
    dataset: {},
    style: {},
    classList: classList(),
    addEventListener(name, callback) { listeners.set(name, callback); },
    emit(name, event = {}) {
      const callback = listeners.get(name);
      if (callback) callback({ preventDefault() {}, stopPropagation() {}, ...event });
    },
    setAttribute(name, value) { attributes.set(name, String(value)); },
    removeAttribute(name) { attributes.delete(name); },
    getAttribute(name) { return attributes.get(name) ?? null; },
    querySelector() { return element(`${id}-child`); },
    querySelectorAll() { return []; },
    getContext() { return context2d; },
    getBoundingClientRect() {
      return {
        left: 0,
        top: 0,
        width: Number.parseFloat(this.style.width) || this.width || 100,
        height: Number.parseFloat(this.style.height) || this.height || 100,
      };
    },
    hasPointerCapture() { return false; },
    setPointerCapture() {},
    releasePointerCapture() {},
    appendChild() {},
    replaceChildren() { this.innerHTML = ""; },
    focus() {},
    click() { this.emit("click"); },
  };
  return node;
}

function getElement(id) {
  if (!elements.has(id)) elements.set(id, element(id));
  return elements.get(id);
}

const document = {
  body: getElement("body"),
  documentElement: getElement("html"),
  getElementById: getElement,
  querySelectorAll() { return []; },
  querySelector() { return null; },
  createElement(tag) { return element(tag); },
  addEventListener(name, callback) { documentListeners.set(name, callback); },
};
const locale = require(process.argv[2]);
const media = { matches: false, addEventListener() {} };
const browserWindow = {
  document,
  qrLocale: { t(key, values) { return locale.translate(activeLocale, key, values); } },
  qrStudioState: require(process.argv[3]),
  qrOutlineEditor: require(process.argv[4]),
  __setBackendAnswer(answer) { backendAnswer = answer; },
  qrCompanion: { createCompanionController() { return {
    update() { return { motion: "walk" }; },
    refreshLocale() {},
  }; } },
  qrBackend: {
    modeKey: "backend.mode.server",
    privacyKey: "privacy.server",
    failurePrefixKey: "backend.failure.server",
    ready: Promise.resolve(),
    onBoot() {},
    solve() { backendSolveCalls += 1; return Promise.resolve(backendAnswer); },
    file() { throw new Error("not called"); },
  },
  localStorage: { getItem() { return null; }, setItem() {} },
  sessionStorage: { getItem() { return null; }, setItem() {} },
  matchMedia() { return media; },
};
document.defaultView = browserWindow;
const sandbox = {
  window: browserWindow,
  document,
  navigator: { mediaDevices: null, clipboard: { writeText: async () => {} } },
  console,
  URL: { createObjectURL() { return "blob:test"; }, revokeObjectURL() {} },
  Blob,
  atob,
  Uint8Array,
  Uint8ClampedArray,
  Symbol,
  Map,
  Set,
  Promise,
  Math,
  Number,
  String,
  Object,
  Array,
  JSON,
  Date,
  parseInt,
  parseFloat,
  isFinite,
  setTimeout() { return 1; },
  clearTimeout() {},
  setInterval() { return 1; },
  clearInterval() {},
  requestAnimationFrame(callback) { callback(); return 1; },
};
sandbox.globalThis = sandbox;
const appSource = fs.readFileSync(process.argv[1], "utf8");
let exposure;
if (probeName === "failure-locale") {
  exposure = `globalThis.__app = {
    showBackendFailure,
    setFailurePhase() { studioState = { ...studioState, phase: "failure" }; },
    load(entry) { loaded = [entry]; },
    progressComplete,
  };`;
} else if (probeName === "assistance-locale") {
  exposure = `globalThis.__app = {
    renderAnswer,
    syncAssistanceControls,
    load(entry) { loaded = [entry]; },
    setFinders(points) { picking = true; picked = points; outlineEditing = false; },
    setOutline(corners, midpoints) {
      picking = false; picked = []; outlineEditing = true;
      outlineCorners = corners; outlineMidpoints = midpoints;
    },
    geometry() { return { picked, corners: outlineCorners, midpoints: outlineMidpoints }; },
  };`;
} else if (probeName === "narrow-failure") {
  exposure = `globalThis.__app = {
    requireSolveAnswer,
    renderAnswer,
    load(entry) { loaded = [entry]; },
  };`;
} else if (probeName === "dynamic-targets") {
  exposure = `globalThis.__app = {
    liveEvent,
    load(entry) { loaded = [entry]; },
  };`;
} else if (probeName === "malformed-success") {
  exposure = `globalThis.__app = {
    solve,
    catalogRun,
    requireSolveAnswer,
    load(entry) { loaded = [entry]; },
    setBackendAnswer(answer) { window.__setBackendAnswer(answer); },
    phase() { return studioState.phase; },
  };`;
} else {
  throw new Error(`unknown probe: ${probeName}`);
}
vm.runInNewContext(`${appSource}\n${exposure}`, sandbox, { filename: process.argv[1] });
const app = sandbox.__app;
const emitLocaleChange = () => documentListeners.get("qrsalvage:localechange")();
const snapshotControls = () => ({
  retry: getElement("retry").hidden,
  outlineRetry: getElement("outlineRetry").hidden,
  outlineSolve: getElement("outlineSolve").hidden,
  cancel: getElement("cancel").hidden,
});
const bitmap = { width: 16, height: 8, close() {} };
const entry = { bitmap, dataUrl: "data:image/png;base64,AA==", name: "small.png" };
const failure = {
  ok: false,
  failure: "not recovered",
  finders: [],
  width: 16,
  height: 8,
  modules: null,
  grid: "",
  exportable: false,
};

if (probeName === "failure-locale") {
  const localizedFailures = {};
  for (const announcementKey of ["boot.failure", "result.failure", "catalogue.recoveryFailure"]) {
    activeLocale = "en";
    app.showBackendFailure(new Error("503"), announcementKey);
    app.setFailurePhase();
    const english = getElement("status").textContent;
    activeLocale = "de";
    emitLocaleChange();
    localizedFailures[announcementKey] = {
      english,
      german: getElement("status").textContent,
      announcement: getElement("statusLive").textContent,
    };
  }
  activeLocale = "en";
  app.load(entry);
  app.showBackendFailure(new Error("stale"), "result.failure");
  app.setFailurePhase();
  getElement("retry").emit("click");
  activeLocale = "de";
  emitLocaleChange();
  const assistance = {
    status: getElement("status").textContent,
    controls: snapshotControls(),
  };
  activeLocale = "en";
  app.showBackendFailure(new Error("stale"), "result.failure");
  app.setFailurePhase();
  app.progressComplete("requesting camera access…");
  activeLocale = "de";
  emitLocaleChange();
  process.stdout.write(JSON.stringify({
    localizedFailures,
    assistance,
    newerStatus: getElement("status").textContent,
    detail: "Error: 503",
    backendSolveCalls,
  }));
} else if (probeName === "assistance-locale") {
  app.load(entry);
  app.renderAnswer(failure, { focus: false });
  app.setFinders([{ x: 2, y: 3 }]);
  app.syncAssistanceControls(true);
  const oneFinderBefore = { controls: snapshotControls(), geometry: app.geometry() };
  activeLocale = "de";
  emitLocaleChange();
  const oneFinderAfter = { controls: snapshotControls(), geometry: app.geometry() };
  app.setFinders([{ x: 2, y: 3 }, { x: 12, y: 3 }]);
  app.syncAssistanceControls(true);
  const twoFindersBefore = { controls: snapshotControls(), geometry: app.geometry() };
  activeLocale = "en";
  emitLocaleChange();
  const twoFindersAfter = { controls: snapshotControls(), geometry: app.geometry() };
  const incompleteCorners = [{ x: 1, y: 1 }, { x: 14, y: 1 }];
  app.setOutline(incompleteCorners, []);
  app.syncAssistanceControls(true);
  const incompleteOutlineBefore = { controls: snapshotControls(), geometry: app.geometry() };
  activeLocale = "de";
  emitLocaleChange();
  const incompleteOutlineAfter = { controls: snapshotControls(), geometry: app.geometry() };
  const corners = [
    { x: 1, y: 1 }, { x: 14, y: 1 }, { x: 14, y: 7 }, { x: 1, y: 7 },
  ];
  const midpoints = [
    { x: 8, y: 1 }, { x: 14, y: 4 }, { x: 8, y: 7 }, { x: 1, y: 4 },
  ];
  app.setOutline(corners, midpoints);
  app.syncAssistanceControls(true);
  const outlineBefore = snapshotControls();
  const geometryBefore = app.geometry();
  activeLocale = "en";
  emitLocaleChange();
  process.stdout.write(JSON.stringify({
    oneFinderBefore,
    oneFinderAfter,
    twoFindersBefore,
    twoFindersAfter,
    incompleteOutlineBefore,
    incompleteOutlineAfter,
    outlineBefore,
    outlineAfter: snapshotControls(),
    geometryBefore,
    geometryAfter: app.geometry(),
    backendSolveCalls,
  }));
} else if (probeName === "narrow-failure") {
  app.load(entry);
  const narrow = app.requireSolveAnswer({
    ok: false,
    failure: "at most 12 photographs of one code at a time",
  });
  app.renderAnswer(narrow, { focus: false });
  const success = {
    ok: true,
    text: "PUBLIC",
    finders: [],
    width: 16,
    height: 8,
    images_given: 1,
    candidates_tried: 1,
    source: "direct",
    clean_png: "data:image/png;base64,AA==",
    token: "public-token",
    exportable: true,
  };
  process.stdout.write(JSON.stringify({
    payload: getElement("payload").innerHTML,
    verdict: getElement("verdict").textContent,
    finders: narrow.finders,
    successUnchanged: app.requireSolveAnswer(success) === success,
  }));
} else if (probeName === "dynamic-targets") {
  app.load(entry);
  app.liveEvent({ type: "finders", points: [] });
  getElement("outlineRetry").emit("click");
  process.stdout.write(JSON.stringify({
    liveStage: getElement("liveStage").innerHTML,
    canvasClass: getElement("photo").classList.toString(),
    canvasWidth: getElement("photo").width,
    canvasHeight: getElement("photo").height,
  }));
} else if (probeName === "malformed-success") {
  const malformed = [
    { ok: true },
    { ok: true, text: "PUBLIC", finders: null },
    { ok: true, text: "PUBLIC", finders: [], width: 16, height: 8, source: "direct" },
  ];
  const rejected = malformed.map((answer) => {
    try { app.requireSolveAnswer(answer); return null; }
    catch (error) { return String(error); }
  });
  const success = {
    ok: true,
    text: "PUBLIC",
    finders: [],
    width: 16,
    height: 8,
    images_given: 1,
    candidates_tried: 1,
    source: "direct",
    clean_png: "data:image/png;base64,AA==",
    token: "public-token",
    exportable: true,
  };
  app.setBackendAnswer({ ok: true });
  app.load(entry);
  app.solve().then(() => {
    const solveFailure = { status: getElement("status").textContent, phase: app.phase() };
    app.load(entry);
    return app.catalogRun().then(() => {
      process.stdout.write(JSON.stringify({
        rejected,
        solveFailure,
        catalogueFailure: { status: getElement("status").textContent, phase: app.phase() },
        successUnchanged: app.requireSolveAnswer(success) === success,
        backendSolveCalls,
      }));
    });
  }).catch((error) => { console.error(error); process.exitCode = 1; });
}
"""
    completed = subprocess.run(
        [
            "node",
            "-e",
            script,
            str(web / "app.js"),
            str(web / "locale.js"),
            str(web / "studio-state.js"),
            str(web / "outline-editor.js"),
            probe,
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def _browser_executable() -> str | None:
    candidates: list[str | Path | None] = [
        shutil.which(name) for name in ("chrome", "google-chrome", "chromium", "msedge")
    ]
    candidates.extend(
        [
            Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
            Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
            Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        ]
    )
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    return None


def _call_browser_target_probe(tmp_path: Path, viewport_width: int):
    browser = _browser_executable()
    if browser is None:
        pytest.skip("Chrome/Edge is unavailable for the real layout regression probe")

    web = ROOT / "src" / "qrsalvage" / "web"
    source = (web / "app.js").read_text(encoding="utf-8")
    start = source.index("function canvasPoint(e)")
    end = source.index('\ncanvas.addEventListener("click"', start)
    canvas_point = source[start:end]
    style_uri = (web / "style.css").resolve().as_uri()
    inner_page = f"""<!doctype html>
<html><head><meta charset="utf-8"><link rel="stylesheet" href="{style_uri}"></head>
<body>
  <section id="live"><p class="stage"><a href="#method">How recovery works</a></p></section>
  <canvas id="landscape" class="outline-editing" width="16" height="8" data-scale="1"></canvas>
  <canvas id="portrait" class="outline-editing" width="8" height="16" data-scale="1"></canvas>
  <script>
    let canvas;
    {canvas_point}
    const measureCanvas = (id) => {{
      canvas = document.getElementById(id);
      const rect = canvas.getBoundingClientRect();
      const mapped = canvasPoint({{
        clientX: rect.left + rect.width * .25,
        clientY: rect.top + rect.height * .75,
      }});
      return {{ width: rect.width, height: rect.height, mapped }};
    }};
    const linkRect = document.querySelector("#live .stage a").getBoundingClientRect();
    document.body.dataset.measurement = JSON.stringify({{
      viewport: window.innerWidth,
      link: {{ width: linkRect.width, height: linkRect.height }},
      landscape: measureCanvas("landscape"),
      portrait: measureCanvas("portrait"),
    }});
  </script>
</body></html>"""
    page = tmp_path / f"dynamic-targets-{viewport_width}.html"
    page.write_text(
        f"""<!doctype html><html><body>
<iframe id="probe" width="{viewport_width}" height="700"
  srcdoc="{html.escape(inner_page, quote=True)}"></iframe>
<script>
  const probe = document.getElementById("probe");
  probe.addEventListener("load", () => {{
    document.body.dataset.measurement = probe.contentDocument.body.dataset.measurement;
  }});
</script>
</body></html>""",
        encoding="utf-8",
    )
    profile = tmp_path / f"browser-profile-{viewport_width}"
    completed = subprocess.run(
        [
            browser,
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--allow-file-access-from-files",
            "--force-device-scale-factor=1",
            f"--window-size={viewport_width},800",
            f"--user-data-dir={profile}",
            "--dump-dom",
            "--virtual-time-budget=1000",
            page.resolve().as_uri(),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    match = re.search(r'data-measurement="([^"]+)"', completed.stdout)
    assert match is not None, completed.stdout
    return json.loads(html.unescape(match.group(1)))


def _call_companion_controller_probe(probe: str):
    helper = ROOT / "src" / "qrsalvage" / "web" / "companion.js"
    app = ROOT / "src" / "qrsalvage" / "web" / "app.js"
    script = r"""
const fs = require("fs");
const { createCompanionController } = require(process.argv[1]);
const probe = process.argv[2];

if (probe === "storage") {
  const source = fs.readFileSync(process.argv[3], "utf8");
  const start = source.indexOf("function guardedStorage");
  const end = source.indexOf("\nconst companionLocal", start);
  const definition = source.slice(start, end);
  const compile = (window) => new Function(
    "window", `"use strict"; ${definition}; return guardedStorage;`
  )(window);
  let stored = "false";
  let failRead = false;
  const window = {
    localStorage: {
      getItem() {
        if (failRead) throw new Error("read refused");
        return stored;
      },
      setItem() { throw new Error("write refused"); },
    },
  };
  const local = compile(window)("localStorage");
  const before = local.get("qrsalvage.motionReduced");
  local.set("qrsalvage.motionReduced", "true");
  const afterFailedWrite = local.get("qrsalvage.motionReduced");
  failRead = true;
  const afterFailedRead = local.get("qrsalvage.motionReduced");
  let readAttempts = 0;
  const readFailureWindow = {
    localStorage: {
      getItem() {
        readAttempts += 1;
        if (readAttempts === 1) throw new Error("read refused");
        return "false";
      },
      setItem() { throw new Error("write refused"); },
    },
  };
  const afterReadFailure = compile(readFailureWindow)("localStorage");
  const failedRead = afterReadFailure.get("qrsalvage.motionReduced");
  afterReadFailure.set("qrsalvage.motionReduced", "true");
  const memoryAfterReadFailure = afterReadFailure.get("qrsalvage.motionReduced");
  process.stdout.write(JSON.stringify({
    before, afterFailedWrite, afterFailedRead, failedRead, memoryAfterReadFailure,
  }));
  process.exit(0);
}

function createHarness() {
  const animations = [];
  const cssAnimation = { cancelled: 0, cancel() { this.cancelled += 1; } };
  let observer = null;
  class FakeObserver {
    constructor(callback) {
      this.callback = callback;
      this.disconnected = false;
      observer = this;
    }
    observe() {}
    disconnect() { this.disconnected = true; }
  }
  const viewportListeners = new Map();
  const viewport = {
    innerWidth: 320,
    innerHeight: 240,
    getComputedStyle() { return { transform: "none" }; },
    IntersectionObserver: FakeObserver,
    addEventListener(name, callback) { viewportListeners.set(name, callback); },
    removeEventListener(name, callback) {
      if (viewportListeners.get(name) === callback) viewportListeners.delete(name);
    },
  };
  const sprite = { style: {} };
  const controls = [];
  const bubble = {
    hidden: true,
    style: {},
    _innerHTML: "",
    offsetWidth: 208,
    offsetHeight: 160,
    get innerHTML() { return this._innerHTML; },
    set innerHTML(value) {
      this._innerHTML = value;
      controls.length = 0;
      if (value.includes("<a ")) {
        controls.push({ tagName: "A", style: {}, addEventListener() {} });
      }
      if (value.includes("<button ")) {
        controls.push({ tagName: "BUTTON", style: {}, addEventListener() {} });
      }
    },
    get offsetLeft() {
      return this.style.left ? Number.parseFloat(this.style.left) : 76;
    },
    get offsetTop() {
      return this.style.top ? Number.parseFloat(this.style.top) : 64;
    },
    querySelector(selector) {
      return controls.find((control) => control.tagName === selector.toUpperCase()) ?? null;
    },
    querySelectorAll(selector) {
      if (selector !== "a, button") throw new Error(`unexpected selector: ${selector}`);
      return controls;
    },
    replaceChildren() { this.innerHTML = ""; },
  };
  function anchor(rect) {
    return {
      rect,
      getBoundingClientRect() { return { ...this.rect }; },
    };
  }
  const anchors = {
    hero: anchor({ right: 140, top: 20 }),
    studio: anchor({ right: 180, top: 40 }),
    progress: anchor({ right: 220, top: 70 }),
    canvas: anchor({ right: 260, top: 90 }),
    manual: anchor({ right: 280, top: 110 }),
    result: anchor({ right: 315, top: 220 }),
    recovery: anchor({ right: 300, top: 180 }),
  };
  const root = {
    ownerDocument: { defaultView: viewport },
    style: {},
    dataset: {},
    offsetWidth: 96,
    offsetHeight: 96,
    querySelector(selector) {
      if (selector !== "#companionSprite") throw new Error(`unexpected selector: ${selector}`);
      return sprite;
    },
    animate() {
      const animation = { cancelled: 0, cancel() { this.cancelled += 1; } };
      animations.push(animation);
      return animation;
    },
    getAnimations() { return [cssAnimation]; },
  };
  const localValues = new Map();
  const sessionValues = new Map();
  const adapter = (values) => ({
    get(key) { return values.get(key) ?? null; },
    set(key, value) { values.set(key, value); },
  });
  const controller = createCompanionController({
    root,
    bubble,
    anchors,
    t: (key) => key,
    local: adapter(localValues),
    session: adapter(sessionValues),
    media: { matches: false },
  });
  return {
    animations, cssAnimation, observer, root, bubble, localValues, controller, viewport,
    viewportListeners, anchors,
  };
}

const harness = createHarness();
if (probe === "same-anchor-reduction") {
  harness.controller.update({ phase: "ready", payloadReady: false });
  harness.localValues.set("qrsalvage.motionReduced", "true");
  const decision = harness.controller.update({ phase: "ready", payloadReady: false });
  process.stdout.write(JSON.stringify({
    cancelled: harness.animations[0].cancelled,
    motion: decision.motion,
    renderedMotion: harness.root.dataset.motion,
  }));
} else if (probe === "same-anchor-active") {
  harness.controller.update({ phase: "ready", payloadReady: false });
  harness.controller.update({ phase: "ready", payloadReady: false });
  process.stdout.write(JSON.stringify({
    animationCount: harness.animations.length,
    cancelled: harness.animations[0].cancelled,
    motion: harness.root.dataset.motion,
  }));
} else if (probe === "destroy") {
  harness.controller.update({ phase: "recovering", payloadReady: false });
  harness.controller.destroy();
  process.stdout.write(JSON.stringify({
    waapiCancelled: harness.animations[0].cancelled,
    cssCancelled: harness.cssAnimation.cancelled,
    motion: harness.root.dataset.motion,
    observerDisconnected: harness.observer.disconnected,
  }));
} else if (probe === "placement") {
  harness.controller.update({ phase: "success", payloadReady: true });
  const match = /translate3d\((-?\d+)px, (-?\d+)px/.exec(harness.root.style.transform);
  if (!match) throw new Error(`missing transform: ${harness.root.style.transform}`);
  const x = Number(match[1]);
  const y = Number(match[2]);
  const left = Math.min(x, x + harness.bubble.offsetLeft);
  const right = Math.max(
    x + harness.root.offsetWidth,
    x + harness.bubble.offsetLeft + harness.bubble.offsetWidth,
  );
  const top = Math.min(y, y + harness.bubble.offsetTop);
  const bottom = Math.max(
    y + harness.root.offsetHeight,
    y + harness.bubble.offsetTop + harness.bubble.offsetHeight,
  );
  process.stdout.write(JSON.stringify({ left, right, top, bottom }));
} else if (probe === "pointer-policy") {
  const initial = {
    layer: harness.root.style.pointerEvents ?? null,
    bubble: harness.bubble.style.pointerEvents ?? null,
  };
  harness.controller.update({ phase: "success", payloadReady: true });
  const donationControls = harness.bubble.querySelectorAll("a, button").map((control) => ({
    tagName: control.tagName,
    pointerEvents: control.style.pointerEvents ?? null,
  }));
  harness.controller.update({
    phase: "assistance", assistance: "outline", payloadReady: false,
  });
  const hintControls = harness.bubble.querySelectorAll("a, button").map((control) => ({
    tagName: control.tagName,
    pointerEvents: control.style.pointerEvents ?? null,
  }));
  process.stdout.write(JSON.stringify({
    initial,
    layer: harness.root.style.pointerEvents ?? null,
    bubble: harness.bubble.style.pointerEvents ?? null,
    donationControls,
    hintControls,
  }));
} else if (probe === "anchor-reflow") {
  harness.controller.update({ phase: "ready", payloadReady: false });
  const initial = harness.root.style.transform;
  harness.anchors.studio.rect = { right: 300, top: 130 };
  const resize = harness.viewportListeners.get("resize");
  if (resize) resize();
  const resized = harness.root.style.transform;
  harness.anchors.studio.rect = { right: 170, top: 72 };
  harness.observer.callback([{
    target: harness.anchors.studio, isIntersecting: true, intersectionRatio: 1,
  }]);
  process.stdout.write(JSON.stringify({
    hasResizeListener: Boolean(resize), initial, resized,
    observed: harness.root.style.transform,
  }));
} else {
  throw new Error(`unknown probe: ${probe}`);
}
"""
    completed = subprocess.run(
        ["node", "-e", script, str(helper), probe, str(app)],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def _call_outline_editor(function: str, *args):
    return _call_web_module("outline-editor.js", function, *args)


def _data_url(image: Path | np.ndarray) -> str:
    if isinstance(image, Path):
        raw = image.read_bytes()
    else:
        ok, buffer = cv2.imencode(".png", image)
        assert ok
        raw = buffer.tobytes()
    return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")


def _curved_outline_case() -> tuple[np.ndarray, dict]:
    text = "QRSALVAGE-OUTLINE-0815"
    matrix = reencode(text)
    modules = matrix.shape[0]
    module_px = 9.0
    quiet = 5
    dome = 0.12
    photo = render_photo(
        matrix,
        Damage(module_px=module_px, curvature=0.0, contrast=0.25, dome=dome),
        seed=2,
    )
    centre = (photo.shape[0] - 1) / 2.0

    def rendered_point(x: float, y: float) -> np.ndarray:
        source = (np.array([x, y]) - centre) / centre
        source_radius = float(np.linalg.norm(source))
        target_radius = source_radius
        for _ in range(8):
            target_radius -= (target_radius + dome * target_radius**3 - source_radius) / (
                1.0 + 3.0 * dome * target_radius**2
            )
        target = source * (target_radius / source_radius)
        return centre + target * centre

    low = quiet * module_px
    high = (quiet + modules) * module_px
    middle = (low + high) / 2.0
    clockwise_corners = np.array(
        [
            rendered_point(low, low),
            rendered_point(high, low),
            rendered_point(high, high),
            rendered_point(low, high),
        ]
    )
    edge_midpoints = np.array(
        [
            rendered_point(middle, low),
            rendered_point(high, middle),
            rendered_point(middle, high),
            rendered_point(low, middle),
        ]
    )
    outline = {
        "corners": [{"x": float(x), "y": float(y)} for x, y in clockwise_corners],
        "edge_midpoints": [{"x": float(x), "y": float(y)} for x, y in edge_midpoints],
    }
    return photo, outline


def test_a_curved_outline_drives_recovery_and_progress(monkeypatch):
    photo, outline = _curved_outline_case()
    events = []
    # The manual path must not quietly fall back to finder detection. Removing the outline
    # forwarding makes this real recovery fail before a grid can be fitted.
    monkeypatch.setattr(pipeline, "detect_finders", lambda _binary: [])

    answer = solve_payload(
        {"image": _data_url(photo), "outline": outline},
        progress=lambda event, data: events.append({"type": event, **data}),
    )

    assert answer["ok"] is True
    assert answer["text"] == "QRSALVAGE-OUTLINE-0815"
    grids = [event for event in events if event["type"] == "grid"]
    assert grids
    assert all(len(event["corners"]) == 4 for event in grids)
    assert all(len(event["edge_midpoints"]) == 4 for event in grids)


@pytest.mark.parametrize(
    ("outline", "extra", "failure"),
    [
        ({}, {}, "outline needs corners and edge_midpoints"),
        ({"corners": [], "edge_midpoints": []}, {}, "outline arrays need exactly four points"),
        (
            {"corners": ["point"] * 4, "edge_midpoints": [{"x": 1, "y": 2}] * 4},
            {},
            "outline points need a numeric x and y",
        ),
        (
            {
                "corners": [{"x": float("nan"), "y": 2}] * 4,
                "edge_midpoints": [{"x": 1, "y": 2}] * 4,
            },
            {},
            "outline points must be finite coordinates",
        ),
        (
            {
                "corners": [{"x": 1, "y": 2}] * 4,
                "edge_midpoints": [{"x": float("inf"), "y": 2}] * 4,
            },
            {},
            "outline points must be finite coordinates",
        ),
        (
            {
                "corners": [{"x": 1, "y": 2}] * 4,
                "edge_midpoints": [{"x": 1, "y": 2}] * 4,
            },
            {"finder_points": [{"x": 1, "y": 2}] * 3},
            "use either finder points or a manual outline, not both",
        ),
    ],
)
def test_invalid_outlines_are_refused(outline, extra, failure):
    answer = solve_payload({"image": _data_url(FIXTURE), "outline": outline, **extra})

    assert answer["ok"] is False
    assert answer["failure"] == failure


def test_an_outline_applies_to_one_photograph_only():
    _photo, outline = _curved_outline_case()
    image = _data_url(FIXTURE)

    answer = solve_payload({"images": [image, image], "outline": outline})

    assert answer["ok"] is False
    assert answer["failure"] == "a manual outline applies to one photograph only"


@pytest.mark.parametrize("ensemble", ["sampling", "geometry"])
def test_an_outline_refuses_flat_ensemble_measurements(ensemble):
    _photo, outline = _curved_outline_case()

    answer = solve_payload({"image": _data_url(FIXTURE), "outline": outline, "ensemble": ensemble})

    assert answer["ok"] is False
    assert answer["failure"] == "a manual outline cannot be combined with an ensemble"


@pytest.mark.parametrize(
    "coordinate",
    [
        pytest.param(10**10000, id="huge-integer"),
        pytest.param(1e300, id="huge-finite-float"),
    ],
)
def test_outline_coordinates_must_stay_near_the_photograph(coordinate):
    outline = {
        "corners": [{"x": coordinate, "y": 2}] * 4,
        "edge_midpoints": [{"x": 1, "y": 2}] * 4,
    }

    answer = solve_payload({"image": _data_url(FIXTURE), "outline": outline})

    assert answer["ok"] is False
    assert answer["failure"] == "outline coordinates are too far outside the photograph"


def test_payload_carries_everything_the_page_shows():
    answer = solve_payload({"image": _data_url(FIXTURE)})

    assert answer["ok"] is True
    assert answer["text"].startswith("QRSALVAGE-SYNTHETIC")
    # Every field the page renders has to be present, or a metric silently disappears.
    for key in (
        "version",
        "modules",
        "wrong_known",
        "known_total",
        "timing",
        "uncertain",
        "candidates_tried",
        "finders",
        "grid",
        "clean_png",
        "reconstructed_png",
    ):
        assert key in answer, f"missing from the response: {key}"
    assert answer["clean_png"].startswith("data:image/png;base64,")
    assert set(answer["grid"].replace("\n", "")) <= {"#", ".", "?"}
    assert answer["payload_info"] == {
        "kind": "text",
        "label": "Plain text",
        "hint": "Plain text. No recognised QR payload format was assumed.",
        "fields": {},
    }
    assert json.dumps(answer)  # must survive serialisation, i.e. no numpy types leaked through


def test_a_broken_upload_is_reported_not_raised():
    answer = solve_payload({"image": "data:image/png;base64,bm90YW5pbWFnZQ=="})
    assert answer["ok"] is False
    assert answer["failure"]


def test_several_photographs_are_fused_when_none_reads_alone():
    """The strongest measured capability of the tool, reachable from the page.

    Three synthetic photographs of one code, each with its own stain, none of which the solver
    reads alone -- exactly the constructed case test_fusion.py pins down -- handed to the
    server as one request. The response must carry the fusion evidence, because whoever reads
    it decides whether to trust an install code on its strength.
    """
    from test_fusion import HARD_GROUP, HARD_STAIN, photographs
    from test_fusion import TEXT as FUSION_TEXT

    encoded = []
    for photo in photographs(HARD_STAIN, HARD_GROUP):
        ok, buffer = cv2.imencode(".png", photo)
        assert ok
        encoded.append(
            "data:image/png;base64," + base64.b64encode(buffer.tobytes()).decode("ascii")
        )

    answer = solve_payload({"images": encoded})

    assert answer["ok"] is True
    assert answer["text"] == FUSION_TEXT
    assert answer["images_given"] == 3
    assert answer["fusion"]["photographs"] == 3
    assert answer["fusion"]["rejected"] == []
    assert answer["fusion"]["disagreeing"] > 0
    assert json.dumps(answer)


def test_a_single_image_may_still_arrive_under_the_old_key():
    """The page sends `images` now; the old `image` contract stays honoured."""
    single = solve_payload({"image": _data_url(FIXTURE)})
    listed = solve_payload({"images": [_data_url(FIXTURE)]})
    assert single["ok"] is True and listed["ok"] is True
    assert single["text"] == listed["text"]
    assert "fusion" not in listed, "one photograph is not a fusion"


def test_whole_photo_direct_decode_is_available_through_the_shared_api():
    text = "https://example.com/recovery?a=" + "x" * 134
    page = render(reencode(text, ecc="Q"), scale=2, quiet=0)
    stretched = cv2.resize(
        page,
        (page.shape[1], round(page.shape[0] * 1.9)),
        interpolation=cv2.INTER_NEAREST,
    )
    ok, encoded = cv2.imencode(".png", stretched)
    assert ok

    answer = solve_payload(
        {"image": "data:image/png;base64," + base64.b64encode(encoded.tobytes()).decode("ascii")}
    )

    assert answer["ok"] is True
    assert answer["text"] == text
    assert answer["source"] == "direct"
    assert answer["candidates_tried"] == 1
    assert answer["exportable"] is True
    assert answer["clean_png"].startswith("data:image/png;base64,")

    data_url = "data:image/png;base64," + base64.b64encode(encoded.tobytes()).decode("ascii")
    bridged = solve_payload({"image": data_url}, trusted_direct_text=text)
    assert bridged["ok"] is True
    assert bridged["text"] == text
    assert bridged["source"] == "direct"


def test_direct_decode_text_cannot_be_supplied_in_the_request_payload():
    answer = solve_payload({"image": _data_url(FIXTURE), "direct_text": "invented"})

    assert answer["ok"] is True
    assert answer["text"] != "invented"
    assert answer["source"] == "recovery"


def test_trusted_direct_decode_can_identify_a_member_of_a_multi_image_request():
    payload = {"images": [_data_url(FIXTURE), _data_url(FIXTURE)]}

    answer = solve_payload(payload, trusted_direct_texts=[None, "MEMBER-TWO"])

    assert answer["ok"] is True
    assert answer["text"] == "MEMBER-TWO"
    assert answer["source"] == "direct"
    assert answer["images_given"] == 2


def test_a_matter_code_arrives_with_its_manual_pairing_code():
    """From photograph to the number a person types into Home Assistant, in one answer.

    The whole audience of this tool is someone whose code cannot be scanned; for Matter the
    derived manual pairing code is what they actually need, so the answer carries it."""
    from qrsalvage.core.decoding import reencode
    from qrsalvage.synth import Damage, render_photo

    photo = render_photo(
        reencode("MT:Y.K9042C00KA0648G00"), Damage(contrast=0.30, curvature=0.15), seed=2
    )
    ok, buffer = cv2.imencode(".png", photo)
    assert ok
    answer = solve_payload(
        {"image": "data:image/png;base64," + base64.b64encode(buffer.tobytes()).decode("ascii")}
    )

    assert answer["ok"] is True
    info = answer["payload_info"]
    assert info["kind"] == "matter"
    assert info["label"] == "Matter onboarding code"
    assert info["fields"]["manual_pairing_code"] == "3497-011-2332"
    assert info["fields"]["setup_passcode"] == "20202021"
    assert "Home Assistant" in info["hint"]
    assert json.dumps(answer)


def test_hand_placed_finders_are_accepted():
    """The escape hatch: three rough clicks instead of the automatic search."""
    automatic = solve_payload({"image": _data_url(FIXTURE)})
    assert len(automatic["finders"]) >= 3

    # Displace every click by 20 px, which is far more than anyone misses by.
    points = [{"x": f["x"] + 20, "y": f["y"] - 20} for f in automatic["finders"][:3]]
    manual = solve_payload({"image": _data_url(FIXTURE), "finder_points": points})

    assert manual["ok"] is True
    assert manual["text"] == automatic["text"]
    assert manual["wrong_known"] == automatic["wrong_known"], (
        "a hand-placed click must land on the same grid as the automatic search"
    )


def test_exports_are_built_from_the_remembered_result():
    """The page exports without recovering a second time.

    Rebuilding the result for each export would mean waiting the whole recovery again -- four
    seconds on an easy image, twenty on one that needs the fallbacks -- for a file the server
    already has everything to produce.
    """
    answer = solve_payload({"image": _data_url(FIXTURE)})
    assert answer["exportable"] is True

    expected = {
        "svg": (b"<svg", "image/svg+xml"),
        "pdf": (b"%PDF", "application/pdf"),
        "json": (b"{", "application/json"),
        "html": (b"<!doctype html>", "text/html"),
    }
    for fmt, (prefix, content_type) in expected.items():
        body, kind, filename = export_payload(
            {"token": answer["token"], "format": fmt, "size_mm": 30}
        )
        assert body.startswith(prefix), fmt
        assert kind == content_type
        assert filename.endswith(fmt)

    # The size the page asks for has to reach the file, or the millimetres are decoration.
    svg, _, _ = export_payload({"token": answer["token"], "format": "svg", "size_mm": 30})
    assert b'width="30.0mm"' in svg


def test_export_refuses_an_unknown_result_and_an_absurd_size():
    answer = solve_payload({"image": _data_url(FIXTURE)})
    with pytest.raises(KeyError):
        export_payload({"token": "not-a-token", "format": "svg"})
    with pytest.raises(ValueError):
        export_payload({"token": answer["token"], "format": "svg", "size_mm": 5000})
    with pytest.raises(ValueError):
        export_payload({"token": answer["token"], "format": "docx"})


def test_the_pairing_secret_is_not_split_out_by_default():
    answer = solve_payload({"image": _data_url(FIXTURE)})
    plain, _, _ = export_payload({"token": answer["token"], "format": "json"})
    assert b"zigbee" not in plain


@pytest.fixture
def running_server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd.server_address
    httpd.shutdown()
    httpd.server_close()


def test_front_page_has_the_adaptive_studio_shell(running_server):
    host, port = running_server
    connection = http.client.HTTPConnection(host, port, timeout=10)
    connection.request("GET", "/")
    page = connection.getresponse().read().decode("utf-8")
    for marker in (
        'id="studioShell"',
        'id="siteHero"',
        'id="studio"',
        'id="modeEasy"',
        'id="modePro"',
        'id="localeDe"',
        'id="localeEn"',
        'data-companion-anchor="hero"',
        'data-companion-anchor="studio"',
    ):
        assert marker in page
    assert page.index('src="studio-state.js"') < page.index('src="app.js"')
    assert page.index('src="locale.js"') < page.index('src="app.js"')


def test_static_assets_are_served_and_nothing_else(running_server):
    host, port = running_server
    connection = http.client.HTTPConnection(host, port, timeout=10)

    connection.request("GET", "/")
    response = connection.getresponse()
    body = response.read()
    assert response.status == 200
    assert b"qrsalvage" in body

    connection.request("GET", "/locale.js")
    response = connection.getresponse()
    assert response.status == 200
    assert b"chooseLocale" in response.read()

    connection.request("GET", "/studio-state.js")
    response = connection.getresponse()
    assert response.status == 200
    assert b"createStudioState" in response.read()

    # No directory traversal, no serving of anything but the one page.
    connection.request("GET", "/../pyproject.toml")
    assert connection.getresponse().status == 404
    connection.close()


def test_server_backend_processes_a_terminal_ndjson_record_without_a_newline():
    result = _call_backend_server_probe("terminal")

    assert result == {
        "resolved": True,
        "answer": {"type": "result", "ok": True, "text": "PUBLIC"},
        "events": [{"type": "grid", "modules": 21}],
    }


@pytest.mark.parametrize(
    ("probe", "message"),
    [("413", "photograph too large"), ("503", "503")],
)
def test_server_backend_rejects_non_success_http_answers(probe, message):
    result = _call_backend_server_probe(probe)

    assert result == {
        "resolved": False,
        "name": "Error",
        "message": message,
        "events": [],
    }


def test_app_rejects_a_missing_or_malformed_backend_answer_before_rendering():
    script = (ROOT / "src" / "qrsalvage" / "web" / "app.js").read_text(encoding="utf-8")
    solve = script[script.index("async function solve") : script.index("/* --- the live view")]

    assert "requireSolveAnswer" in solve
    assert solve.index("requireSolveAnswer(answer)") < solve.index("answer.ok")


def test_app_normalizes_narrow_api_failures_without_weakening_successes():
    result = _call_app_runtime_probe("narrow-failure")

    assert "at most 12 photographs of one code at a time" in result["payload"]
    assert result["finders"] == []
    assert result["successUnchanged"] is True


def test_app_rejects_incomplete_successes_inside_solve_and_catalogue():
    result = _call_app_runtime_probe("malformed-success")

    assert all("incomplete successful result" in message for message in result["rejected"])
    assert "incomplete successful result" in result["solveFailure"]["status"]
    assert result["solveFailure"]["phase"] == "failure"
    assert "incomplete successful result" in result["catalogueFailure"]["status"]
    assert result["catalogueFailure"]["phase"] == "failure"
    assert result["successUnchanged"] is True
    assert result["backendSolveCalls"] == 2


def test_outline_editor_is_served_with_touch_and_curved_geometry(running_server):
    """The manual escape hatch must survive unchanged in every static deployment."""
    host, port = running_server
    connection = http.client.HTTPConnection(host, port, timeout=10)

    assets = {}
    for path in ("/", "/style.css", "/outline-editor.js", "/app.js"):
        connection.request("GET", path)
        response = connection.getresponse()
        assert response.status == 200, path
        assets[path] = response.read().decode("utf-8")
    connection.close()

    page = assets["/"]
    style = assets["/style.css"]
    editor = assets["/outline-editor.js"]
    script = assets["/app.js"]
    assert 'id="outlineRetry"' in page
    assert 'id="outlineSolve"' in page
    assert re.search(r"\.outline-editing\s*\{[^}]*touch-action:\s*none", style, re.DOTALL)
    for fragment in (
        "pointerdown",
        "setPointerCapture",
        "edge_midpoints",
        "quadraticCurveTo",
    ):
        assert fragment in script
    assert re.search(
        r"outline:\s*outlineHint\s*\?\s*\{[^}]*corners:[^}]*edge_midpoints:",
        script,
        re.DOTALL,
    )
    assert '<script src="outline-editor.js"></script>' in page
    assert page.index('src="outline-editor.js"') < page.index('src="app.js"')
    assert "selectNearestHandle" in editor
    assert "qrOutlineEditor.selectNearestHandle" in script
    assert "moveHandle" in editor
    assert "qrOutlineEditor.moveHandle" in script
    instructions = (
        "manual.topLeft",
        "manual.topRight",
        "manual.bottomRight",
        "manual.bottomLeft",
    )
    positions = [script.index(name) for name in instructions]
    assert positions == sorted(positions)


def test_photo_selection_and_outline_expose_complete_keyboard_paths(running_server):
    """The visible upload and canvas cannot depend on a pointing device."""
    host, port = running_server
    connection = http.client.HTTPConnection(host, port, timeout=10)
    connection.request("GET", "/")
    page = connection.getresponse().read().decode("utf-8")
    connection.request("GET", "/app.js")
    script = connection.getresponse().read().decode("utf-8")
    connection.close()

    assert re.search(r'<div id="drop"[^>]*role="button"[^>]*tabindex="0"', page)
    canvas_tag = re.search(r'<canvas id="photo"[^>]*>', page)
    assert canvas_tag is not None
    assert 'role="application"' not in canvas_tag.group(0)
    assert 'tabindex="0"' not in canvas_tag.group(0)
    assert "aria-label=" not in canvas_tag.group(0)
    assert 'drop.addEventListener("keydown"' in script
    assert 'canvas.addEventListener("keydown"' in script
    assert "qrStudioState.isActivationKey" in script
    assert "qrOutlineEditor.keyboardCommand" in script
    assert "function setOutlineCanvasActive" in script
    assert 'canvas.setAttribute("role", "application")' in script
    assert 'canvas.setAttribute("tabindex", "0")' in script
    assert 'canvas.removeAttribute("role")' in script
    assert 'canvas.removeAttribute("tabindex")' in script
    assert 'canvas.removeAttribute("aria-label")' in script


def test_studio_state_reducer_keeps_mode_separate_from_recovery_phase():
    state = _call_web_module("studio-state.js", "createStudioState", "pro")
    assert state == {"phase": "welcome", "mode": "pro"}
    state = _call_web_module(
        "studio-state.js", "reduceStudioState", state, {"type": "RECOVERY_STARTED"}
    )
    assert state == {"phase": "recovering", "mode": "pro"}
    state = _call_web_module(
        "studio-state.js", "reduceStudioState", state, {"type": "SET_MODE", "mode": "easy"}
    )
    assert state == {"phase": "recovering", "mode": "easy"}


def test_keyboard_commands_cover_activation_placement_and_adjustment():
    assert _call_web_module("studio-state.js", "isActivationKey", "Enter") is True
    assert _call_web_module("studio-state.js", "isActivationKey", " ") is True
    assert _call_web_module("studio-state.js", "isActivationKey", "Tab") is False

    assert _call_outline_editor("keyboardCommand", "Enter", False) == {"type": "place"}
    assert _call_outline_editor("keyboardCommand", "ArrowLeft", False) == {
        "type": "move",
        "x": -1,
        "y": 0,
        "multiplier": 1,
    }
    assert _call_outline_editor("keyboardCommand", "ArrowDown", True) == {
        "type": "move",
        "x": 0,
        "y": 1,
        "multiplier": 5,
    }
    assert _call_outline_editor("keyboardCommand", "]", False) == {
        "type": "cycle",
        "direction": 1,
    }
    assert _call_outline_editor("keyboardCommand", "Escape", False) is None


def test_companion_only_offers_kofi_after_a_visible_success_once_per_session():
    success = {"phase": "success", "payloadReady": True, "reducedMotion": False}
    first = _call_web_module("companion.js", "companionDecision", success, {})
    assert first["pose"] == "celebrate"
    assert first["offerDonation"] is True
    again = _call_web_module("companion.js", "companionDecision", success, {"donationShown": True})
    assert again["offerDonation"] is False
    failed = _call_web_module(
        "companion.js",
        "companionDecision",
        {"phase": "failure", "payloadReady": False, "reducedMotion": False},
        {},
    )
    assert failed["offerDonation"] is False


def test_companion_reduced_motion_is_static_and_hints_are_once_only():
    state = {
        "phase": "assistance",
        "assistance": "outline",
        "payloadReady": False,
        "reducedMotion": True,
    }
    first = _call_web_module("companion.js", "companionDecision", state, {})
    assert first["motion"] == "still"
    assert first["hintKey"] == "companion.outline"
    seen = _call_web_module(
        "companion.js",
        "companionDecision",
        state,
        {"seenHints": ["companion.outline"]},
    )
    assert seen["hintKey"] is None


def test_companion_reduction_cancels_an_in_flight_same_anchor_animation():
    result = _call_companion_controller_probe("same-anchor-reduction")

    assert result == {"cancelled": 1, "motion": "still", "renderedMotion": "still"}


def test_companion_same_anchor_active_update_preserves_in_flight_animation():
    result = _call_companion_controller_probe("same-anchor-active")

    assert result == {"animationCount": 1, "cancelled": 0, "motion": "active"}


def test_companion_destroy_cancels_all_motion_and_leaves_a_still_sprite():
    result = _call_companion_controller_probe("destroy")

    assert result == {
        "waapiCancelled": 1,
        "cssCancelled": 1,
        "motion": "still",
        "observerDisconnected": True,
    }


def test_companion_places_the_sprite_and_visible_bubble_inside_the_viewport():
    result = _call_companion_controller_probe("placement")

    assert result["left"] >= 8
    assert result["right"] <= 312
    assert result["top"] >= 8
    assert result["bottom"] <= 232


def test_companion_remeasures_the_same_anchor_after_resize_and_observer_updates():
    result = _call_companion_controller_probe("anchor-reflow")

    assert result["hasResizeListener"] is True
    assert result["resized"] != result["initial"]
    assert result["observed"] != result["resized"]


def test_companion_storage_prefers_memory_after_browser_storage_fails():
    result = _call_companion_controller_probe("storage")

    assert result == {
        "before": "false",
        "afterFailedWrite": "true",
        "afterFailedRead": "true",
        "failedRead": None,
        "memoryAfterReadFailure": "true",
    }


def test_companion_controller_enforces_pointer_policy_for_dynamic_controls():
    result = _call_companion_controller_probe("pointer-policy")

    assert result == {
        "initial": {"layer": "none", "bubble": "none"},
        "layer": "none",
        "bubble": "none",
        "donationControls": [
            {"tagName": "A", "pointerEvents": "auto"},
            {"tagName": "BUTTON", "pointerEvents": "auto"},
        ],
        "hintControls": [{"tagName": "BUTTON", "pointerEvents": "auto"}],
    }


def test_companion_motion_control_is_labelled_and_os_reduction_always_wins():
    web = ROOT / "src" / "qrsalvage" / "web"
    page = (web / "index.html").read_text(encoding="utf-8")
    script = (web / "companion.js").read_text(encoding="utf-8")

    toggle = re.search(r'<button id="motionToggle"(?P<body>[^>]*)>', page)
    assert toggle is not None
    assert 'type="button"' in toggle["body"]
    assert 'data-i18n-aria="companion.motionToggle"' in toggle["body"]
    assert 'aria-pressed="false"' in toggle["body"]
    assert 'media.matches || local.get("qrsalvage.motionReduced") === "true"' in script


def test_companion_has_one_anchored_nonblocking_layer_and_motion_safe_sprite():
    web = ROOT / "src" / "qrsalvage" / "web"
    page = (web / "index.html").read_text(encoding="utf-8")
    style = (web / "style.css").read_text(encoding="utf-8")
    script = (web / "companion.js").read_text(encoding="utf-8")

    assert page.count('id="companion"') == 1
    assert page.index('id="studioShell"') < page.index('id="companion"')
    assert 'id="companionSprite" aria-hidden="true"' in page
    assert re.search(r'id="companionBubble"[^>]*\bhidden\b', page)
    for anchor in ("hero", "studio", "progress", "canvas", "manual", "result", "recovery"):
        assert page.count(f'data-companion-anchor="{anchor}"') == 1
    assert re.search(r"#companion\s*\{[^}]*pointer-events:\s*none", style, re.DOTALL)
    bubble_rule = re.search(r"#companionBubble\s*\{(?P<body>[^}]*)\}", style, re.DOTALL)
    controls_rule = re.search(
        r"#companionBubble a, #companionBubble button\s*\{(?P<body>[^}]*)\}",
        style,
        re.DOTALL,
    )
    assert bubble_rule is not None
    assert "pointer-events: none" in bubble_rule["body"]
    assert controls_rule is not None
    assert "pointer-events: auto" in controls_rule["body"]
    assert "new IntersectionObserver" in script
    assert ".getBoundingClientRect()" in script
    assert ".animate(" in script
    assert "currentAnimation?.cancel()" in script
    assert "observer?.disconnect()" in script
    assert "steps(" in style
    reduced = style[style.rindex("@media (prefers-reduced-motion: reduce)") :]
    assert "#companion" in reduced
    assert "animation: none" in reduced


def test_companion_walk_animation_holds_both_discrete_sprite_frames():
    style = (ROOT / "src" / "qrsalvage" / "web" / "style.css").read_text(encoding="utf-8")

    walk = re.search(r"animation:\s*companion-walk[^;]+;", style)
    assert walk is not None
    assert "steps(2, jump-none)" in walk.group(0)


def test_companion_assets_are_served_built_and_loaded_between_locale_and_app(running_server):
    host, port = running_server
    connection = http.client.HTTPConnection(host, port, timeout=10)
    assets = {}
    for path in ("/", "/companion.js", "/axolotl-companion.png"):
        connection.request("GET", path)
        response = connection.getresponse()
        assert response.status == 200, path
        assets[path] = response.read()
    connection.close()

    page = assets["/"].decode("utf-8")
    assert page.index('src="locale.js"') < page.index('src="companion.js"')
    assert page.index('src="companion.js"') < page.index('src="app.js"')
    assert b"companionDecision" in assets["/companion.js"]
    assert assets["/axolotl-companion.png"].startswith(b"\x89PNG\r\n\x1a\n")


def test_companion_uses_the_single_dispatch_path_and_visible_payload_gate():
    script = (ROOT / "src" / "qrsalvage" / "web" / "app.js").read_text(encoding="utf-8")
    dispatch = script[
        script.index("function dispatchStudio") : script.index(
            "window.dispatchStudio = dispatchStudio"
        )
    ]
    assert "companion.update" in dispatch
    finder_handler = script[
        script.index('$("retry").addEventListener') : script.index(
            '$("outlineRetry").addEventListener'
        )
    ]
    outline_handler = script[
        script.index('$("outlineRetry").addEventListener') : script.index(
            '$("outlineSolve").addEventListener'
        )
    ]
    assert 'companionDetail.assistance = "finders"' in finder_handler
    assert 'dispatchStudio({ type: "ASSISTANCE_REQUIRED" })' in finder_handler
    assert 'companionDetail.assistance = "outline"' in outline_handler
    assert 'dispatchStudio({ type: "ASSISTANCE_REQUIRED" })' in outline_handler

    success_render = script[
        script.index("function renderAnswer") : script.index("async function download")
    ]
    assert success_render.index("payload.innerHTML") < success_render.index(
        '$("resultHeading").focus()'
    )
    assert success_render.index('$("resultHeading").focus()') < success_render.index(
        "companionDetail.payloadReady = true"
    )


def test_companion_kofi_is_a_clicked_post_success_link_once_per_session():
    web = ROOT / "src" / "qrsalvage" / "web"
    companion = (web / "companion.js").read_text(encoding="utf-8")
    app = (web / "app.js").read_text(encoding="utf-8")

    assert 'href="https://ko-fi.com/shadesmaverick"' in companion
    assert 'target="_blank"' in companion
    assert 'rel="noopener noreferrer"' in companion
    assert "fetch(" not in companion
    assert "iframe" not in companion.lower()
    assert "thanksHtml" not in app
    assert "axolotl.png" not in app
    assert set(re.findall(r"qrsalvage\.donation[A-Za-z]+", companion)) == {
        "qrsalvage.donationShown"
    }


@pytest.mark.parametrize(
    ("event", "phase"),
    [
        ("RESET", "welcome"),
        ("IMAGES_READY", "ready"),
        ("PREPARING", "preparing"),
        ("RECOVERY_STARTED", "recovering"),
        ("ASSISTANCE_REQUIRED", "assistance"),
        ("RECOVERY_SUCCEEDED", "success"),
        ("RECOVERY_FAILED", "failure"),
    ],
)
def test_studio_state_reducer_has_one_named_phase(event, phase):
    state = _call_web_module("studio-state.js", "createStudioState", "invalid")
    state = _call_web_module("studio-state.js", "reduceStudioState", state, {"type": event})
    view = _call_web_module("studio-state.js", "viewForState", state)
    assert state["phase"] == phase
    assert state["mode"] == "easy"
    assert view["phaseClass"] == f"studio-phase-{phase}"


def test_easy_and_pro_change_visibility_not_recovery_requests():
    easy = _call_web_module(
        "studio-state.js", "viewForState", {"phase": "recovering", "mode": "easy"}
    )
    pro = _call_web_module(
        "studio-state.js", "viewForState", {"phase": "recovering", "mode": "pro"}
    )
    assert easy["diagnosticsExpanded"] is False
    assert pro["diagnosticsExpanded"] is True
    script = (ROOT / "src" / "qrsalvage" / "web" / "app.js").read_text(encoding="utf-8")
    solve = script[script.index("async function solve") : script.index("/* --- the live view")]
    assert "studioState.mode" not in solve


def test_runtime_messages_use_locale_keys_instead_of_raw_english_assignments():
    script = (ROOT / "src" / "qrsalvage" / "web" / "app.js").read_text(encoding="utf-8")
    messages = {
        '"requesting camera access…"': "camera.requesting",
        '"capturing photographs…"': "camera.capturing",
        '"preparing the captured photographs…"': "camera.preparing",
        '"preparing the recovery engine…"': "progress.preparing",
        '"Recovery started"': "progress.started",
        '"Recovery failed"': "result.failure",
        '"QR code recovered"': "result.success",
        '"Catalogue recovery failed"': "catalogue.recoveryFailure",
        '"Catalogue recovery complete"': "catalogue.complete",
        '"preparing the catalogue download…"': "catalogue.preparingDownload",
        '"Catalogue downloaded"': "catalogue.downloaded",
        '"Export failed"': "export.failureAnnouncement",
        '"copied ✓"': "clipboard.copied",
        '"copy failed — select the text"': "clipboard.failure",
    }
    for literal, key in messages.items():
        assert literal not in script
        assert f't("{key}"' in script


def test_homepage_locale_contract_covers_metadata_controls_privacy_and_footer():
    page = (ROOT / "src" / "qrsalvage" / "web" / "index.html").read_text(encoding="utf-8")

    required_consumers = {
        'data-i18n="meta.title"',
        'data-i18n-content="meta.description"',
        'data-i18n-content="meta.ogTitle"',
        'data-i18n-content="meta.ogDescription"',
        'data-i18n-aria="nav.primary"',
        'data-i18n-aria="nav.home"',
        'data-i18n-aria="mode.label"',
        'data-i18n-aria="locale.label"',
        'data-i18n="input.drop"',
        'data-i18n="input.choose"',
        'data-i18n="input.multiHint"',
        'data-i18n="camera.title"',
        'data-i18n="camera.captureSingle"',
        'data-i18n="camera.close"',
        'data-i18n="input.modeOne"',
        'data-i18n="input.modeMany"',
        'data-i18n="stage.input"',
        'data-i18n="stage.export"',
        'data-i18n="export.explanation"',
        'data-i18n="export.edgeLength"',
        'data-i18n="export.errorCorrection"',
        'data-i18n="export.originalLevel"',
        'data-i18n="export.report"',
        'data-i18n="export.splitPayload"',
        'data-i18n="catalogue.title"',
        'data-i18n="catalogue.explanation"',
        'data-i18n="catalogue.codeSize"',
        'data-i18n="catalogue.download"',
        'data-i18n="situations.eyebrow"',
        'data-i18n="privacy.eyebrow"',
        'data-i18n="privacy.explanation"',
        'data-i18n="privacy.source"',
        'data-i18n="footer.method"',
        'data-i18n="footer.legal"',
        'data-i18n="footer.license"',
    }
    missing = sorted(fragment for fragment in required_consumers if fragment not in page)
    assert not missing, f"Unlocalized homepage consumers: {missing}"


def test_payload_presentation_has_german_labels_advice_warnings_and_fields():
    translations = {
        "payload.label.matter": "Matter-Inbetriebnahmecode",
        "payload.hint.matter": (
            "Ein Matter-Inbetriebnahmecode. Füge das Gerät in Home Assistant, Apple Home "
            "oder Google Home hinzu — und gib den manuellen Pairing-Code ein, wenn Scannen "
            "nicht möglich ist."
        ),
        "payload.warning.matter": (
            "Passcode und manueller Pairing-Code nehmen das Gerät in Betrieb. "
            "Behandle sie wie Schlüssel."
        ),
        "payload.field.manual_pairing_code": "manueller Pairing-Code",
    }
    for key, expected in translations.items():
        assert _call_web_module("locale.js", "translate", "de", key) == expected


def test_locale_change_rerenders_runtime_state_without_starting_recovery():
    script = (ROOT / "src" / "qrsalvage" / "web" / "app.js").read_text(encoding="utf-8")
    start = script.index('document.addEventListener("qrsalvage:localechange"')
    end = script.index("function escapeHtml", start)
    handler = script[start:end]

    assert "renderAnswer(lastAnswer" in handler
    assert "updateOutlineInstructions" in handler
    assert "companion.refreshLocale" in handler
    assert "solve(" not in handler
    assert "catalogRun(" not in handler
    assert "window.qrBackend.solve" not in handler
    assert "window.qrBackend.file" not in handler


def test_backend_failure_prefix_is_localized_again_without_losing_technical_detail():
    contract = _call_backend_contract_probe()
    result = _call_app_runtime_probe("failure-locale")

    assert contract == {
        "server": {
            "failurePrefixKey": "backend.failure.server",
        },
        "worker": {
            "failurePrefixKey": "backend.failure.browser",
        },
    }
    announcements = {
        "boot.failure": "Die Recovery-Engine konnte nicht gestartet werden",
        "result.failure": "Rettung fehlgeschlagen",
        "catalogue.recoveryFailure": "Katalogrettung fehlgeschlagen",
    }
    for key, expected_announcement in announcements.items():
        localized = result["localizedFailures"][key]
        assert localized["english"].endswith(result["detail"])
        assert localized["german"].endswith(result["detail"])
        assert localized["english"] != localized["german"]
        assert localized["announcement"] == expected_announcement
    assert result["assistance"] == {
        "status": "",
        "controls": {
            "retry": True,
            "outlineRetry": True,
            "outlineSolve": True,
            "cancel": False,
        },
    }
    assert result["newerStatus"] == "requesting camera access…"
    assert result["backendSolveCalls"] == 0


def test_locale_rerender_preserves_active_assistance_controls_and_geometry():
    result = _call_app_runtime_probe("assistance-locale")

    finder_controls = {
        "retry": True,
        "outlineRetry": True,
        "outlineSolve": True,
        "cancel": False,
    }
    outline_controls = {
        "retry": True,
        "outlineRetry": True,
        "outlineSolve": False,
        "cancel": False,
    }
    for snapshot in (result["oneFinderBefore"], result["oneFinderAfter"]):
        assert snapshot["controls"] == finder_controls
        assert snapshot["geometry"]["picked"] == [{"x": 2, "y": 3}]
    for snapshot in (result["twoFindersBefore"], result["twoFindersAfter"]):
        assert snapshot["controls"] == finder_controls
        assert snapshot["geometry"]["picked"] == [
            {"x": 2, "y": 3},
            {"x": 12, "y": 3},
        ]
    incomplete_controls = {
        "retry": True,
        "outlineRetry": True,
        "outlineSolve": True,
        "cancel": False,
    }
    for snapshot in (
        result["incompleteOutlineBefore"],
        result["incompleteOutlineAfter"],
    ):
        assert snapshot["controls"] == incomplete_controls
        assert snapshot["geometry"] == {
            "picked": [],
            "corners": [{"x": 1, "y": 1}, {"x": 14, "y": 1}],
            "midpoints": [],
        }
    assert result["outlineBefore"] == outline_controls
    assert result["outlineAfter"] == outline_controls
    assert result["geometryAfter"] == result["geometryBefore"]
    assert result["backendSolveCalls"] == 0


def test_studio_modes_share_controls_and_only_change_disclosure():
    web = ROOT / "src" / "qrsalvage" / "web"
    page = (web / "index.html").read_text(encoding="utf-8")
    script = (web / "app.js").read_text(encoding="utf-8")
    style = (web / "style.css").read_text(encoding="utf-8")
    for element_id in (
        "diagnosticsPanel",
        "diagnosticsDetails",
        "manualTools",
        "advancedExport",
        "matrixDetails",
    ):
        assert page.count(f'id="{element_id}"') == 1
    dispatch = script[
        script.index("function dispatchStudio") : script.index(
            "window.dispatchStudio = dispatchStudio"
        )
    ]
    assert "view.diagnosticsExpanded" in dispatch
    assert "view.manualToolsExpanded" in dispatch
    mode_handlers = script[
        script.index('for (const [id, modeName] of [["modeEasy"') : script.index(
            'motionToggle.addEventListener("click"'
        )
    ]
    assert "dispatchStudio" in mode_handlers
    assert "qrsalvage.mode" in mode_handlers
    assert "solve(" not in mode_handlers
    assert "catalogRun(" not in mode_handlers
    assert "qrBackend" not in mode_handlers
    assert ".studio-mode-easy" in style
    assert ".studio-mode-pro" in style


def test_locale_prefers_a_saved_choice_then_browser_german_then_english():
    assert _call_web_module("locale.js", "chooseLocale", "en", ["de-DE"]) == "en"
    assert _call_web_module("locale.js", "chooseLocale", None, ["de-DE", "en"]) == "de"
    assert _call_web_module("locale.js", "chooseLocale", None, ["fr-FR"]) == "en"


def test_locale_interpolates_values_and_falls_back_to_english():
    assert (
        _call_web_module("locale.js", "translate", "de", "progress.photoCount", {"count": 3})
        == "3 Fotos werden gemeinsam gelesen"
    )
    assert _call_web_module("locale.js", "translate", "fr", "action.reset") == "Start over"


def test_locale_dictionaries_have_identical_keys():
    keys = _call_web_module("locale.js", "dictionaryKeys")
    assert keys["en"] == keys["de"]


def test_locale_manifest_covers_every_static_app_and_html_consumer():
    web = ROOT / "src" / "qrsalvage" / "web"
    script = "\n".join(
        (web / name).read_text(encoding="utf-8") for name in ("app.js", "companion.js")
    )
    keys = set(_call_web_module("locale.js", "dictionaryKeys")["en"])

    literal_calls = {key for _, key in re.findall(r"(?<![\w.])t\(\s*(['\"])([^'\"]+)\1", script)}
    call_heads = re.findall(r"(?<![\w.])t\(\s*([^,\n)]+)", script)
    dynamic_calls = {
        head.strip() for head in call_heads if not head.lstrip().startswith(('"', "'"))
    }
    assert dynamic_calls == {
        "DYNAMIC_LOCALE_KEYS.outlineCorners[outlineCorners.length]",
        "DYNAMIC_LOCALE_KEYS.payloadFields[key]",
        "DYNAMIC_LOCALE_KEYS.recoveryStages[e.type]",
        "decision.hintKey",
        "direct",
        "hintKey",
        "labelKey",
        "lastBackendFailure.announcementKey",
        "lastBackendFailure.prefixKey",
        "localeKey",
        "warningKey",
        "window.qrBackend.modeKey",
        "window.qrBackend.privacyKey",
    }

    manifests = re.findall(
        r"// DYNAMIC-LOCALE-CONSUMERS: START(?P<body>.*?)"
        r"// DYNAMIC-LOCALE-CONSUMERS: END",
        script,
        re.DOTALL,
    )
    assert len(manifests) == 2
    dynamic_keys = {
        key
        for body in manifests
        for _, key in re.findall(r"(['\"])([a-z][A-Za-z0-9]*(?:\.[A-Za-z0-9]+)+)\1", body)
    }

    html_keys: set[str] = set()
    for page in web.glob("*.html"):
        html_keys.update(
            key
            for _, key in re.findall(
                r"data-i18n(?:-aria|-content)?=(['\"])([^'\"]+)\1",
                page.read_text(encoding="utf-8"),
            )
        )

    consumers = literal_calls | dynamic_keys | html_keys
    assert consumers <= keys, f"Unknown locale consumers: {sorted(consumers - keys)}"


def test_locale_translate_rejects_an_unknown_key():
    helper = ROOT / "src" / "qrsalvage" / "web" / "locale.js"
    script = r"""
const { translate } = require(process.argv[1]);
let outcome;
try {
  translate("en", "review.deliberatelyMissing");
  outcome = { threw: false };
} catch (error) {
  outcome = { threw: true, message: error.message };
}
process.stdout.write(JSON.stringify(outcome));
"""
    completed = subprocess.run(
        ["node", "-e", script, str(helper)],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "threw": True,
        "message": "Unknown translation key: review.deliberatelyMissing",
    }


def test_locale_controller_applies_the_dom_and_survives_failed_storage():
    helper = ROOT / "src" / "qrsalvage" / "web" / "locale.js"
    script = r"""
const { createLocaleController } = require(process.argv[1]);
const text = { dataset: { i18n: "action.reset" }, textContent: "" };
const aria = {
  dataset: { i18nAria: "action.copy" },
  setAttribute(name, value) { this[name] = value; },
};
const german = { dataset: { lang: "de" }, hidden: false };
const english = { dataset: { lang: "en" }, hidden: false };
const deButton = {
  dataset: { locale: "de" },
  setAttribute(name, value) { this[name] = value; },
};
const enButton = {
  dataset: { locale: "en" },
  setAttribute(name, value) { this[name] = value; },
};
const groups = {
  "[data-i18n]": [text],
  "[data-i18n-aria]": [aria],
  "[data-i18n-content]": [],
  "[data-lang]": [german, english],
  "[data-locale]": [deButton, enButton],
};
const description = { content: "", setAttribute(name, value) { this[name] = value; } };
const document = {
  title: "",
  body: {
    dataset: {
      titleEn: "English title",
      titleDe: "German title",
      descriptionEn: "English description",
      descriptionDe: "German description",
    },
  },
  documentElement: { lang: "" },
  querySelectorAll(selector) { return groups[selector]; },
  querySelector(selector) { return selector === 'meta[name="description"]' ? description : null; },
  events: [],
  dispatchEvent(event) { this.events.push({ type: event.type, detail: event.detail }); },
  defaultView: { CustomEvent: class CustomEvent {
    constructor(type, options) { this.type = type; this.detail = options.detail; }
  } },
};
const storage = { setItem() { throw new Error("denied"); } };
const controller = createLocaleController({ locale: "en", document, storage });
controller.setLocale("de");
process.stdout.write(JSON.stringify({
  locale: controller.locale,
  lang: document.documentElement.lang,
  text: text.textContent,
  aria: aria["aria-label"],
  germanHidden: german.hidden,
  englishHidden: english.hidden,
  dePressed: deButton["aria-pressed"],
  enPressed: enButton["aria-pressed"],
  title: document.title,
  description: description.content,
  events: document.events,
}));
"""
    completed = subprocess.run(
        ["node", "-e", script, str(helper)],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "locale": "de",
        "lang": "de",
        "text": "Neu beginnen",
        "aria": "Kopieren",
        "germanHidden": False,
        "englishHidden": True,
        "dePressed": "true",
        "enPressed": "false",
        "title": "German title",
        "description": "German description",
        "events": [{"type": "qrsalvage:localechange", "detail": {"locale": "de"}}],
    }


def test_every_visible_interactive_kind_has_a_forty_four_pixel_contract():
    style = (ROOT / "src" / "qrsalvage" / "web" / "style.css").read_text(encoding="utf-8")
    rule = re.search(
        r"(?P<selectors>[^{}]*\.interactive-targets[^{}]*)\{(?P<body>[^}]*)\}",
        style,
        re.DOTALL,
    )
    assert rule is not None
    for selector in (
        ".site-brand",
        ".site-nav > a",
        "summary",
        ".manual-rail a",
        'input[type="radio"]',
        ".text-link",
        ".editorial-links a",
        "footer a",
        ".legal-page a",
        ".manual-content a",
        ".payload a[download]",
    ):
        assert selector in rule["selectors"], selector
    assert "min-width: 44px" in rule["body"]
    assert "min-height: 44px" in rule["body"]


def test_dynamic_live_link_and_outline_canvas_keep_44_pixel_targets():
    style = (ROOT / "src" / "qrsalvage" / "web" / "style.css").read_text(encoding="utf-8")
    state = _call_app_runtime_probe("dynamic-targets")

    live_link = re.search(r"#live \.stage a\s*\{(?P<body>[^}]*)\}", style, re.DOTALL)
    outline_canvas = re.search(r"canvas\.outline-editing\s*\{(?P<body>[^}]*)\}", style, re.DOTALL)
    assert '<a href="method.html#search"' in state["liveStage"]
    assert "outline-editing" in state["canvasClass"]
    assert live_link is not None
    assert "min-height: 44px" in live_link["body"]
    assert outline_canvas is not None
    assert "min-width: 44px" in outline_canvas["body"]
    assert "min-height: 44px" in outline_canvas["body"]
    assert (state["canvasWidth"], state["canvasHeight"]) == (16, 8)


@pytest.mark.parametrize("viewport_width", [1440, 320])
def test_real_browser_keeps_dynamic_targets_large_without_warping_coordinates(
    tmp_path, viewport_width
):
    measurement = _call_browser_target_probe(tmp_path, viewport_width)

    assert measurement["viewport"] == viewport_width
    assert measurement["link"]["height"] >= 44
    landscape = measurement["landscape"]
    portrait = measurement["portrait"]
    for canvas in (landscape, portrait):
        assert canvas["width"] >= 44
        assert canvas["height"] >= 44
    assert landscape["width"] / landscape["height"] == pytest.approx(2)
    assert portrait["width"] / portrait["height"] == pytest.approx(0.5)
    assert landscape["mapped"] == pytest.approx({"x": 4, "y": 6})
    assert portrait["mapped"] == pytest.approx({"x": 2, "y": 12})


def test_generated_png_download_is_one_anchor_control_not_nested_interactives():
    script = (ROOT / "src" / "qrsalvage" / "web" / "app.js").read_text(encoding="utf-8")
    start = script.index("function panel(")
    panel = script[start : script.index('\n$("retry")', start)]

    assert '<a class="download-control"' in panel
    assert "<button" not in panel


def test_outline_editor_selects_the_nearest_overlapping_handle():
    """A short edge's midpoint must not lose merely because corners were checked first."""
    corners = [
        {"x": 0, "y": 0},
        {"x": 30, "y": 0},
        {"x": 30, "y": 30},
        {"x": 0, "y": 30},
    ]
    edge_midpoints = [
        {"x": 15, "y": 0},
        {"x": 30, "y": 15},
        {"x": 15, "y": 30},
        {"x": 0, "y": 15},
    ]

    selected = _call_outline_editor(
        "selectNearestHandle", {"x": 15, "y": 0}, corners, edge_midpoints, 18
    )

    assert selected == {"kind": "midpoint", "index": 0}


def test_outline_editor_corner_drag_moves_adjacent_midpoints_by_half():
    corners = [
        {"x": 0, "y": 0},
        {"x": 100, "y": 0},
        {"x": 100, "y": 100},
        {"x": 0, "y": 100},
    ]
    edge_midpoints = [
        {"x": 50, "y": 0},
        {"x": 100, "y": 50},
        {"x": 50, "y": 100},
        {"x": 0, "y": 50},
    ]

    moved = _call_outline_editor(
        "moveHandle",
        corners,
        edge_midpoints,
        {"kind": "corner", "index": 0},
        {"x": 10, "y": 6},
    )

    assert moved == {
        "corners": [
            {"x": 10, "y": 6},
            {"x": 100, "y": 0},
            {"x": 100, "y": 100},
            {"x": 0, "y": 100},
        ],
        "edgeMidpoints": [
            {"x": 55, "y": 3},
            {"x": 100, "y": 50},
            {"x": 50, "y": 100},
            {"x": 5, "y": 53},
        ],
    }


def test_outline_editor_midpoint_drag_moves_only_that_midpoint():
    corners = [
        {"x": 0, "y": 0},
        {"x": 100, "y": 0},
        {"x": 100, "y": 100},
        {"x": 0, "y": 100},
    ]
    edge_midpoints = [
        {"x": 50, "y": 0},
        {"x": 100, "y": 50},
        {"x": 50, "y": 100},
        {"x": 0, "y": 50},
    ]

    moved = _call_outline_editor(
        "moveHandle",
        corners,
        edge_midpoints,
        {"kind": "midpoint", "index": 1},
        {"x": -4, "y": 7},
    )

    assert moved == {
        "corners": corners,
        "edgeMidpoints": [
            {"x": 50, "y": 0},
            {"x": 96, "y": 57},
            {"x": 50, "y": 100},
            {"x": 0, "y": 50},
        ],
    }


def test_the_legal_page_is_reachable_and_still_has_blanks_to_fill(running_server):
    """A page nobody links to does not satisfy an obligation to be reachable.

    German law requires an operator to be identifiable from the published site, and a donation
    button removes any argument about whether that applies here. So the front page has to link
    it, the page has to answer, and -- until someone fills in a name and a postal address that
    can receive mail -- the placeholders have to be loud enough that publishing with them still
    in place would be a decision rather than an oversight.
    """
    host, port = running_server
    connection = http.client.HTTPConnection(host, port, timeout=10)

    connection.request("GET", "/")
    front = connection.getresponse().read()
    assert b'href="legal.html"' in front, "the front page does not link the legal page"

    connection.request("GET", "/legal.html")
    response = connection.getresponse()
    page = response.read().decode("utf-8")
    assert response.status == 200
    assert response.getheader("Content-Type", "").startswith("text/html")
    assert "Impressum" in page and "Datenschutz" in page

    # The claim the whole project rests on belongs here in plain words, not only in a README.
    assert "verlassen Ihr Gerät nicht" in page

    # Turned around in September 2026, the day the operator's details went in. From here on a
    # placeholder reappearing -- a template refactor, a revert, an overeager merge -- is the
    # failure, because publishing with one would break a legal obligation, not a preference.
    assert "TODO" not in page, "a placeholder came back into the legal page"
    assert "Fabian Marius Freitag" in page, "the imprint lost the operator's name"
    connection.close()


def test_the_success_companion_points_at_the_live_kofi_page():
    script = (ROOT / "src" / "qrsalvage" / "web" / "companion.js").read_text(encoding="utf-8")

    assert 'href="https://ko-fi.com/shadesmaverick"' in script
    assert "ko-fi.com/yourname" not in script


def test_the_public_page_declares_its_canonical_address_and_search_files():
    page = (ROOT / "src" / "qrsalvage" / "web" / "index.html").read_text(encoding="utf-8")
    robots = (ROOT / "src" / "qrsalvage" / "web" / "robots.txt").read_text(encoding="utf-8")
    sitemap = (ROOT / "src" / "qrsalvage" / "web" / "sitemap.xml").read_text(encoding="utf-8")

    public = "https://shadesmaverick.github.io/qrsalvage/"
    assert f'<link rel="canonical" href="{public}">' in page
    assert f'<meta property="og:url" content="{public}">' in page
    assert f'<meta property="og:image" content="{public}qrsalvage-social.png">' in page
    assert f'"url": "{public}"' in page
    assert f"Sitemap: {public}sitemap.xml" in robots
    assert public in sitemap


def test_the_public_page_leads_with_general_qr_recovery():
    page = (ROOT / "src" / "qrsalvage" / "web" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "src" / "qrsalvage" / "web" / "app.js").read_text(encoding="utf-8")
    companion = (ROOT / "src" / "qrsalvage" / "web" / "companion.js").read_text(encoding="utf-8")
    locale = (ROOT / "src" / "qrsalvage" / "web" / "locale.js").read_text(encoding="utf-8")
    head, body = page.split("</head>", 1)

    assert "damaged qr code recovery" in head.lower()
    general_examples = ("packaging", "tickets", "documents", "product labels")
    assert all(phrase in head.lower() for phrase in general_examples)
    assert "including codes on curved surfaces like light bulbs" not in head.lower()
    assert "every qr code can carry something different" in body.lower()
    assert "saved your qr code?" in locale.lower()
    assert 't("donation.successPrompt")' in companion
    assert "saved your lamp?" not in script.lower()


def test_search_discovery_files_are_part_of_the_static_build():
    from scripts.build_site import PAGE_FILES

    assert {"robots.txt", "sitemap.xml"} <= set(PAGE_FILES)


def test_signal_studio_buttons_keep_a_44_pixel_target():
    style = (ROOT / "src" / "qrsalvage" / "web" / "style.css").read_text(encoding="utf-8")

    buttons = re.search(r"^\s*button\s*\{(?P<body>.*?)\}", style, re.MULTILINE | re.DOTALL)
    thumbnails = re.search(r"\.thumb button\s*\{(?P<body>.*?)\}", style, re.DOTALL)
    assert buttons is not None
    assert thumbnails is not None
    assert "min-width: 44px" in buttons.group("body")
    assert "min-height: 44px" in buttons.group("body")
    assert "width: 44px" in thumbnails.group("body")
    assert "height: 44px" in thumbnails.group("body")


def test_catalogue_cards_fit_a_320_pixel_viewport():
    style = (ROOT / "src" / "qrsalvage" / "web" / "style.css").read_text(encoding="utf-8")

    small_screen = style[
        style.index("@media (max-width: 20rem)") : style.index(
            "@media (prefers-reduced-motion: reduce)"
        )
    ]
    assert ".cards { grid-template-columns: minmax(0, 1fr); }" in small_screen
    body = re.search(r"^\s*body\s*\{(?P<body>.*?)\}", style, re.MULTILINE | re.DOTALL)
    assert body is not None
    assert "overflow-x: hidden" not in body.group("body")


def test_reduced_motion_statically_disables_every_shell_movement():
    style = (ROOT / "src" / "qrsalvage" / "web" / "style.css").read_text(encoding="utf-8")

    reduced_motion = style[style.rindex("@media (prefers-reduced-motion: reduce)") :]
    assert "#drop, #drop::before, button { transition: none; }" in reduced_motion
    assert "#drop.over { transform: none; }" in reduced_motion
    assert ".progress-scan { animation: none;" in reduced_motion
    assert style.rstrip().endswith(reduced_motion.rstrip())


def test_new_shell_spacing_stays_on_the_four_pixel_grid():
    style = (ROOT / "src" / "qrsalvage" / "web" / "style.css").read_text(encoding="utf-8")
    sections = (
        style[style.index("/* --- shared navigation") : style.index("/* --- identity")],
        style[style.index("/* --- Studio toolbar") : style.index("/* --- drop zone")],
        style[
            style.index("/* --- editorial sections") : style.index(
                "@media (prefers-reduced-motion: reduce)"
            )
        ],
    )

    spacing = re.compile(
        r"\b(?:gap|margin(?:-(?:top|right|bottom|left))?|"
        r"padding(?:-(?:top|right|bottom|left))?)\s*:\s*([^;]+);"
    )
    dimensions = re.compile(r"(-?\d+(?:\.\d+)?)(px|rem)")
    for section in sections:
        for declaration in spacing.findall(section):
            for value, unit in dimensions.findall(declaration):
                pixels = abs(float(value)) * (16 if unit == "rem" else 1)
                assert abs(pixels % 4) < 1e-9, declaration


def test_wait_feedback_is_graphical_accessible_and_motion_safe(running_server):
    """A long browser recovery must look alive without excluding motion-sensitive users."""
    host, port = running_server
    connection = http.client.HTTPConnection(host, port, timeout=10)

    connection.request("GET", "/")
    page = connection.getresponse().read().decode("utf-8")
    connection.request("GET", "/style.css")
    style = connection.getresponse().read().decode("utf-8")
    connection.request("GET", "/app.js")
    script = connection.getresponse().read().decode("utf-8")

    progress = re.search(r'<div id="progress"[^>]*>', page)
    assert progress is not None
    assert 'class="progress-mark" aria-hidden="true"' in page
    assert '<div id="status" class="note"></div>' in page
    live_status = re.search(r'<div id="statusLive"[^>]*>', page)
    assert live_status is not None
    assert 'class="sr-only"' in live_status.group(0)
    assert 'role="status"' in live_status.group(0)
    assert 'aria-live="polite"' in live_status.group(0)
    assert 'aria-atomic="true"' in live_status.group(0)
    assert "<main aria-busy=" not in page
    assert '<div id="workspace" aria-busy="false">' in page
    assert page.index('id="progress"') < page.index('id="workspace"')
    assert page.index('id="statusLive"') < page.index('id="workspace"')
    assert page.count('<main id="mainContent">') == 1
    assert '<a class="skip-link" href="#mainContent"' in page
    for button_id, label, pressed in (
        ("modeEasy", "Easy", "true"),
        ("modePro", "Pro", "false"),
        ("localeDe", "DE", "false"),
        ("localeEn", "EN", "true"),
    ):
        assert re.search(
            rf'<button id="{button_id}"[^>]*aria-pressed="{pressed}"[^>]*>{label}</button>',
            page,
        )

    reduced_motion = re.search(
        r"@media \(prefers-reduced-motion: reduce\)\s*\{(?P<body>.*?)\n\s*\}",
        style,
        re.DOTALL,
    )
    assert reduced_motion is not None
    assert ".progress-scan { animation: none;" in reduced_motion.group("body")
    assert ".sr-only" in style
    assert ".busy #drop { pointer-events: none; }" not in style
    assert 'workspace.setAttribute("aria-busy", "true")' in script
    assert 'workspace.setAttribute("aria-busy", "false")' in script
    assert "progressOwner === bootProgressOwner" in script
    assert 'id="elapsed" aria-hidden="true"' in script
    assert "statusLive.textContent" in script
    assert "}, 4000);" in script


def test_success_reveal_locks_on_without_forcing_motion(running_server):
    """A recovered code gets a visible finish while reduced-motion users get a static state."""
    host, port = running_server
    connection = http.client.HTTPConnection(host, port, timeout=10)

    connection.request("GET", "/")
    page = connection.getresponse().read().decode("utf-8")
    connection.request("GET", "/style.css")
    style = connection.getresponse().read().decode("utf-8")
    connection.request("GET", "/app.js")
    script = connection.getresponse().read().decode("utf-8")

    assert '<div id="photoStage" class="photo-stage" data-companion-anchor="canvas">' in page
    assert '<div id="successLock" class="success-lock" aria-hidden="true">' in page
    assert style.count(".lock-corner") >= 4
    assert "@keyframes success-lock" in style
    assert ".success-reveal #verdict" in style

    reduced_motion = re.search(
        r"@media \(prefers-reduced-motion: reduce\)\s*\{(?P<body>.*?)\n\s*\}",
        style,
        re.DOTALL,
    )
    assert reduced_motion is not None
    assert ".photo-stage.locked .success-lock { animation: none; opacity: 1; }" in (
        reduced_motion.group("body")
    )
    assert ".photo-stage.locked .lock-corner { opacity: 1; }" in reduced_motion.group("body")
    assert "celebrateRecovery();" in script
    assert "const grid = liveGrid || settledGrid;" in script
    solve = script[script.index("async function solve") : script.index("/* --- the live view")]
    catalog = script[
        script.index("async function catalogRun") : script.index("function catalogRender")
    ]
    assert "prepareRecoveryVisuals();" in solve
    assert "prepareRecoveryVisuals();" in catalog
    assert "liveEnd(false);" in solve
    assert "liveEnd(answer.ok);" in solve


def test_async_input_work_cannot_outlive_its_progress_owner():
    """Resetting while a browser promise resolves must not resurrect stale photographs."""
    script = (ROOT / "src" / "qrsalvage" / "web" / "app.js").read_text(encoding="utf-8")

    camera = script[
        script.index("async function openCamera") : script.index("function closeCamera")
    ]
    capture = script[script.index("async function captureBurst") : script.index("for (const radio")]
    selection = script[script.index("async function addFiles") : script.index("function resetAll")]
    reset = script[script.index("function resetAll") : script.index("function refresh")]

    assert "stream = await navigator.mediaDevices.getUserMedia" in camera
    assert "if (progressOwner !== owner)" in camera
    assert "for (const track of stream.getTracks()) track.stop()" in camera

    assert capture.index('const owner = Symbol("capture")') < capture.index(
        "await createImageBitmap"
    )
    assert "releaseBitmaps(frames)" in capture
    assert capture.count("progressOwner !== owner") >= 2
    assert 'document.body.classList.contains("busy")' in capture
    assert 'document.body.classList.add("busy")' in capture
    assert "catch (err)" in capture
    assert "finally" in capture
    assert "$(" + '"cameraClose"' + ').addEventListener("click", cancelCapture)' in script

    assert "const accepted = []" in selection
    assert 'if (document.body.classList.contains("busy")) return' in selection
    assert 'document.body.classList.add("busy")' in selection
    assert 'document.body.classList.remove("busy")' in selection
    assert "loaded.push(...accepted)" in selection
    assert "releaseBitmaps(accepted)" in selection
    assert selection.count("progressOwner !== owner") >= 2
    assert "lastSolved = false" in reset


def test_browser_direct_reader_is_bounded_and_checks_each_photograph():
    worker = (ROOT / "src" / "qrsalvage" / "web" / "worker.js").read_text(encoding="utf-8")

    assert "const MAX_DIRECT_PIXELS = 16_000_000" in worker
    assert "bitmap.width * bitmap.height > MAX_DIRECT_PIXELS" in worker
    assert "targetWidth * targetHeight > MAX_DIRECT_PIXELS" in worker
    assert "for (const entry of encoded)" in worker


def test_every_figure_the_method_page_asks_for_is_served(running_server):
    """A missing figure is invisible from the outside: the page still renders, just emptier.

    The alt text carries the argument for readers who cannot see the picture, so a silently
    broken image loses the statement as well as the illustration.
    """
    host, port = running_server
    connection = http.client.HTTPConnection(host, port, timeout=10)

    connection.request("GET", "/method")
    page = connection.getresponse().read().decode("utf-8")
    # References are relative so that one build serves from a root, a subpath or a filesystem.
    # From /method the browser resolves them against the root, which is what this asks for.
    referenced = re.findall(r'<img src="([^":]+)"', page)
    assert referenced, "the method page references no figures at all"

    for path in referenced:
        connection.request("GET", "/" + path.lstrip("/"))
        response = connection.getresponse()
        body = response.read()
        assert response.status == 200, f"{path} is referenced but not served"
        assert body, f"{path} is served empty"

    # Inside a <figure> the alt text is not decoration, it is the only version of the picture a
    # screen reader gets, so it has to carry the argument. Elsewhere -- the header axolotl --
    # an empty alt is the correct answer and this must not push anyone into writing "logo".
    figures = re.findall(r"<figure>.*?</figure>", page, re.S)
    assert len(figures) >= 6, f"only {len(figures)} figures on the method page"
    for figure in figures:
        alt = re.search(r'alt="([^"]*)"', figure)
        assert alt and len(alt.group(1)) > 60, figure[:200]
    connection.close()


def test_it_listens_on_loopback_only(running_server):
    """A damaged code's payload is frequently a secret. The socket must not be reachable."""
    host, _ = running_server
    assert host == "127.0.0.1"


def test_the_catalogue_is_built_from_titles_and_texts_alone():
    """Stateless: the page sends what it knows, the server re-encodes and lays out.

    No token, no cache: a catalogue can span more recoveries than the export cache holds, and
    the entries survive a server restart because there is nothing to survive.
    """
    body, content_type, filename = catalog_payload(
        {
            "entries": [
                {"title": "LED Lampe Badezimmer", "text": "CATALOG-A-0001", "ecc": "L"},
                {"title": "Heizung Keller", "text": "CATALOG-B-0002"},
                {"title": "", "text": "CATALOG-C-0003"},
                {"title": "leer", "text": "   "},
            ],
            "size_mm": 45,
        }
    )
    assert body.startswith(b"%PDF-")
    assert content_type == "application/pdf"
    assert filename == "catalog.pdf"
    assert b"(LED Lampe Badezimmer)" in body
    assert b"(untitled)" in body, "an empty title falls back rather than vanishing"
    assert b"CATALOG-C-0003" in body
    assert body.count(b"/Type /Page ") == 1, "three usable entries fit one page"


def test_the_catalogue_refuses_nothing_and_nonsense_sizes():
    with pytest.raises(ValueError):
        catalog_payload({"entries": [{"title": "x", "text": "  "}]})
    with pytest.raises(ValueError):
        catalog_payload({"entries": [{"title": "x", "text": "OK"}], "size_mm": 400})


def test_the_solve_can_stream_its_progress(running_server):
    """Newline-delimited JSON: the recovery narrated live, the result as the last line."""
    host, port = running_server
    connection = http.client.HTTPConnection(host, port, timeout=120)
    body = json.dumps({"image": _data_url(FIXTURE), "stream": True})
    connection.request(
        "POST", "/api/solve", body=body, headers={"Content-Type": "application/json"}
    )
    response = connection.getresponse()
    assert response.status == 200
    assert response.getheader("Content-Type", "").startswith("application/x-ndjson")

    lines = [json.loads(line) for line in response.read().splitlines() if line.strip()]
    connection.close()

    assert len(lines) > 5, "a recovery has more steps than that"
    assert lines[-1]["type"] == "result"
    assert lines[-1]["ok"] is True
    kinds = {line["type"] for line in lines}
    assert {"image", "finders", "grid", "sampled"} <= kinds
    # Coordinates in the events land on the photograph the page shows.
    grid = next(line for line in lines if line["type"] == "grid")
    assert all(0 <= x <= 4000 and 0 <= y <= 4000 for x, y in grid["corners"])


def test_a_foreign_host_header_is_refused(running_server):
    """DNS rebinding is the one road a hostile page has to a loopback server.

    The socket only listens on 127.0.0.1, and CORS never fires because the browser believes
    the attacker's rebound domain IS this origin. What survives the rebinding is the Host
    header, so the server refuses anything that does not name the loopback."""
    host, port = running_server
    connection = http.client.HTTPConnection(host, port, timeout=10)

    connection.request("GET", "/", headers={"Host": "attacker.example"})
    assert connection.getresponse().status == 403

    connection.request(
        "POST",
        "/api/solve",
        body=json.dumps({"image": "data:,x"}),
        headers={"Host": "attacker.example:8765", "Content-Type": "application/json"},
    )
    assert connection.getresponse().status == 403

    # The loopback names keep working, with and without a port.
    connection.request("GET", "/", headers={"Host": f"localhost:{port}"})
    assert connection.getresponse().status == 200
    connection.close()


def test_a_cross_origin_post_is_refused(running_server):
    """The attack the Host check cannot see, and the callers that must not be caught with it.

    Rebinding is not needed to reach a loopback server: a page on any origin can post straight
    at it, and the browser writes the Host header itself, so the check above sees exactly what
    it wants to see. What the page cannot write is the browser's own account of where the
    request came from -- and a caller that sends no such account is not a browser at all."""
    host, port = running_server
    body = json.dumps({"image": "data:,x"})

    for headers in (
        {"Origin": "https://evil.example"},
        {"Sec-Fetch-Site": "cross-site"},
        {"Origin": f"http://127.0.0.1:{port}", "Sec-Fetch-Site": "cross-site"},
    ):
        connection = http.client.HTTPConnection(host, port, timeout=10)
        connection.request(
            "POST", "/api/solve", body=body, headers={"Content-Type": "application/json", **headers}
        )
        assert connection.getresponse().status == 403, headers
        connection.close()

    # The page's own fetch, and curl or the CLI, which never had an Origin to send. Both reach
    # the recovery -- "data:,x" is simply not an image, which is a different answer entirely.
    for headers in (
        {"Origin": f"http://localhost:{port}", "Sec-Fetch-Site": "same-origin"},
        {},
    ):
        connection = http.client.HTTPConnection(host, port, timeout=10)
        connection.request(
            "POST", "/api/solve", body=body, headers={"Content-Type": "application/json", **headers}
        )
        response = connection.getresponse()
        assert response.status == 200, headers
        assert json.loads(response.read())["ok"] is False
        connection.close()


def test_the_caller_cannot_name_its_own_workload():
    """Every number the caller chooses is bounded, and the ones that are not numbers say so.

    These all used to travel straight into the recovery: a burst of any length, a frame of any
    size, a budget of any magnitude, and finder points that were neither three nor finite.
    NaN in particular survives every comparison the geometry makes, so it produced a grid that
    was neither placed nor refused."""
    one = _data_url(FIXTURE)

    assert solve_payload({"images": [one] * 13})["failure"].startswith("at most 12")
    assert solve_payload({})["failure"] == "no photograph was given"

    for points, expected in (
        ([{"x": 1, "y": 2}], "three finder points"),
        ([{"x": 1, "y": 2}] * 4, "three finder points"),
        ([{"x": "a", "y": 2}] * 3, "needs a numeric"),
        ([{"x": float("nan"), "y": 2.0}] * 3, "finite"),
        ([{"x": float("inf"), "y": 2.0}] * 3, "finite"),
    ):
        answer = solve_payload({"image": one, "finder_points": points})
        assert answer["ok"] is False
        assert expected in answer["failure"], points

    assert solve_payload({"image": one, "budget": "lots"})["failure"] == "budget must be a number"


def test_a_malformed_request_costs_an_answer_but_never_a_thread(running_server):
    """Two bodies that decode fine and then fall over on the way in.

    Both used to raise outside every handler in do_POST: a Content-Length that is not a number
    at the int(), and a JSON body that is not an object at the first .get(). The handler runs
    on a worker thread whose log_message is stubbed out, so the traceback went nowhere and the
    caller waited on a connection nobody was still holding. What each one must cost now is one
    refusal -- and the server must still be answering afterwards."""
    host, port = running_server

    connection = http.client.HTTPConnection(host, port, timeout=10)
    connection.putrequest("POST", "/api/solve")
    connection.putheader("Content-Type", "application/json")
    connection.putheader("Content-Length", "not-a-number")
    connection.endheaders()
    assert connection.getresponse().status == 400
    connection.close()

    for body in ("[1, 2]", '"a string"', "17"):
        connection = http.client.HTTPConnection(host, port, timeout=10)
        connection.request(
            "POST", "/api/solve", body=body, headers={"Content-Type": "application/json"}
        )
        response = connection.getresponse()
        assert response.status == 200
        assert json.loads(response.read())["ok"] is False
        connection.close()

    # The point of all of the above: the server is still there.
    connection = http.client.HTTPConnection(host, port, timeout=10)
    connection.request("GET", "/")
    assert connection.getresponse().status == 200
    connection.close()


def test_the_page_ships_hardened_headers(running_server):
    """No sniffing, no framing, no referrer -- and no inline script to allow at all."""
    host, port = running_server
    connection = http.client.HTTPConnection(host, port, timeout=10)
    connection.request("GET", "/")
    response = connection.getresponse()
    body = response.read()
    policy = response.getheader("Content-Security-Policy", "")
    assert response.getheader("X-Content-Type-Options") == "nosniff"
    assert response.getheader("Referrer-Policy") == "no-referrer"
    assert "frame-ancestors 'none'" in policy
    assert "'unsafe-inline'" not in policy.split("style-src")[0], (
        "scripts must never be allowed by blanket"
    )

    # The page carries no inline script at all -- its script is an external file under
    # script-src 'self'. That is the strongest position: nothing to hash, nothing an injected
    # <script> tag could ever satisfy. (The hash machinery in the server still exists for any
    # HTML that does carry an inline script, and it once cost a page its life to a CRLF-vs-LF
    # mismatch: the browser hashes after the parser normalises line endings.)
    import re as regex

    assert not regex.findall(rb"<script>", body), "the page grew an inline script"
    assert b'<script src="app.js">' in body

    # The page speaks to whichever backend.js is in place and never learns which one it got.
    # It has to be loaded first: app.js reads window.qrBackend while it is being parsed.
    assert b'<script src="backend.js">' in body
    assert body.index(b'<script src="backend.js">') < body.index(b'<script src="app.js">'), (
        "backend.js must be in place before app.js runs"
    )

    # Every reference is relative, which is what lets one build serve from a domain root, from
    # a project subpath and off a filesystem. A leading slash would work here and break there,
    # which is the kind of difference that is only ever discovered after publishing.
    for absolute in (rb'src="/', rb'href="/'):
        assert absolute not in body, f"the page grew a root-relative reference: {absolute!r}"

    served = {}
    for script in ("/app.js", "/backend.js"):
        connection.request("GET", script)
        response = connection.getresponse()
        served[script] = response.read()
        assert response.status == 200, script
        assert response.getheader("Content-Type", "").startswith("text/javascript"), script
        assert b"use strict" in served[script], script

    # This server hands out the HTTP backend; the worker one belongs to the static build, and
    # its worker.js is not served here at all.
    assert b"/api/solve" in served["/backend.js"]
    connection.request("GET", "/worker.js")
    assert connection.getresponse().status == 404

    # API answers and figures carry a policy that allows nothing at all.
    connection.request("GET", "/fig-known.svg")
    assert connection.getresponse().getheader("Content-Security-Policy") == "default-src 'none'"
    connection.close()
