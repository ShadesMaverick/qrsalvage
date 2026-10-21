/* Pure outline-editing geometry. The browser uses the global; Node uses the same functions
   through CommonJS so interaction rules can be tested without constructing the page DOM. */

"use strict";

(function exposeOutlineEditor(root, factory) {
  const editor = factory();
  if (typeof module === "object" && module.exports) module.exports = editor;
  root.qrOutlineEditor = editor;
})(typeof globalThis === "undefined" ? this : globalThis, () => {
  function selectNearestHandle(point, corners, edgeMidpoints, hitRadius) {
    const candidates = [
      ...corners.map((handle, index) => ({ kind: "corner", index, handle })),
      ...edgeMidpoints.map((handle, index) => ({ kind: "midpoint", index, handle })),
    ].map((candidate) => ({
      ...candidate,
      distance: Math.hypot(
        candidate.handle.x - point.x,
        candidate.handle.y - point.y
      ),
    })).filter((candidate) => candidate.distance <= hitRadius);
    if (!candidates.length) return null;
    const nearest = candidates.reduce((best, candidate) =>
      candidate.distance < best.distance ? candidate : best
    );
    return { kind: nearest.kind, index: nearest.index };
  }

  function moveHandle(corners, edgeMidpoints, handle, delta) {
    const movedCorners = corners.map((point) => ({ ...point }));
    const movedMidpoints = edgeMidpoints.map((point) => ({ ...point }));
    const move = (point, share = 1) => {
      point.x += delta.x * share;
      point.y += delta.y * share;
    };
    if (handle.kind === "corner") {
      move(movedCorners[handle.index]);
      const previousEdge = (handle.index + movedMidpoints.length - 1) % movedMidpoints.length;
      move(movedMidpoints[previousEdge], 0.5);
      move(movedMidpoints[handle.index], 0.5);
    } else {
      move(movedMidpoints[handle.index]);
    }
    return { corners: movedCorners, edgeMidpoints: movedMidpoints };
  }

  function keyboardCommand(key, shiftKey) {
    if (key === "Enter" || key === " ") return { type: "place" };
    const directions = {
      ArrowLeft: [-1, 0],
      ArrowRight: [1, 0],
      ArrowUp: [0, -1],
      ArrowDown: [0, 1],
    };
    if (directions[key]) {
      return {
        type: "move",
        x: directions[key][0],
        y: directions[key][1],
        multiplier: shiftKey ? 5 : 1,
      };
    }
    if (key === "[" || key === "]") {
      return { type: "cycle", direction: key === "]" ? 1 : -1 };
    }
    return null;
  }

  return { selectNearestHandle, moveHandle, keyboardCommand };
});
