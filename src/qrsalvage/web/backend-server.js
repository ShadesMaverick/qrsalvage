/* Where the page sends its work: the local Python server, over HTTP on the loopback.
 *
 * One of two files that can occupy this slot. The other is backend-worker.js, which runs the
 * identical Python inside the browser; the local server copies this one into place and the
 * static build copies that one, so the page itself never learns which world it is in. Both
 * expose exactly the interface below, and both return the answers of qrsalvage.api unchanged
 * -- the same dictionaries, the same progress events, the same export bytes.
 *
 *   qrBackend.modeKey        locale key naming where recovery runs
 *   qrBackend.privacyKey     locale key saying "this stayed with you" truthfully
 *   qrBackend.failurePrefixKey  locale key introducing a failure that is the backend's fault
 *   qrBackend.ready          a promise that resolves once recovering is possible
 *   qrBackend.onBoot(fn)     progress while that promise is pending (here: nothing to report)
 *   qrBackend.solve(payload, onEvent)  -> the answer of api.solve_payload; onEvent per event
 *   qrBackend.file(kind, payload)      -> {blob, filename} from api.export_payload/catalog
 */

"use strict";

window.qrBackend = {
  modeKey: "backend.mode.server",
  privacyKey: "privacy.server",
  failurePrefixKey: "backend.failure.server",
  ready: Promise.resolve(),
  onBoot() {},

  async solve(payload, onEvent) {
    const response = await fetch("/api/solve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...payload, stream: true }),
    });
    if (!response.ok) {
      let reason = `${response.status}`;
      try {
        const body = await response.text();
        reason = JSON.parse(body).failure || reason;
      } catch {
        /* an empty or non-JSON response still has a useful HTTP status */
      }
      throw new Error(reason);
    }
    if (!response.body) throw new Error("the local server returned no response body");
    // Newline-delimited JSON: every line but the last is a step of the actual recovery — the
    // grid snapping into place, the versions competing, the probe counting. The last line is
    // the result.
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let answer = null;
    const consume = (line) => {
      const trimmed = line.trim();
      if (!trimmed) return;
      const event = JSON.parse(trimmed);
      if (event.type === "result") answer = event;
      else onEvent(event);
    };
    for (;;) {
      const { done, value } = await reader.read();
      if (done) {
        buffer += decoder.decode();
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      let cut;
      while ((cut = buffer.indexOf("\n")) >= 0) {
        const line = buffer.slice(0, cut);
        buffer = buffer.slice(cut + 1);
        consume(line);
      }
    }
    consume(buffer);
    if (!answer) throw new Error("the local server returned no result");
    return answer;
  },

  async file(kind, payload) {
    const response = await fetch(`/api/${kind}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      let reason = `${response.status}`;
      try {
        reason = (await response.json()).failure || reason;
      } catch {
        /* the body was not JSON; the status is all there is to say */
      }
      throw new Error(reason);
    }
    const disposition = response.headers.get("Content-Disposition") || "";
    const named = disposition.match(/filename="([^"]+)"/);
    return { blob: await response.blob(), filename: named ? named[1] : null };
  },
};
