/* The recovery itself, in the browser, off the main thread.
 *
 * This worker is the third shell over the core -- after the command line and the local server
 * -- and it is deliberately the thinnest of the three. It boots CPython on WebAssembly, hands
 * the core an oracle compiled to WASM, and then calls qrsalvage.api, the very same functions
 * the local server calls. Nothing about a recovery is reimplemented here. That is what keeps
 * the browser answer identical to the command-line answer instead of merely similar.
 *
 * Two things had to be true for this to work without JSPI, and both were measured in
 * spike/pyodide before anything was built on them:
 *
 *   - Decoding: zxing-wasm's async surface is only about module readiness. Underneath sits a
 *     synchronous embind call, readBarcodesFromPixmap(pointer, width, height, options). One
 *     warmed-up wrapper call captures the fully-defaulted options object -- embind rejects
 *     partial ones -- and every decode after that is a plain synchronous call.
 *   - Encoding: writeBarcodeFromText(text, options) is synchronous already. It answers with a
 *     symbol of one byte per module, and that symbol always carries the four-module quiet
 *     zone regardless of withQuietZones, so the bridge strips the light border rather than
 *     trusting a flag. Every solved recovery re-encodes its text and the whole A4 catalogue is
 *     re-encoded from text, so without this direction the browser build would be a reader
 *     only.
 *
 * Because neither direction needs stack switching, nothing in this path depends on JSPI -- the
 * one feature Safari lacks by design. The page stays responsive throughout: the recovery runs
 * here, not on the main thread.
 */

// Where the runtime comes from. The production build vendors everything next to the page and
// passes nothing; the query parameter exists so a developer can point at a different local
// layout while working.
//
// It is confined to this origin on purpose, and that is a deliberate loss: it used to accept
// any absolute http(s) URL, which made "point at a CDN" a link away. This worker imports and
// runs whatever it finds at that address, and it is also the half of the page that holds the
// photograph -- so an origin a stranger can name in a query string is the one place the
// runtime must not come from. A developer who wants a different build serves it from here.
const params = new URLSearchParams(self.location.search);
const VENDORED = new URL("./vendor/", self.location.href);
const requested = new URL(params.get("assets") || "./vendor/", self.location.href);
const sameOrigin = requested.origin === self.location.origin;
if (!sameOrigin) {
  console.warn(
    `qrsalvage: the assets parameter points at ${requested.origin}; using the vendored runtime instead`,
  );
}
const PYODIDE = (sameOrigin ? requested : VENDORED).href;

const post = (message) => self.postMessage(message);
const boot = (stage, since) =>
  post({ type: "boot", stage, seconds: Math.round((performance.now() - since) / 100) / 10 });
// The shared API accepts larger photographs, but duplicating one into canvases for speculative
// aspect-ratio correction would multiply its memory. Larger frames skip this cheap preflight and
// continue through the normal recovery path without another full-size RGBA allocation.
const MAX_DIRECT_PIXELS = 16_000_000;

let pyodide = null;
let handleJson = null;
let handleFile = null;

/** Arm both directions of the oracle as synchronous calls, and expose them to Python. */
async function armOracle(zxing) {
  const mod = await zxing.prepareZXingModule({ fireImmediately: true });

  // Capture the reader's fully-defaulted options object from one wrapper call.
  let readerOptions = null;
  const readOriginal = mod.readBarcodesFromPixmap;
  mod.readBarcodesFromPixmap = function (...args) {
    readerOptions = args[3];
    return readOriginal.apply(this, args);
  };
  // A blank image is enough. Nothing about the warmup's result matters -- the only purpose is
  // to make the wrapper build its options object once so it can be captured. Reading a real
  // barcode here would mean rendering one, which used to cost an OffscreenCanvas and with it
  // Safari 16.4 as the floor for the whole tool; a bare ImageData asks for nothing newer than
  // the module worker already does.
  const blank = new ImageData(new Uint8ClampedArray(32 * 32 * 4), 32, 32);
  // Match the native oracle's explicit options. The wrapper otherwise enables `tryHarder`,
  // rotation and downscaling by default while `readBarcodesFromPixmap` receives whatever this
  // warmup captured; spelling the choices out makes the browser/native contract deliberate.
  await zxing.readBarcodes(blank, {
    formats: ["QRCode"],
    tryHarder: true,
    tryRotate: true,
    tryInvert: false,
    tryDownscale: true,
    maxNumberOfSymbols: 1,
    returnErrors: false,
  });
  mod.readBarcodesFromPixmap = readOriginal;

  // The writer's options object, captured the same way and reused with the level patched in.
  let writerOptions = null;
  const writeOriginal = mod.writeBarcodeFromText;
  mod.writeBarcodeFromText = function (...args) {
    writerOptions = args[1];
    return writeOriginal.apply(this, args);
  };
  await zxing.writeBarcode("WARMUP", { format: "QRCode", ecLevel: "M" });
  mod.writeBarcodeFromText = writeOriginal;

  if (!readerOptions || !writerOptions) throw new Error("could not arm the oracle");

  // Handles that live in the WASM heap are not garbage collected -- embind hands JavaScript a
  // reference and waits to be told when it may go. `delete` is missing on a plain object, so
  // the guard keeps this safe whichever kind of value comes back.
  const release = (handle) => {
    if (handle && typeof handle.delete === "function") handle.delete();
  };

  self.zxDecodeSync = (rgbaBytes, width, height) => {
    const pointer = mod._malloc(rgbaBytes.length);
    mod.HEAPU8.set(rgbaBytes, pointer);
    const results = mod.readBarcodesFromPixmap(pointer, width, height, readerOptions);
    mod._free(pointer);
    // The probe asks this question thousands of times for one photograph -- up to the search
    // budget, four thousand by default. A result vector left behind on each of those is a heap
    // that only grows, and the page dies partway through a recovery with nothing to explain it.
    try {
      if (results.size() === 0) return null;
      const first = results.get(0);
      try {
        return first.isValid && !first.error ? first.text : null;
      } finally {
        release(first);
      }
    } finally {
      release(results);
    }
  };

  // Keep the public wrapper too. The synchronous bridge above is essential for the thousands
  // of matrix probes Python performs inside one solve; a whole uploaded photograph is attempted
  // only once, so the normal wrapper can preserve every reader heuristic exactly as shipped.
  self.zxDecodePhoto = async (rgbaBytes, width, height) => {
    const pixels = new Uint8ClampedArray(rgbaBytes);
    const options = {
      formats: ["QRCode"],
      tryHarder: true,
      tryRotate: true,
      tryInvert: false,
      tryDownscale: true,
      maxNumberOfSymbols: 1,
      returnErrors: false,
    };
    // zxing-cpp native reads the motivating non-square screenshot as-is. The current WASM build
    // does not, but succeeds as soon as the same pixels are normalised toward a square. Trying a
    // small fixed transform set is cheap (one attempt per uploaded photograph) and checksum-safe.
    const attempts = [[width, height]];
    if (width !== height) {
      const side = Math.min(Math.max(width, height), Math.floor(Math.sqrt(MAX_DIRECT_PIXELS)));
      const geometricMean = Math.round(Math.sqrt(width * height));
      attempts.push([side, side], [geometricMean, geometricMean]);
    }
    const source = new OffscreenCanvas(width, height);
    source.getContext("2d").putImageData(new ImageData(pixels, width, height), 0, 0);
    for (const [targetWidth, targetHeight] of attempts) {
      if (targetWidth * targetHeight > MAX_DIRECT_PIXELS) continue;
      try {
        let image;
        if (targetWidth === width && targetHeight === height) {
          image = new ImageData(pixels, width, height);
        } else {
          const canvas = new OffscreenCanvas(targetWidth, targetHeight);
          const context = canvas.getContext("2d");
          context.drawImage(source, 0, 0, targetWidth, targetHeight);
          image = context.getImageData(0, 0, targetWidth, targetHeight);
        }
        const first = (await zxing.readBarcodes(image, options))[0];
        if (first && first.isValid && !first.error && first.text) return first.text;
      } catch {
        // Allocation or one reader attempt failing must fall through to the recovery pipeline.
      }
    }
    return null;
  };

  self.zxEncodeSync = (text, ecLevel) => {
    // An empty level means "the encoder's choice", which is exactly what the core means by a
    // level of None -- so the two vocabularies already agree.
    writerOptions.ecLevel = ecLevel || "";
    const written = writeOriginal.apply(mod, [text, writerOptions]);
    if (written.error) throw new Error(written.error);
    const symbol = written.symbol;
    return { data: symbol.data, width: symbol.width, height: symbol.height };
  };
}

/** The Python side of the bridge: the oracle, and two entry points that speak plain JSON. */
const GLUE = `
import base64
import json

import js
import numpy as np
from pyodide.ffi import to_js

from qrsalvage.core import oracle


def _decode(gray):
    height, width = gray.shape
    rgba = np.dstack([gray, gray, gray, np.full_like(gray, 255)])
    return js.zxDecodeSync(to_js(rgba.tobytes()), width, height)


def _encode(text, ec_level):
    answer = js.zxEncodeSync(text, ec_level or "")
    flat = np.asarray(bytearray(answer.data.to_py()), dtype=np.uint8)
    dark = flat.reshape(answer.height, answer.width) < 128
    # The symbol always carries its quiet zone, so trim the light border. A QR code has a dark
    # module in its first and last row and column -- the three finders sit in the corners -- so
    # this recovers the bare matrix exactly, and would be a no-op if the zone were ever absent.
    rows = np.flatnonzero(dark.any(axis=1))
    cols = np.flatnonzero(dark.any(axis=0))
    return dark[rows[0] : rows[-1] + 1, cols[0] : cols[-1] + 1]


oracle.use(_decode, _encode)

from qrsalvage import api  # noqa: E402 -- the oracle has to be in place first


def _progress(event, data):
    # Serialised here rather than converted, so the events crossing this boundary are byte for
    # byte the ones the server's NDJSON stream sends. One event shape for every shell.
    js.reportProgress(json.dumps({"type": event, **data}))


def handle_json(kind, payload_json, direct_texts_json=None):
    payload = json.loads(payload_json)
    if kind == "solve":
        # JSON is the deliberate JS/Python boundary: a raw JavaScript null becomes Pyodide's
        # JsNull proxy rather than None and would be rejected by the shared API contract.
        direct_texts = json.loads(direct_texts_json) if direct_texts_json is not None else None
        return json.dumps(
            api.solve_payload(payload, progress=_progress, trusted_direct_texts=direct_texts)
        )
    raise ValueError("unknown request: " + kind)


def handle_file(kind, payload_json):
    payload = json.loads(payload_json)
    builder = api.export_payload if kind == "export" else api.catalog_payload
    body, content_type, filename = builder(payload)
    return json.dumps(
        {
            "base64": base64.b64encode(body).decode("ascii"),
            "contentType": content_type,
            "filename": filename,
        }
    )
`;

async function start() {
  // Started here and awaited three steps down. Nothing about fetching the wheel depends on
  // Python existing yet -- only unpacking it does -- so the download rides alongside the WASM
  // that is being fetched and compiled anyway, instead of waiting its turn behind all of it.
  const wheelBytes = fetch(`${PYODIDE}qrsalvage.whl`).then((response) => response.arrayBuffer());

  let t = performance.now();
  const zxing = await import(`${PYODIDE}zxing/index.mjs`);
  await armOracle(zxing);
  boot("oracle ready", t);

  t = performance.now();
  const { loadPyodide } = await import(`${PYODIDE}pyodide/pyodide.mjs`);
  pyodide = await loadPyodide({ indexURL: `${PYODIDE}pyodide/` });
  boot("python ready", t);

  t = performance.now();
  await pyodide.loadPackage(["numpy", "opencv-python"]);
  boot("numpy and opencv ready", t);

  t = performance.now();
  const wheel = await wheelBytes;
  pyodide.unpackArchive(wheel, "wheel");
  self.reportProgress = (line) => post({ type: "progress", line });
  await pyodide.runPythonAsync(GLUE);
  handleJson = pyodide.globals.get("handle_json");
  handleFile = pyodide.globals.get("handle_file");
  boot("qrsalvage ready", t);

  post({ type: "ready" });
}

const booted = start().catch((error) => {
  post({ type: "fatal", message: String(error && error.message ? error.message : error) });
  throw error;
});

self.onmessage = async ({ data }) => {
  const { id, kind, payload } = data;
  try {
    await booted;
    let body = JSON.stringify(payload);
    if (kind === "solve") {
      const encoded = payload.images || (payload.image ? [payload.image] : []);
      const directTexts = [];
      if (!payload.finder_points) {
        for (const entry of encoded) {
          let text = null;
          try {
            const blob = await (await fetch(entry)).blob();
            const bitmap = await createImageBitmap(blob);
            if (bitmap.width * bitmap.height > MAX_DIRECT_PIXELS) {
              bitmap.close();
            } else {
              const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
              const context = canvas.getContext("2d");
              context.drawImage(bitmap, 0, 0);
              bitmap.close();
              const image = context.getImageData(0, 0, canvas.width, canvas.height);
              text = await self.zxDecodePhoto(image.data, image.width, image.height);
            }
          } catch {
            // The shared recovery still gets the original image below.
          }
          directTexts.push(text);
          if (text) break;
        }
      }
      while (directTexts.length < encoded.length) directTexts.push(null);
      post({
        id,
        type: "result",
        result: JSON.parse(handleJson(kind, body, JSON.stringify(directTexts))),
      });
    } else {
      post({ id, type: "file", file: JSON.parse(handleFile(kind, body)) });
    }
  } catch (error) {
    post({ id, type: "error", message: String(error && error.message ? error.message : error) });
  }
};
