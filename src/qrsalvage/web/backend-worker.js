/* Where the page sends its work: a worker in this very browser, running the same Python.
 *
 * The static build ships this file as backend.js; the local server ships backend-server.js.
 * The page cannot tell the difference, because both keep the same promises -- see the
 * interface described at the top of backend-server.js.
 *
 * The honest cost of this mode is the first minute: a Python runtime, NumPy and OpenCV have to
 * arrive before anything can be recovered. That wait is reported rather than hidden, because a
 * page that looks broken for forty seconds is worse than one that says what it is doing. The
 * benefit is the reason this project exists in the first place -- there is no server, so the
 * claim that the photograph never leaves the device is not a policy but an architecture.
 */

"use strict";

window.qrBackend = (() => {
  const worker = new Worker(new URL("./worker.js", document.baseURI), { type: "module" });
  const pending = new Map();
  const bootListeners = [];
  let nextId = 1;
  let settle = null;

  const ready = new Promise((resolve, reject) => {
    settle = { resolve, reject };
  });

  worker.onmessage = ({ data }) => {
    if (data.type === "boot") {
      bootListeners.forEach((fn) => fn(data));
      return;
    }
    if (data.type === "ready") {
      bootListeners.forEach((fn) => fn({ stage: "ready", done: true }));
      settle.resolve();
      return;
    }
    if (data.type === "fatal") {
      const error = new Error(data.message);
      settle.reject(error);
      pending.forEach((entry) => entry.reject(error));
      pending.clear();
      return;
    }
    if (data.type === "progress") {
      // The worker forwards the core's events as the JSON lines the server would have sent,
      // so the live view consumes them without knowing which shell produced them.
      const entry = pending.get(data.id) || pending.values().next().value;
      if (entry) entry.onEvent(JSON.parse(data.line));
      return;
    }
    const entry = pending.get(data.id);
    if (!entry) return;
    pending.delete(data.id);
    if (data.type === "error") entry.reject(new Error(data.message));
    else if (data.type === "result") entry.resolve(data.result);
    else entry.resolve(data.file);
  };

  worker.onerror = (event) => {
    const error = new Error(event.message || "the recovery engine stopped");
    settle.reject(error);
    pending.forEach((entry) => entry.reject(error));
    pending.clear();
  };

  const send = (kind, payload, onEvent) =>
    new Promise((resolve, reject) => {
      const id = nextId++;
      pending.set(id, { resolve, reject, onEvent: onEvent || (() => {}) });
      worker.postMessage({ id, kind, payload });
    });

  return {
    modeKey: "backend.mode.browser",
    privacyKey: "privacy.browser",
    failurePrefixKey: "backend.failure.browser",
    ready,
    onBoot(fn) {
      bootListeners.push(fn);
    },

    solve(payload, onEvent) {
      return send("solve", payload, onEvent);
    },

    async file(kind, payload) {
      const answer = await send(kind, payload);
      // Bytes cross the worker boundary base64-encoded: small next to the photographs already
      // in play, and immune to the conversion surprises of typed arrays through Pyodide.
      const binary = atob(answer.base64);
      // One engine-level pass rather than a JavaScript loop per character. An HTML report
      // carries the photograph inside it, so this string runs to megabytes, and this runs on
      // the thread that draws the page.
      const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
      return {
        blob: new Blob([bytes], { type: answer.contentType }),
        filename: answer.filename,
      };
    },
  };
})();
