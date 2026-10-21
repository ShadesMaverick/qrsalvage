(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.qrStudioState = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const PHASE_FOR_EVENT = Object.freeze({
    RESET: "welcome",
    IMAGES_READY: "ready",
    PREPARING: "preparing",
    RECOVERY_STARTED: "recovering",
    ASSISTANCE_REQUIRED: "assistance",
    RECOVERY_SUCCEEDED: "success",
    RECOVERY_FAILED: "failure",
  });

  function normalizeMode(value) {
    return value === "pro" ? "pro" : "easy";
  }

  function createStudioState(mode) {
    return { phase: "welcome", mode: normalizeMode(mode) };
  }

  function reduceStudioState(state, event) {
    if (event.type === "SET_MODE") return { ...state, mode: normalizeMode(event.mode) };
    const phase = PHASE_FOR_EVENT[event.type];
    return phase ? { ...state, phase } : state;
  }

  function viewForState(state) {
    const mode = normalizeMode(state.mode);
    return {
      phaseClass: `studio-phase-${state.phase}`,
      modeClass: `studio-mode-${mode}`,
      diagnosticsExpanded: mode === "pro",
      manualToolsExpanded: mode === "pro",
    };
  }

  return { createStudioState, reduceStudioState, viewForState };
});
