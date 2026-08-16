/* The recovery, off the main thread — and without JSPI.
 *
 * Two findings shape this file. First, the whole Pyodide runtime lives happily in a module
 * worker, so the page stays responsive while the core computes. Second, zxing-wasm's async
 * surface is only about module readiness: underneath sits a synchronous embind call,
 * readBarcodesFromPixmap(heapPointer, width, height, options). One warmed-up wrapper call
 * captures the fully-defaulted options object, and from then on every decode is a plain
 * synchronous function — the synchronous Python core calls it directly, no JSPI, no
 * stack-switching, nothing Safari lacks by design.
 */

import { loadPyodide } from "https://cdn.jsdelivr.net/pyodide/v0.28.0/full/pyodide.mjs";
import * as zxing from "https://cdn.jsdelivr.net/npm/zxing-wasm@2/full/+esm";

const post = (type, data = {}) => self.postMessage({ type, ...data });
const stamp = (label, t0) =>
  post("stage", { label, seconds: Math.round((performance.now() - t0) / 100) / 10 });

try {
  // --- the oracle, armed for synchronous use --------------------------------------------
  let t = performance.now();
  const mod = await zxing.prepareZXingModule({ fireImmediately: true });

  // One wrapper call with a written-and-read roundtrip captures the embind options object
  // with every default filled in; embind rejects partial objects, and building one by hand
  // would chase the wrapper's defaults forever.
  let capturedOptions = null;
  const original = mod.readBarcodesFromPixmap;
  mod.readBarcodesFromPixmap = function (...args) {
    capturedOptions = args[3];
    return original.apply(this, args);
  };
  const warm = await zxing.writeBarcode("WARMUP", { format: "QRCode" });
  const bitmap = await createImageBitmap(warm.image);
  const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
  const context = canvas.getContext("2d");
  context.drawImage(bitmap, 0, 0);
  await zxing.readBarcodes(context.getImageData(0, 0, bitmap.width, bitmap.height), {
    formats: ["QRCode"],
    tryInvert: false,
  });
  mod.readBarcodesFromPixmap = original;
  if (!capturedOptions) throw new Error("could not capture the reader options");
  stamp("zxing-cpp WASM ready, sync oracle armed", t);

  self.zxDecodeSync = (rgbaBytes, width, height) => {
    const pointer = mod._malloc(rgbaBytes.length);
    mod.HEAPU8.set(rgbaBytes, pointer);
    const results = mod.readBarcodesFromPixmap(pointer, width, height, capturedOptions);
    mod._free(pointer);
    return results.size() > 0 ? results.get(0).text : null;
  };

  // --- CPython, numpy, OpenCV, the pure wheel -------------------------------------------
  t = performance.now();
  const pyodide = await loadPyodide();
  stamp("pyodide (CPython) ready", t);

  t = performance.now();
  await pyodide.loadPackage(["numpy", "opencv-python"]);
  stamp("numpy + opencv loaded", t);

  t = performance.now();
  const wheel = await (await fetch("/dist/qrsalvage-0.1.0-py3-none-any.whl")).arrayBuffer();
  pyodide.unpackArchive(wheel, "wheel");
  const fixture = new Uint8Array(
    await (await fetch("/fixtures/engraved-curved-hard.png")).arrayBuffer()
  );
  pyodide.FS.writeFile("/fixture.png", fixture);
  stamp("qrsalvage wheel + fixture in place", t);

  // Progress events flow to the page as they happen — the live view, worker edition.
  self.reportProgress = (event) => post("progress", { event });

  // --- solve ----------------------------------------------------------------------------
  t = performance.now();
  await pyodide.runPythonAsync(`
import json
import time

import cv2
import js
import numpy as np
from pyodide.ffi import to_js

from qrsalvage.core import oracle


def wasm_decode(gray):
    height, width = gray.shape
    rgba = np.dstack([gray, gray, gray, np.full_like(gray, 255)])
    return js.zxDecodeSync(to_js(rgba.tobytes()), width, height)


def no_encode(text, ec_level):
    raise NotImplementedError("the spike bridges the decode direction only")


oracle.use(wasm_decode, no_encode)

from qrsalvage.core.pipeline import solve

image = cv2.imread("/fixture.png")
started = time.perf_counter()
result = solve(image, progress=lambda event, data: js.reportProgress(event))
elapsed = time.perf_counter() - started

report = json.dumps({
    "solved": result.solved,
    "text": result.text,
    "version": result.version,
    "wrong_known": result.wrong_known,
    "known_total": result.known_total,
    "attempts": result.candidates_tried,
    "seconds": round(elapsed, 1),
})
`);
  const report = JSON.parse(pyodide.globals.get("report"));
  post("result", { report });
} catch (error) {
  post("error", { message: String(error) });
}
