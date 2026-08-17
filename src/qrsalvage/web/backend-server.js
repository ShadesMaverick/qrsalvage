/* Where the page sends its work: the local Python server, over HTTP on the loopback.
 *
 * One of two files that can occupy this slot. The other is backend-worker.js, which runs the
 * identical Python inside the browser; the local server copies this one into place and the
 * static build copies that one, so the page itself never learns which world it is in. Both
 * expose exactly the interface below, and both return the answers of qrsalvage.api unchanged
 * -- the same dictionaries, the same progress events, the same export bytes.
 *
 *   qrBackend.mode           a word for the page to show ("local server" / "your browser")
 *   qrBackend.privacyNote    how to say "this stayed with you" truthfully in this mode
 *   qrBackend.failurePrefix  how to introduce a failure that is the backend's fault
 *   qrBackend.ready          a promise that resolves once recovering is possible
 *   qrBackend.onBoot(fn)     progress while that promise is pending (here: nothing to report)
 *   qrBackend.solve(payload, onEvent)  -> the answer of api.solve_payload; onEvent per event
 *   qrBackend.file(kind, payload)      -> {blob, filename} from api.export_payload/catalog
 */

"use strict";

window.qrBackend = {
  mode: "local server",
  privacyNote: "Ran on your own machine — nothing was uploaded.",
  failurePrefix: "the local server did not answer: ",
  ready: Promise.resolve(),
  onBoot() {},

  async solve(payload, onEvent) {
    const response = await fetch("/api/solve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...payload, stream: true }),
    });
    // Newline-delimited JSON: every line but the last is a step of the actual recovery — the
    // grid snapping into place, the versions competing, the probe counting. The last line is
    // the result.
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let answer = null;
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let cut;
      while ((cut = buffer.indexOf("\n")) >= 0) {
        const line = buffer.slice(0, cut).trim();
        buffer = buffer.slice(cut + 1);
        if (!line) continue;
        const event = JSON.parse(line);
        if (event.type === "result") answer = event;
        else onEvent(event);
      }
    }
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
