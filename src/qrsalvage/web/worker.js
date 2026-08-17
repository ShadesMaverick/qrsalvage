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
// passes nothing; the query parameter exists so a developer can point at a CDN while working.
const params = new URLSearchParams(self.location.search);
const ASSETS = params.get("assets") || "./vendor/";
const PYODIDE = ASSETS.startsWith("http") ? ASSETS : new URL(ASSETS, self.location.href).href;

const post = (message) => self.postMessage(message);
const boot = (stage, since) =>
  post({ type: "boot", stage, seconds: Math.round((performance.now() - since) / 100) / 10 });

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
  const warm = await zxing.writeBarcode("WARMUP", { format: "QRCode" });
  const bitmap = await createImageBitmap(warm.image);
  const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
  canvas.getContext("2d").drawImage(bitmap, 0, 0);
  await zxing.readBarcodes(canvas.getContext("2d").getImageData(0, 0, bitmap.width, bitmap.height), {
    formats: ["QRCode"],
    tryInvert: false,
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

  self.zxDecodeSync = (rgbaBytes, width, height) => {
    const pointer = mod._malloc(rgbaBytes.length);
    mod.HEAPU8.set(rgbaBytes, pointer);
    const results = mod.readBarcodesFromPixmap(pointer, width, height, readerOptions);
    mod._free(pointer);
    return results.size() > 0 ? results.get(0).text : null;
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


def handle_json(kind, payload_json):
    payload = json.loads(payload_json)
    if kind == "solve":
        return json.dumps(api.solve_payload(payload, progress=_progress))
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
  const wheel = await (await fetch(`${PYODIDE}qrsalvage.whl`)).arrayBuffer();
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
    const body = JSON.stringify(payload);
    if (kind === "solve") {
      post({ id, type: "result", result: JSON.parse(handleJson(kind, body)) });
    } else {
      post({ id, type: "file", file: JSON.parse(handleFile(kind, body)) });
    }
  } catch (error) {
    post({ id, type: "error", message: String(error && error.message ? error.message : error) });
  }
};
