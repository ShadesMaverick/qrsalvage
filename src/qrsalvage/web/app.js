/* The interface's single script. Split from index.html for one reason only: a
   1200-line file was the largest mental hurdle in the repository. Still no build
   step -- three static files instead of one, served as they are. An external file
   also lets the Content-Security-Policy say script-src 'self' with no inline-hash
   machinery behind it. */

"use strict";
const $ = (id) => document.getElementById(id);
const t = (key, values) => window.qrLocale.t(key, values);

// These two consumers select keys from runtime state rather than spelling them inside t().
// Keep the complete finite sets here so the locale-consumer test can validate every key.
// DYNAMIC-LOCALE-CONSUMERS: START
const DYNAMIC_LOCALE_KEYS = Object.freeze({
  outlineCorners: Object.freeze([
    "manual.topLeft", "manual.topRight", "manual.bottomRight", "manual.bottomLeft",
  ]),
  recoveryStages: Object.freeze({
    image: "recovery.stage.image",
    finders: "recovery.stage.finders",
    polarity: "recovery.stage.polarity",
    grid: "recovery.stage.grid",
    chosen: "recovery.stage.chosen",
    sampled: "recovery.stage.sampled",
    repair: "recovery.stage.repair",
    probe: "recovery.stage.probe",
    member: "recovery.stage.member",
    fusion: "recovery.stage.fusion",
  }),
});
// DYNAMIC-LOCALE-CONSUMERS: END

function readPreference(key) {
  try { return window.localStorage.getItem(key); } catch { return null; }
}

function writePreference(key, value) {
  try { window.localStorage.setItem(key, value); } catch { /* presentation state stays in memory */ }
}

let studioState = window.qrStudioState.createStudioState(readPreference("qrsalvage.mode"));
let disclosureMode = null;
const companionDetail = { assistance: null, payloadReady: false };

function guardedStorage(name) {
  let storage = null;
  const memory = new Map();
  try { storage = window[name]; } catch { /* private browsing may refuse the storage object */ }
  return {
    get(key) {
      if (memory.has(key)) return memory.get(key);
      try { return storage ? storage.getItem(key) : null; }
      catch { storage = null; return null; }
    },
    set(key, value) {
      memory.set(key, value);
      try { if (storage) storage.setItem(key, value); }
      catch { storage = null; /* the in-memory preference remains authoritative */ }
    },
  };
}

const companionLocal = guardedStorage("localStorage");
const companionSession = guardedStorage("sessionStorage");
const companionMedia = window.matchMedia("(prefers-reduced-motion: reduce)");
const companionAnchors = Object.fromEntries(
  [...document.querySelectorAll("[data-companion-anchor]")]
    .map((element) => [element.dataset.companionAnchor, element]),
);
const companion = window.qrCompanion.createCompanionController({
  root: $("companion"),
  bubble: $("companionBubble"),
  anchors: companionAnchors,
  t,
  local: companionLocal,
  session: companionSession,
  media: companionMedia,
});
const motionToggle = $("motionToggle");

function syncCompanionControl(decision) {
  motionToggle.setAttribute("aria-pressed", String(decision.motion === "still"));
}

function setDisclosure(id, expanded) {
  const details = $(id);
  details.open = expanded;
  const summary = details.querySelector("summary");
  if (summary) summary.setAttribute("aria-expanded", String(expanded));
}

function dispatchStudio(event) {
  studioState = window.qrStudioState.reduceStudioState(studioState, event);
  const view = window.qrStudioState.viewForState(studioState);
  if (studioState.phase !== "success") companionDetail.payloadReady = false;
  if (studioState.phase !== "assistance") companionDetail.assistance = null;
  const shell = $("studioShell");
  shell.className = `${view.phaseClass} ${view.modeClass}`;
  $("modeEasy").setAttribute("aria-pressed", String(studioState.mode === "easy"));
  $("modePro").setAttribute("aria-pressed", String(studioState.mode === "pro"));
  if (disclosureMode !== studioState.mode) {
    setDisclosure("diagnosticsDetails", view.diagnosticsExpanded);
    setDisclosure("advancedExport", view.diagnosticsExpanded);
    setDisclosure("matrixDetails", view.diagnosticsExpanded);
    disclosureMode = studioState.mode;
  }
  syncManualTools(view.manualToolsExpanded);
  syncCompanionControl(companion.update({ ...studioState, ...companionDetail }));
}

window.dispatchStudio = dispatchStudio;

for (const [id, modeName] of [["modeEasy", "easy"], ["modePro", "pro"]]) {
  $(id).addEventListener("click", () => {
    writePreference("qrsalvage.mode", modeName);
    dispatchStudio({ type: "SET_MODE", mode: modeName });
  });
}

motionToggle.addEventListener("click", () => {
  const next = companionLocal.get("qrsalvage.motionReduced") !== "true";
  companionLocal.set("qrsalvage.motionReduced", String(next));
  syncCompanionControl(companion.update({ ...studioState, ...companionDetail }));
});

companionMedia.addEventListener("change", () => {
  syncCompanionControl(companion.update({ ...studioState, ...companionDetail }));
});

for (const id of ["diagnosticsDetails", "advancedExport", "matrixDetails"]) {
  $(id).addEventListener("toggle", () => {
    $(id).querySelector("summary").setAttribute("aria-expanded", String($(id).open));
  });
}

const drop = $("drop"), fileInput = $("file"), status = $("status");
const progress = $("progress"), statusLive = $("statusLive"), workspace = $("workspace");
const canvas = $("photo"), ctx = canvas.getContext("2d");
const photoStage = $("photoStage");

// Several photographs of one code, in the order they arrived. The first one is the one shown
// on the canvas; hand-marking finders only makes sense against a single framing, so the
// marking flow is offered only while exactly one is loaded.
let loaded = [];    // { dataUrl, bitmap, name, result? (catalogue mode caches per photo) }

// An ImageBitmap holds a decoded frame at full resolution outside the JavaScript heap, so
// dropping the last reference to one does not hand the memory back on any schedule this page
// controls -- the browser frees it when it gets around to it. A burst of camera frames is
// hundreds of megabytes of that, and the tab is often open across several codes. So entries
// leaving `loaded` say so on the way out.
function releaseBitmaps(entries) {
  for (const entry of entries) {
    if (entry && entry.bitmap && typeof entry.bitmap.close === "function") entry.bitmap.close();
  }
}
let picking = false;
let picked = [];
let outlineEditing = false;
let outlineCorners = [];
let outlineMidpoints = [];
let outlineDrag = null;
let outlineKeyboardCursor = null;
let outlineKeyboardHandle = null;
let token = null;   // identifies the result the backend is holding for export
let seq = 0;        // solve sequence; a late answer from a superseded run must not render
let timerId = null;
let statusTimer = null;
let successTimer = null;
let progressOwner = null;
let lastAnnouncement = "";
let pendingWarning = "";
const bootProgressOwner = Symbol("boot");
let mode = "one";   // "one": several photographs of one code; "many": a catalogue
let lastSolved = false;  // a fresh drop after a success starts a fresh recovery

function syncManualTools(direct = studioState.mode === "pro") {
  const active = picking || outlineEditing;
  const single = loaded.length === 1;
  const recoveryChoice = studioState.phase === "failure" || studioState.phase === "assistance";
  const expanded = active || (single && (direct || recoveryChoice) && studioState.phase !== "success");
  const controls = $("manualTools");
  controls.hidden = !expanded;
  controls.setAttribute("aria-expanded", String(expanded));
  if (active) return;
  $("retry").hidden = !expanded;
  $("outlineRetry").hidden = !expanded;
  $("outlineSolve").hidden = true;
  $("cancel").hidden = true;
}

dispatchStudio({ type: "SET_MODE", mode: studioState.mode });

function announce(message) {
  if (!message || message === lastAnnouncement) return;
  lastAnnouncement = message;
  statusLive.textContent = message;
}

function stopElapsedTimer() {
  clearInterval(timerId);
  timerId = null;
}

function progressWorking(owner) {
  clearTimeout(statusTimer);
  stopElapsedTimer();
  progressOwner = owner;
  progress.classList.add("working");
  progress.classList.remove("complete");
  workspace.setAttribute("aria-busy", "true");
}

function progressIdle(owner) {
  if (owner !== undefined && progressOwner !== owner) return false;
  clearTimeout(statusTimer);
  stopElapsedTimer();
  progress.classList.remove("working", "complete");
  workspace.setAttribute("aria-busy", "false");
  progressOwner = null;
  return true;
}

function progressComplete(message) {
  progressIdle();
  const owner = Symbol("complete");
  progressOwner = owner;
  progress.classList.add("complete");
  status.textContent = message;
  announce(message);
  statusTimer = setTimeout(() => {
    if (progressOwner === owner) {
      status.textContent = "";
      progressIdle(owner);
    }
  }, 4000);
}

function resetSuccessEffect() {
  clearTimeout(successTimer);
  photoStage.classList.remove("locked");
  $("results").classList.remove("success-reveal");
}

function prepareRecoveryVisuals() {
  resetSuccessEffect();
  liveGrid = null;
  settledGrid = null;
  scheduleDraw();
}

function celebrateRecovery() {
  resetSuccessEffect();
  // Flush the removed state so a second recovered photograph replays the entrance cleanly.
  void photoStage.offsetWidth;
  photoStage.classList.add("locked");
  $("results").classList.add("success-reveal");
  successTimer = setTimeout(resetSuccessEffect, 1800);
}

/* --- the backend: where the work happens -------------------------------------------- */
/* window.qrBackend arrives from backend.js and is the page's only route to the recovery. The
   page never learns which of the two it got -- the local Python server or the same Python in a
   worker in this browser -- so everything that differs between the two is asked of it rather
   than assumed here: what to call this place, how to phrase the privacy fact, how to introduce
   its failures, and whether it needs a minute to start at all. */

$("privacyNote").textContent = window.qrBackend.privacyNote;

/* Booting is free on the local server and costs the better part of a minute in the browser,
   where a Python runtime, NumPy and OpenCV have to arrive before anything can be recovered.
   Reported in the ordinary status line: a page that looks broken for forty seconds is worse
   than one that says what it is doing. In server mode this never fires. */
window.qrBackend.onBoot((event) => {
  if (event.done) {
    if (progressOwner === bootProgressOwner && progressIdle(bootProgressOwner)) {
      status.textContent = "";
      announce(t("boot.ready"));
    }
    return;
  }
  if (progressOwner !== null && progressOwner !== bootProgressOwner) return;
  progressWorking(bootProgressOwner);
  const seconds = event.seconds
    ? ` <span class="mono">${escapeHtml(Number(event.seconds))} s</span>`
    : "";
  status.innerHTML =
    escapeHtml(t("boot.startingIn", { mode: window.qrBackend.mode })) +
    ` — ${escapeHtml(event.stage)}${seconds}` +
    `<span class="quiet"> — ${escapeHtml(t("boot.once"))}</span>`;
  announce(t("boot.starting", { stage: event.stage }));
});

/** Wait until recovering is possible at all. Answers false if it never will be. */
async function backendReady(owner) {
  try {
    await window.qrBackend.ready;
    return true;
  } catch (err) {
    if (progressIdle(owner)) {
      document.body.classList.remove("busy");
      status.textContent = window.qrBackend.failurePrefix + err;
      announce(t("boot.failure"));
      dispatchStudio({ type: "RECOVERY_FAILED" });
    }
    return false;
  }
}

/* --- camera: a burst while the hand moves ------------------------------------------- */
/* The fusion of photographs from different angles is the strongest measured lever of the
   whole tool -- and nobody takes three photographs by hand. One press takes four frames over
   two and a half seconds while the hand drifts, which is angle variation enough; frames go
   through exactly the same path as dropped files. The stream never leaves the device, and it
   is released the moment the panel closes. */

let cameraStream = null;
let capturing = false;
let captureOwner = null;
let torchOn = false;

if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
  $("cameraOpen").classList.remove("hidden");
}

$("cameraOpen").addEventListener("click", (e) => { e.stopPropagation(); openCamera(); });
$("cameraClose").addEventListener("click", cancelCapture);
$("capture").addEventListener("click", captureBurst);
$("torch").addEventListener("click", toggleTorch);

async function openCamera() {
  if (cameraStream || document.body.classList.contains("busy")) return;
  const owner = Symbol("camera");
  progressWorking(owner);
  status.textContent = t("camera.requesting");
  announce(t("camera.requestingAnnouncement"));
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment", width: { ideal: 2560 }, height: { ideal: 1440 } },
      audio: false,
    });
  } catch (err) {
    if (progressIdle(owner)) {
      status.textContent = t("camera.unavailable", { name: err.name });
      announce(t("camera.unavailableAnnouncement"));
    }
    return;
  }
  if (progressOwner !== owner) {
    for (const track of stream.getTracks()) track.stop();
    return;
  }
  cameraStream = stream;
  if (progressIdle(owner)) status.textContent = "";
  $("cameraFeed").srcObject = cameraStream;
  $("cameraPanel").classList.remove("hidden");
  $("cameraNote").textContent = mode === "one"
    ? t("camera.noteBurst")
    : t("camera.noteSingle");
  $("capture").textContent = mode === "one"
    ? t("camera.captureBurst")
    : t("camera.captureSingle");

  // A torch helps on shadowed, reflective and low-contrast labels in dark corners.
  const track = cameraStream.getVideoTracks()[0];
  const capabilities = track.getCapabilities ? track.getCapabilities() : {};
  $("torch").classList.toggle("hidden", !capabilities.torch);
  torchOn = false;
  $("torch").textContent = t("camera.lightOn");
}

function closeCamera() {
  if (cameraStream) for (const track of cameraStream.getTracks()) track.stop();
  cameraStream = null;
  $("cameraFeed").srcObject = null;
  $("cameraPanel").classList.add("hidden");
}

function cancelCapture() {
  const owner = captureOwner;
  captureOwner = null;
  capturing = false;
  if (owner && progressIdle(owner)) {
    document.body.classList.remove("busy");
    status.textContent = "";
  }
  closeCamera();
}

async function toggleTorch() {
  if (!cameraStream) return;
  torchOn = !torchOn;
  try {
    await cameraStream.getVideoTracks()[0].applyConstraints({ advanced: [{ torch: torchOn }] });
    $("torch").textContent = torchOn ? t("camera.lightOff") : t("camera.lightOn");
  } catch { /* not every browser lets the page at the torch; the button just stays honest */ }
}

async function captureBurst() {
  if (!cameraStream || capturing || document.body.classList.contains("busy")) return;
  const video = $("cameraFeed");
  if (!video.videoWidth) { $("cameraNote").textContent = t("camera.starting"); return; }
  const owner = Symbol("capture");
  const frames = [];
  captureOwner = owner;
  capturing = true;
  document.body.classList.add("busy");
  progressWorking(owner);
  status.textContent = t("camera.capturing");
  announce(t("camera.capturingAnnouncement"));
  const count = mode === "one" ? 4 : 1;
  let committed = false;
  try {
    for (let i = 0; i < count; i++) {
      $("cameraNote").textContent = count > 1
        ? t("camera.frame", { current: i + 1, total: count })
        : t("camera.captured");
      const frame = document.createElement("canvas");
      frame.width = video.videoWidth;
      frame.height = video.videoHeight;
      frame.getContext("2d").drawImage(video, 0, 0);
      const bitmap = await createImageBitmap(frame);
      frames.push({
        // JPEG, not PNG: a camera frame is noise-limited anyway, and a 2560-wide PNG would
        // make every recovery haul megabytes to the backend for nothing.
        dataUrl: frame.toDataURL("image/jpeg", 0.92),
        bitmap,
        name: `camera ${loaded.length + frames.length + 1}`,
      });
      if (progressOwner !== owner) return;
      if (i < count - 1) {
        await new Promise((resolve) => setTimeout(resolve, 700));
        if (progressOwner !== owner) return;
      }
    }
    if (progressOwner !== owner) return;
    loaded.push(...frames);
    committed = true;
    closeCamera();
    status.textContent = t("camera.preparing");
    announce(t("camera.preparingAnnouncement"));
    refresh();
    run();
  } catch (err) {
    if (progressIdle(owner)) {
      document.body.classList.remove("busy");
      status.textContent = t("camera.failure", { message: err.message });
      announce(t("camera.failureAnnouncement"));
    }
  } finally {
    if (!committed) releaseBitmaps(frames);
    if (captureOwner === owner) {
      captureOwner = null;
      capturing = false;
    }
  }
}

for (const radio of document.querySelectorAll('#modeRow input')) {
  radio.addEventListener("change", () => {
    mode = radio.value;
    picked = []; picking = false;
    clearOutlineEditor(false);
    if (loaded.length) run();
  });
}

function run() {
  if (mode === "many") { catalogRun(); } else { solve(); }
}

drop.addEventListener("click", () => {
  if (!document.body.classList.contains("busy")) fileInput.click();
});
drop.addEventListener("keydown", (event) => {
  if (event.target !== drop || !window.qrStudioState.isActivationKey(event.key)) return;
  event.preventDefault();
  if (!document.body.classList.contains("busy")) fileInput.click();
});
drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", (e) => {
  e.preventDefault(); drop.classList.remove("over");
  addFiles(e.dataTransfer.files);
});
fileInput.addEventListener("change", () => { addFiles(fileInput.files); fileInput.value = ""; });
$("reset").addEventListener("click", (e) => { e.stopPropagation(); resetAll(); });

function readAsDataURL(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

function bitmapToJpeg(bitmap) {
  const frame = document.createElement("canvas");
  frame.width = bitmap.width;
  frame.height = bitmap.height;
  frame.getContext("2d").drawImage(bitmap, 0, 0);
  return frame.toDataURL("image/jpeg", 0.95);
}

async function addFiles(files) {
  const images = [...(files || [])].filter((f) => f.type && f.type.startsWith("image/"));
  if (!images.length) return;
  if (document.body.classList.contains("busy")) return;
  document.body.classList.add("busy");
  const owner = Symbol("selection");
  progressWorking(owner);
  status.textContent = images.length === 1
    ? t("input.readingOne")
    : t("input.readingMany", { count: images.length });
  announce(images.length === 1
    ? t("input.readingOneAnnouncement")
    : t("input.readingManyAnnouncement", { count: images.length }));

  const accepted = [];
  const refused = [];
  for (const file of images) {
    let bitmap = null;
    try {
      bitmap = await createImageBitmap(file);
      if (progressOwner !== owner) {
        bitmap.close();
        releaseBitmaps(accepted);
        return;
      }
      // iPhones photograph HEIC. Where the browser can decode it (Safari), it is transcoded
      // to JPEG here, because the recovery backend cannot read HEIC bytes. Everything else
      // travels untouched -- recompressing a crisp PNG would only cost detail.
      const transcode = /hei[cf]/i.test(file.type || "");
      const dataUrl = transcode ? bitmapToJpeg(bitmap) : await readAsDataURL(file);
      if (progressOwner !== owner) {
        bitmap.close();
        releaseBitmaps(accepted);
        return;
      }
      accepted.push({
        dataUrl,
        bitmap,
        name: file.name,
      });
    } catch {
      if (bitmap) bitmap.close();
      // The old behaviour on an undecodable file was silence -- the drop zone did not even
      // twitch. The most common cause is an iPhone HEIC on a browser without an HEIC decoder.
      refused.push(file.name);
    }
  }
  if (progressOwner !== owner) {
    releaseBitmaps(accepted);
    return;
  }
  if (!accepted.length) {
    if (progressIdle(owner)) {
      document.body.classList.remove("busy");
      status.textContent = t("input.unreadable", { names: refused.join(", ") });
      announce(t("input.unreadableAnnouncement"));
    }
    return;
  }

  // After a success a fresh drop means a fresh code: adding to a solved one is always
  // pointless, because the already-solved member wins again before anything is fused.
  if (mode === "one" && lastSolved && loaded.length) {
    releaseBitmaps(loaded);
    loaded = []; token = null; lastSolved = false;
  }
  loaded.push(...accepted);
  dispatchStudio({ type: "IMAGES_READY" });
  if (refused.length) {
    pendingWarning = t("input.unreadable", { names: refused.join(", ") });
  }
  picked = []; picking = false;
  clearOutlineEditor(false);
  refresh();
  run();
}

function resetAll() {
  seq += 1;               // orphan any solve still in flight
  busy(false);
  captureOwner = null;
  capturing = false;
  closeCamera();
  releaseBitmaps(loaded);
  loaded = []; picked = []; picking = false; token = null; pendingWarning = "";
  clearOutlineEditor(false);
  lastSolved = false;
  settledGrid = null;
  resetSuccessEffect();
  $("results").classList.add("hidden");
  $("catalogPanel").classList.add("hidden");
  drop.classList.remove("compact");
  $("reset").classList.add("hidden");
  $("dropTitle").textContent = t("input.drop");
  $("dropMore").textContent = ` ${t("input.choose")}`;
  status.textContent = "";
  dispatchStudio({ type: "RESET" });
}

function refresh() {
  drop.classList.add("compact");
  $("reset").classList.remove("hidden");
  $("dropTitle").textContent = loaded.length === 1
    ? t("input.loadedOne")
    : t("input.loadedMany", { count: loaded.length });
  $("dropMore").textContent = ` — ${t("input.more")}`;

  const thumbs = $("thumbs");
  thumbs.classList.toggle("hidden", mode === "one" && loaded.length < 2);
  thumbs.innerHTML = loaded
    .map((l, i) => `<div class="thumb"><img src="${escapeHtml(l.dataUrl)}" alt="">` +
                   `<button data-index="${escapeHtml(i)}" title="${escapeHtml(t("input.remove"))}">×</button></div>`)
    .join("");
  for (const button of thumbs.querySelectorAll("button")) {
    button.addEventListener("click", () => {
      releaseBitmaps(loaded.splice(parseInt(button.dataset.index, 10), 1));
      picked = []; picking = false;
      clearOutlineEditor(false);
      if (!loaded.length) { resetAll(); return; }
      refresh();
      run();
    });
  }
  draw();
}

function draw(detected) {
  if (!loaded.length) return;
  const bitmap = loaded[0].bitmap;
  const width = Math.min(bitmap.width, 520);
  const scale = width / bitmap.width;
  canvas.width = width;
  canvas.height = Math.round(bitmap.height * scale);
  ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  canvas.dataset.scale = scale;

  // What the detector found, quietly; what the user clicked, loudly. Both over a dark halo,
  // because a thin bright ring on a bright photograph is invisible exactly where it matters.
  for (const p of detected || []) ring(p.x * scale, p.y * scale, 11, "#8fd3b0", 2.5);
  const grid = liveGrid || settledGrid;
  if (grid) drawCurvedOutline(grid, scale);
  picked.forEach((p, i) => {
    ring(p.x * scale, p.y * scale, 11, "#f07ea3", 2.5);
    ctx.font = "600 13px ui-monospace, monospace";
    ctx.strokeStyle = "rgba(10, 14, 18, .85)"; ctx.lineWidth = 3;
    ctx.strokeText(String(i + 1), p.x * scale + 15, p.y * scale + 5);
    ctx.fillStyle = "#f07ea3";
    ctx.fillText(String(i + 1), p.x * scale + 15, p.y * scale + 5);
  });
  drawEditableOutline(scale);
}

function pointObject(point) {
  return Array.isArray(point) ? { x: point[0], y: point[1] } : { x: point.x, y: point.y };
}

function defaultEdgeMidpoints(corners) {
  return corners.map((start, i) => {
    const end = corners[(i + 1) % corners.length];
    return { x: (start.x + end.x) / 2, y: (start.y + end.y) / 2 };
  });
}

function outlineGeometry(corners, edgeMidpoints) {
  const points = corners.map(pointObject);
  const middles = edgeMidpoints && edgeMidpoints.length === points.length
    ? edgeMidpoints.map(pointObject)
    : defaultEdgeMidpoints(points);
  return { corners: points, edgeMidpoints: middles };
}

function drawCurvedOutline(outline, scale) {
  if (!outline || outline.corners.length !== 4 || outline.edgeMidpoints.length !== 4) return;
  ctx.beginPath();
  ctx.moveTo(outline.corners[0].x * scale, outline.corners[0].y * scale);
  outline.corners.forEach((start, i) => {
    const end = outline.corners[(i + 1) % outline.corners.length];
    const middle = outline.edgeMidpoints[i];
    const controlX = 2 * middle.x - (start.x + end.x) / 2;
    const controlY = 2 * middle.y - (start.y + end.y) / 2;
    ctx.quadraticCurveTo(controlX * scale, controlY * scale, end.x * scale, end.y * scale);
  });
  ctx.closePath();
  ctx.strokeStyle = "rgba(10, 14, 18, .85)"; ctx.lineWidth = 4.5; ctx.stroke();
  ctx.strokeStyle = "#f07ea3"; ctx.lineWidth = 2; ctx.stroke();
}

function diamond(x, y, radius, colour) {
  const path = () => {
    ctx.beginPath();
    ctx.moveTo(x, y - radius); ctx.lineTo(x + radius, y);
    ctx.lineTo(x, y + radius); ctx.lineTo(x - radius, y); ctx.closePath();
  };
  path(); ctx.strokeStyle = "rgba(10, 14, 18, .85)"; ctx.lineWidth = 5; ctx.stroke();
  path(); ctx.fillStyle = colour; ctx.fill();
}

function drawEditableOutline(scale) {
  if (!outlineCorners.length) return;
  if (outlineCorners.length === 4 && outlineMidpoints.length === 4) {
    drawCurvedOutline(
      { corners: outlineCorners, edgeMidpoints: outlineMidpoints },
      scale
    );
    outlineMidpoints.forEach((p) => diamond(p.x * scale, p.y * scale, 6, "#f7b3c8"));
  }
  outlineCorners.forEach((p, i) => {
    ring(p.x * scale, p.y * scale, 12, "#f07ea3", 3);
    ctx.font = "600 13px ui-monospace, monospace";
    ctx.strokeStyle = "rgba(10, 14, 18, .85)"; ctx.lineWidth = 3;
    ctx.strokeText(String(i + 1), p.x * scale + 16, p.y * scale + 5);
    ctx.fillStyle = "#f7b3c8";
    ctx.fillText(String(i + 1), p.x * scale + 16, p.y * scale + 5);
  });
  if (outlineKeyboardCursor) {
    diamond(
      outlineKeyboardCursor.x * scale,
      outlineKeyboardCursor.y * scale,
      7,
      "#8fd3b0"
    );
  }
  if (outlineKeyboardHandle && outlineCorners.length === 4) {
    const points = outlineKeyboardHandle.kind === "corner" ? outlineCorners : outlineMidpoints;
    const selected = points[outlineKeyboardHandle.index];
    ring(selected.x * scale, selected.y * scale, 16, "#8fd3b0", 2.5);
  }
}

function ring(x, y, r, colour, width) {
  ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.strokeStyle = "rgba(10, 14, 18, .85)"; ctx.lineWidth = width + 3; ctx.stroke();
  ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.strokeStyle = colour; ctx.lineWidth = width; ctx.stroke();
}

function canvasPoint(e) {
  const rect = canvas.getBoundingClientRect();
  const scale = parseFloat(canvas.dataset.scale);
  return {
    x: ((e.clientX - rect.left) * (canvas.width / rect.width)) / scale,
    y: ((e.clientY - rect.top) * (canvas.height / rect.height)) / scale,
  };
}

canvas.addEventListener("click", (e) => {
  if (!picking) return;
  picked.push(canvasPoint(e));
  draw();
  $("canvasNote").textContent = picked.length < 3
    ? t("manual.finderProgress", { count: picked.length })
    : t("manual.findersReady");
  if (picked.length === 3) { picking = false; solve(picked); }
});

function updateOutlineInstructions() {
  let message;
  if (outlineCorners.length < 4) {
    const next = t(DYNAMIC_LOCALE_KEYS.outlineCorners[outlineCorners.length]);
    message = `${t("manual.outlineProgress", {
      count: outlineCorners.length,
      next,
    })} ${t("manual.outlineKeyboardPlace")}`;
  } else {
    message = `${t("manual.outlineAdjust")} ${t("manual.outlineKeyboardAdjust")}`;
  }
  $("canvasNote").textContent = message;
  canvas.setAttribute("aria-label", message);
}

function freezeOutlineEditor() {
  if (outlineDrag && canvas.hasPointerCapture(outlineDrag.pointerId)) {
    canvas.releasePointerCapture(outlineDrag.pointerId);
  }
  outlineEditing = false;
  outlineDrag = null;
  canvas.classList.remove("outline-editing", "outline-ready", "outline-dragging");
}

function clearOutlineEditor(redraw = true) {
  freezeOutlineEditor();
  outlineCorners = [];
  outlineMidpoints = [];
  outlineKeyboardCursor = null;
  outlineKeyboardHandle = null;
  canvas.setAttribute("aria-label", t("manual.outlineCanvas"));
  $("outlineSolve").hidden = true;
  if (redraw && loaded.length) draw();
}

function nextOutlineKeyboardCursor() {
  const bitmap = loaded[0].bitmap;
  const positions = [
    [0.1, 0.1],
    [0.9, 0.1],
    [0.9, 0.9],
    [0.1, 0.9],
  ];
  const [x, y] = positions[outlineCorners.length];
  return { x: bitmap.width * x, y: bitmap.height * y };
}

function cycleOutlineKeyboardHandle(direction) {
  const current = outlineKeyboardHandle
    ? outlineKeyboardHandle.index + (outlineKeyboardHandle.kind === "midpoint" ? 4 : 0)
    : 0;
  const next = (current + direction + 8) % 8;
  outlineKeyboardHandle = next < 4
    ? { kind: "corner", index: next }
    : { kind: "midpoint", index: next - 4 };
}

function outlineHandleAt(point) {
  const rect = canvas.getBoundingClientRect();
  const scale = parseFloat(canvas.dataset.scale);
  const imagePixelsPerCssPixel = (canvas.width / rect.width) / scale;
  const hitRadius = 18 * imagePixelsPerCssPixel;
  return window.qrOutlineEditor.selectNearestHandle(
    point, outlineCorners, outlineMidpoints, hitRadius
  );
}

canvas.addEventListener("pointerdown", (e) => {
  if (!outlineEditing || (e.button !== undefined && e.button !== 0)) return;
  e.preventDefault();
  const point = canvasPoint(e);
  if (outlineCorners.length < 4) {
    outlineCorners.push(point);
    if (outlineCorners.length === 4) {
      outlineMidpoints = defaultEdgeMidpoints(outlineCorners);
      outlineKeyboardCursor = null;
      outlineKeyboardHandle = { kind: "corner", index: 0 };
      canvas.classList.add("outline-ready");
      $("outlineSolve").hidden = false;
    } else {
      outlineKeyboardCursor = nextOutlineKeyboardCursor();
    }
    updateOutlineInstructions();
    draw();
    return;
  }

  const handle = outlineHandleAt(point);
  if (!handle) return;
  outlineDrag = { ...handle, pointerId: e.pointerId, last: point };
  canvas.setPointerCapture(e.pointerId);
  canvas.classList.add("outline-dragging");
});

canvas.addEventListener("pointermove", (e) => {
  if (!outlineEditing || !outlineDrag || outlineDrag.pointerId !== e.pointerId) return;
  e.preventDefault();
  const point = canvasPoint(e);
  const dx = point.x - outlineDrag.last.x;
  const dy = point.y - outlineDrag.last.y;
  const moved = window.qrOutlineEditor.moveHandle(
    outlineCorners, outlineMidpoints, outlineDrag, { x: dx, y: dy }
  );
  outlineCorners = moved.corners;
  outlineMidpoints = moved.edgeMidpoints;
  outlineDrag.last = point;
  draw();
});

function finishOutlineDrag(e) {
  if (!outlineDrag || outlineDrag.pointerId !== e.pointerId) return;
  if (canvas.hasPointerCapture(e.pointerId)) canvas.releasePointerCapture(e.pointerId);
  outlineDrag = null;
  canvas.classList.remove("outline-dragging");
}

canvas.addEventListener("pointerup", finishOutlineDrag);
canvas.addEventListener("pointercancel", finishOutlineDrag);

canvas.addEventListener("keydown", (event) => {
  if (!outlineEditing) return;
  const command = window.qrOutlineEditor.keyboardCommand(event.key, event.shiftKey);
  if (!command) return;
  event.preventDefault();
  if (command.type === "place") {
    if (outlineCorners.length >= 4 || !outlineKeyboardCursor) return;
    outlineCorners.push({ ...outlineKeyboardCursor });
    if (outlineCorners.length === 4) {
      outlineMidpoints = defaultEdgeMidpoints(outlineCorners);
      outlineKeyboardCursor = null;
      outlineKeyboardHandle = { kind: "corner", index: 0 };
      canvas.classList.add("outline-ready");
      $("outlineSolve").hidden = false;
    } else {
      outlineKeyboardCursor = nextOutlineKeyboardCursor();
    }
  } else if (command.type === "cycle" && outlineCorners.length === 4) {
    cycleOutlineKeyboardHandle(command.direction);
  } else if (command.type === "move") {
    const bitmap = loaded[0].bitmap;
    const step = Math.max(bitmap.width, bitmap.height) / 100 * command.multiplier;
    const delta = { x: command.x * step, y: command.y * step };
    if (outlineCorners.length < 4 && outlineKeyboardCursor) {
      outlineKeyboardCursor.x = Math.max(0, Math.min(bitmap.width, outlineKeyboardCursor.x + delta.x));
      outlineKeyboardCursor.y = Math.max(0, Math.min(bitmap.height, outlineKeyboardCursor.y + delta.y));
    } else if (outlineKeyboardHandle) {
      const moved = window.qrOutlineEditor.moveHandle(
        outlineCorners, outlineMidpoints, outlineKeyboardHandle, delta
      );
      outlineCorners = moved.corners;
      outlineMidpoints = moved.edgeMidpoints;
    }
  }
  updateOutlineInstructions();
  draw();
});

function busy(on, owner) {
  if (!on) {
    if (owner !== undefined && progressOwner !== owner) return false;
    document.body.classList.remove("busy");
    progressIdle(owner);
    status.textContent = "";
    return true;
  }
  document.body.classList.add("busy");
  progressWorking(owner);
  const started = Date.now();
  const together = loaded.length > 1
    ? ` · ${t("progress.readingTogether", { count: loaded.length })}`
    : "";
  const warning = pendingWarning
    ? `<span class="quiet"> · ${escapeHtml(pendingWarning)}</span>`
    : "";
  status.innerHTML =
    `<strong>${escapeHtml(t("progress.recovering"))}</strong> ` +
    `<span class="mono" id="elapsed" aria-hidden="true">0 s</span>` +
    `<span class="quiet" id="progressStage">${escapeHtml(
      together || ` · ${t("progress.readingOne")}`
    )} — ${escapeHtml(t("progress.largePhoto"))}</span>${warning}`;
  announce(pendingWarning ? t("progress.startedWarning") : t("progress.started"));
  pendingWarning = "";
  timerId = setInterval(() => {
    const el = $("elapsed");
    if (el) el.textContent = Math.round((Date.now() - started) / 1000) + " s";
  }, 1000);
  return true;
}

async function solve(points, outlineHint) {
  if (!loaded.length) return;
  prepareRecoveryVisuals();
  for (const id of ["retry", "outlineRetry", "outlineSolve", "cancel"]) {
    $(id).hidden = true;
  }
  const my = ++seq;
  const owner = Symbol(`solve-${my}`);
  $("catalogPanel").classList.add("hidden");
  document.body.classList.add("busy");
  progressWorking(owner);
  status.textContent = t("progress.preparing");
  announce(t("progress.preparingAnnouncement"));
  dispatchStudio({ type: "PREPARING" });
  const ready = await backendReady(owner);
  if (!ready || my !== seq) {
    if (my === seq) clearOutlineEditor();
    if (progressOwner === owner) {
      document.body.classList.remove("busy");
      progressIdle(owner);
      status.textContent = "";
    }
    return;
  }
  dispatchStudio({ type: "RECOVERY_STARTED" });
  busy(true, owner);
  liveStart();
  let answer = null;
  try {
    // Every event but the last is a step of the actual recovery — the grid snapping into
    // place, the versions competing, the probe counting. The last one is the result, and it
    // is what solve() answers with.
    answer = await window.qrBackend.solve(
      {
        images: loaded.map((l) => l.dataUrl),
        finder_points: points || null,
        outline: outlineHint ? {
          corners: outlineHint.corners,
          edge_midpoints: outlineHint.edgeMidpoints,
        } : null,
      },
      (event) => { if (my === seq) liveEvent(event); }
    );
  } catch (err) {
    if (my === seq && busy(false, owner)) {
      clearOutlineEditor(false);
      liveEnd(false);
      status.textContent = window.qrBackend.failurePrefix + err;
      announce(t("result.failure"));
      dispatchStudio({ type: "RECOVERY_FAILED" });
    }
    return;
  }
  if (my !== seq) return;  // superseded by a newer drop; this answer belongs to old inputs
  if (!busy(false, owner)) return;
  clearOutlineEditor(false);
  liveEnd(!!answer.ok);
  if (answer) {
    renderAnswer(answer);
    if (answer.ok) {
      progressComplete(t("result.success"));
      celebrateRecovery();
      dispatchStudio({ type: "RECOVERY_SUCCEEDED" });
    } else {
      dispatchStudio({ type: "RECOVERY_FAILED" });
    }
  }
}

/* --- the live view: watch the method work ------------------------------------------- */
/* Everything shown here is a true intermediate state of the recovery, not an animation
   played over a black box. The grid drawn on the photograph is the grid the descent is
   holding right now; the numbers are the numbers it is scoring. */

let liveGrid = null;      // {corners, edgeMidpoints} for the last accepted grid
let settledGrid = null;   // successful final grid, kept visible after the live view closes
let liveGrids = {};       // modules -> geometry, so the chosen version keeps its matching grid
let liveSizes = {};       // modules -> {wrong, total, quality}
let liveFrame = false;    // requestAnimationFrame throttle
let liveChosen = null;

// The method links are relative on purpose, like every other reference the page makes. The
// static build is served from wherever it is put -- a domain root, a project subpath such as
// <user>.github.io/qrsalvage/, or a bare filesystem -- and "/method#grid" would leave that
// directory and land at the host root under two of those three. method.html is the file's real
// name; the local server answers /method as well, but only the name works everywhere.
const STAGE_LINKS = {
  finders: "method.html#search",
  polarity: "method.html#search",
  grid: "method.html#grid",
  chosen: "method.html#search",
  sampled: "method.html#posterior",
  repair: "method.html#rs",
  probe: "method.html#probe",
};

function liveStart() {
  liveGrid = null; settledGrid = null; liveGrids = {}; liveSizes = {}; liveChosen = null;
  document.body.classList.add("watching");
  $("live").classList.remove("hidden");
  $("verdict").classList.add("hidden");
  $("metrics").innerHTML = "";
  $("liveStage").textContent = "";
  $("liveSizes").innerHTML = "";
  $("heat").width = 0; $("heat").height = 0;
  $("heatNote").textContent = "";
  $("payload").classList.add("hidden");
  $("images").innerHTML = "";
  $("exports").classList.add("hidden");
  $("results").classList.remove("hidden");
}

function liveEnd(persistGrid) {
  document.body.classList.remove("watching");
  $("live").classList.add("hidden");
  $("payload").classList.remove("hidden");
  settledGrid = persistGrid ? liveGrid : null;
  liveGrid = null;
  scheduleDraw();
}

function liveEvent(e) {
  const stageKey = DYNAMIC_LOCALE_KEYS.recoveryStages[e.type];
  if (stageKey) {
    const member = e.member !== undefined
      ? `${t("recovery.member", { count: e.member + 1 })} · `
      : "";
    const stageText = t(DYNAMIC_LOCALE_KEYS.recoveryStages[e.type]);
    const extra =
      e.type === "grid" && e.phase === "bow" ? ` — ${t("recovery.gridBow")}` :
      e.type === "grid" && e.phase === "restart" ? ` — ${t("recovery.gridRestart")}` :
      e.type === "probe" ? ` — ${t("recovery.probeAttempts", { tried: e.tried, budget: e.budget })}` :
      e.type === "repair" ? ` — ${e.method === "ladder"
        ? t("recovery.repairErasures", { count: e.step })
        : t("recovery.repairSets", { count: e.step })}` :
      e.type === "member" ? ` — ${t("recovery.memberProgress", {
        current: e.index + 1,
        total: e.total,
      })}` : "";
    const stageLink = STAGE_LINKS[e.type];
    $("liveStage").innerHTML = escapeHtml(member) + (stageLink
      ? `<a href="${escapeHtml(stageLink)}" target="_blank">${escapeHtml(stageText)}</a>`
      : escapeHtml(stageText)) + escapeHtml(extra);
    const progressStage = $("progressStage");
    if (progressStage) {
      progressStage.textContent = ` · ${member}${stageText}${extra}`;
    }
    // The visible diagnostics may update on every probe. Screen readers get the meaningful
    // stage only, and announce() suppresses identical consecutive stages.
    announce(t("progress.stage", { stage: `${member}${stageText}` }));
  }
  if (e.type === "member") {
    liveGrid = null; liveGrids = {}; liveSizes = {}; liveChosen = null; scheduleDraw();
  }
  if (e.type === "finders" && loaded.length === 1 && e.member === undefined) {
    draw(e.points);
  }
  if (e.type === "grid") {
    liveSizes[e.modules] = { wrong: e.wrong, total: e.total, quality: e.quality };
    renderRace();
    // Only the primary photograph's grid is drawn — the canvas shows that one.
    if (loaded.length === 1 || e.member === 0 || e.member === undefined) {
      liveGrid = outlineGeometry(e.corners, e.edge_midpoints);
      liveGrids[e.modules] = liveGrid;
      scheduleDraw();
    }
  }
  if (e.type === "chosen") {
    liveChosen = e.modules;
    liveGrid = liveGrids[e.modules] || liveGrid;
    renderRace();
    scheduleDraw();
  }
  if (e.type === "sampled" && e.posterior) { renderHeat(e); }
}

function renderRace() {
  const sizes = Object.keys(liveSizes).map(Number).sort((a, b) => a - b);
  const rows = sizes.map((m) => {
    const s = liveSizes[m];
    const share = Math.min(s.wrong / Math.max(s.total, 1) / 0.4, 1);
    const width = 4 + Math.round(76 * share);
    const best = liveChosen === m ? " best" : "";
    return `<dt>${escapeHtml(t("diagnostics.modules", { count: Number(m) }))}</dt>` +
           `<dd><span class="racebar${escapeHtml(best)}" style="width:${escapeHtml(width)}px"></span>` +
           `${escapeHtml(t("diagnostics.wrong", {
             wrong: Number(s.wrong), total: Number(s.total),
           }))}</dd>`;
  });
  $("liveSizes").innerHTML = rows.join("");
}

function renderHeat(e) {
  // The three-state story, visible: dark and light where the model is sure, red where it is
  // not. This is the matrix the search is about to work on.
  const n = e.posterior.length;
  const heat = $("heat");
  heat.width = n; heat.height = n;
  heat.style.width = `${Math.min(n * 5, 176)}px`;
  const context = heat.getContext("2d");
  const pixels = context.createImageData(n, n);
  for (let r = 0; r < n; r++) {
    for (let c = 0; c < n; c++) {
      const p = e.posterior[r][c];
      const confidence = Math.min(Math.abs(p - 0.5) * 2 / 0.6, 1);
      const base = p >= 0.5 ? [14, 22, 29] : [238, 241, 243];
      const offset = (r * n + c) * 4;
      pixels.data[offset]     = Math.round(base[0] * confidence + 224 * (1 - confidence));
      pixels.data[offset + 1] = Math.round(base[1] * confidence + 90 * (1 - confidence));
      pixels.data[offset + 2] = Math.round(base[2] * confidence + 74 * (1 - confidence));
      pixels.data[offset + 3] = 255;
    }
  }
  context.putImageData(pixels, 0, 0);
  $("heatNote").textContent = t("diagnostics.heatmap", {
    modules: e.modules,
    uncertain: e.uncertain,
    wrongKnown: e.wrong_known,
  });
}

function scheduleDraw() {
  if (liveFrame) return;
  liveFrame = true;
  requestAnimationFrame(() => { liveFrame = false; draw(); });
}

/* --- catalogue mode: every photograph its own code ---------------------------------- */

function titleFrom(name) {
  return (name || "").replace(/\.[^.]+$/, "").replace(/[-_]+/g, " ").trim() ||
    t("catalogue.untitled");
}

async function catalogRun() {
  prepareRecoveryVisuals();
  const my = ++seq;
  const owner = Symbol(`catalog-${my}`);
  const warning = pendingWarning;
  pendingWarning = "";
  $("results").classList.add("hidden");
  $("catalogPanel").classList.remove("hidden");
  document.body.classList.add("busy");
  progressWorking(owner);
  status.innerHTML = escapeHtml(t("catalogue.preparing")) +
    (warning ? `<span class="quiet"> · ${escapeHtml(warning)}</span>` : "");
  announce(warning
    ? t("catalogue.preparingWarning")
    : t("catalogue.preparingAnnouncement"));
  dispatchStudio({ type: "PREPARING" });
  const ready = await backendReady(owner);
  if (!ready || my !== seq) {
    if (progressOwner === owner) {
      document.body.classList.remove("busy");
      progressIdle(owner);
      status.textContent = "";
    }
    return;
  }
  dispatchStudio({ type: "RECOVERY_STARTED" });

  // One photograph at a time, so the progress is real rather than a guess — and a photograph
  // already recovered in this session is not recovered again when one more lands in the pile.
  const pending = loaded.filter((l) => !l.result);
  let done = 0;
  for (const item of pending) {
    status.innerHTML =
      `<strong>${escapeHtml(t("catalogue.recovering", {
        current: ++done,
        total: pending.length,
      }))}</strong> ` +
      `<span class="quiet">${escapeHtml(item.name)}</span>` +
      (warning ? `<span class="quiet"> · ${escapeHtml(warning)}</span>` : "");
    announce(t("catalogue.recoveringAnnouncement", { current: done, total: pending.length }));
    catalogRender();
    try {
      // A catalogue narrates its own progress card by card, so the events of the single
      // recovery running right now have nowhere to go.
      const answer = await window.qrBackend.solve({ images: [item.dataUrl] }, () => {});
      if (my !== seq) return;
      item.result = answer;
    } catch (err) {
      if (my !== seq) return;
      if (progressIdle(owner)) {
        document.body.classList.remove("busy");
        status.textContent = window.qrBackend.failurePrefix + err;
        announce(t("catalogue.recoveryFailure"));
        dispatchStudio({ type: "RECOVERY_FAILED" });
      }
      return;
    }
  }
  if (my !== seq) return;
  if (!progressIdle(owner)) return;
  document.body.classList.remove("busy");
  catalogRender();
  progressComplete(t("catalogue.complete"));
  dispatchStudio({
    type: loaded.some((item) => item.result && item.result.ok)
      ? "RECOVERY_SUCCEEDED"
      : "RECOVERY_FAILED",
  });
}

function catalogRender() {
  const seen = new Map();  // payload text -> index of the first card that carries it
  const cards = loaded.map((item, index) => {
    const r = item.result;
    if (item.title === undefined) item.title = titleFrom(item.name);
    if (!r) {
      return `<div class="card"><span class="state quiet">${escapeHtml(t("catalogue.waiting"))}</span>
        <img src="${escapeHtml(item.dataUrl)}" alt=""></div>`;
    }
    if (!r.ok) {
      return `<div class="card miss"><span class="state bad">${escapeHtml(t("catalogue.notRecovered"))}</span>
        <img src="${escapeHtml(item.dataUrl)}" alt="">
        <div class="snippet">${escapeHtml(item.name)} — ${escapeHtml(r.failure || "")}.
        ${escapeHtml(t("catalogue.failureAdvice"))}</div></div>`;
    }
    const first = seen.get(r.text);
    if (first !== undefined) {
      return `<div class="card dup"><span class="state quiet">${escapeHtml(
        t("catalogue.duplicate", { title: loaded[first].title })
      )}</span>
        <img src="${escapeHtml(item.dataUrl)}" alt=""></div>`;
    }
    seen.set(r.text, index);
    return `<div class="card"><span class="state ok">${escapeHtml(t("catalogue.recovered"))}</span>
      ${r.clean_png ? `<img src="${escapeHtml(r.clean_png)}" alt="">` : ""}
      <input class="title" data-index="${escapeHtml(index)}" value="${escapeHtml(item.title)}"
        placeholder="${escapeHtml(t("catalogue.titlePlaceholder"))}">
      <div class="snippet">${escapeHtml(r.text)}</div></div>`;
  });
  $("cards").innerHTML = cards.join("");
  for (const input of $("cards").querySelectorAll("input.title")) {
    input.addEventListener("input", () => {
      loaded[parseInt(input.dataset.index, 10)].title = input.value;
    });
  }
  const solvedTexts = new Set(
    loaded.filter((l) => l.result && l.result.ok).map((l) => l.result.text)
  );
  $("catalogPdf").disabled = solvedTexts.size === 0;
}

$("catalogPdf").addEventListener("click", async () => {
  if (document.body.classList.contains("busy")) return;
  const seen = new Set();
  const entries = [];
  for (const item of loaded) {
    const r = item.result;
    if (!r || !r.ok || seen.has(r.text)) continue;
    seen.add(r.text);
    const note = (r.version ? t("catalogue.version", { version: r.version }) : "") +
      (r.ecc ? ` · ${t("catalogue.errorCorrection", { level: r.ecc })}` : "") +
      ` · ${t("catalogue.characters", { count: r.text.length })}`;
    entries.push({ title: item.title || titleFrom(item.name), text: r.text,
                   ecc: r.ecc || null, note: note.replace(/^ · /, "") });
  }
  if (!entries.length) return;
  const owner = Symbol("catalog-export");
  document.body.classList.add("busy");
  progressWorking(owner);
  status.textContent = t("catalogue.preparingDownload");
  announce(t("catalogue.preparingDownloadAnnouncement"));
  let file;
  try {
    file = await window.qrBackend.file("catalog", {
      entries,
      size_mm: parseFloat($("catalogSizeMm").value) || 50,
    });
  } catch (err) {
    if (progressIdle(owner)) {
      document.body.classList.remove("busy");
      status.textContent = t("catalogue.exportFailure", { message: err.message });
      announce(t("catalogue.exportFailureAnnouncement"));
    }
    return;
  }
  if (progressOwner !== owner) return;
  const url = URL.createObjectURL(file.blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = file.filename || "catalog.pdf";
  link.click();
  URL.revokeObjectURL(url);
  document.body.classList.remove("busy");
  progressComplete(t("catalogue.downloaded"));
});

function informationGone(a) {
  // The honest bad news, distinguished from the hopeful kind: the grid is essentially
  // perfect, several photographs agreed, and the data still will not read. Measured on the
  // corpus, that combination means modules are physically gone -- more photographs of the
  // same views cannot bring them back.
  const rate = a.wrong_known / a.known_total;
  return !a.ok && rate <= 0.01 && a.timing >= 100 && (a.images_given || 1) >= 3;
}

function verdictFor(a) {
  if (a.ok && a.source === "direct") {
    return ["ok", t("verdict.direct")];
  }
  if (!a.modules) {
    const n = a.finders.length;
    return ["bad", n === 1
      ? t("verdict.noGridOne")
      : t("verdict.noGrid", { count: n })];
  }
  const rate = a.wrong_known / a.known_total;
  const seated = rate <= 0.01 && a.timing >= 100;
  if (a.ok && seated) return ["ok", t("verdict.clean")];
  if (a.ok) return ["ok", t("verdict.recovered")];
  if (rate > 0.05 || a.timing < 100) {
    return ["bad", t("verdict.geometry")];
  }
  if (informationGone(a)) {
    return ["bad", t("verdict.informationGone", { count: a.images_given })];
  }
  return ["warn", t("verdict.outOfReach")];
}

function renderAnswer(a) {
  lastSolved = !!a.ok;
  companionDetail.payloadReady = false;
  $("results").classList.remove("hidden");
  $("payload").classList.remove("hidden");
  liveGrid = null;
  if (!a.ok) settledGrid = null;
  const single = loaded.length === 1;
  draw(single && !picked.length ? a.finders : null);
  $("canvasNote").textContent = single
    ? "" : t("result.showingFirst", { count: loaded.length });

  const [cls, text] = verdictFor(a);
  const verdict = $("verdict");
  verdict.className = `verdict ${cls}`;
  verdict.textContent = text;

  const rows = [];
  const push = (k, v, klass) =>
    rows.push(
      `<dt>${escapeHtml(k)}</dt><dd${klass ? ` class="${escapeHtml(klass)}"` : ""}>${escapeHtml(String(v))}</dd>`
    );

  push(t("metrics.image"), `${a.width} × ${a.height} px`);
  if (a.source === "direct") {
    push(t("metrics.route"), t("metrics.directReader"));
  } else {
    push(t("metrics.finders"), a.finders.length, a.finders.length >= 3 ? "" : "bad");
  }
  if (a.modules) {
    push(t("metrics.version"), t("metrics.versionValue", {
      version: a.version,
      modules: a.modules,
    }));
    const rate = a.wrong_known / a.known_total;
    push(t("metrics.knownWrong"), `${a.wrong_known} / ${a.known_total}`,
         rate > 0.05 ? "bad" : rate > 0.01 ? "warn" : "ok");
    push(t("metrics.timing"), `${a.timing} %`, a.timing < 100 ? "warn" : "ok");
    push(t("metrics.uncertain"), `${a.uncertain} / ${a.modules * a.modules}`);
    push(t("metrics.decodeAttempts"), a.candidates_tried);
    if (a.repair) push(t("metrics.reedSolomon"), a.repair);
  }
  if (a.fusion) {
    push(t("metrics.photographsFused"), a.fusion.photographs);
    const worst = Math.min(...a.fusion.agreement.slice(1));
    if (isFinite(worst)) push(t("metrics.agreement"), t("metrics.agreementLowest", {
      percent: (worst * 100).toFixed(1),
    }));
    push(t("metrics.cellsInDispute"), a.fusion.disagreeing);
    if (a.fusion.rejected.length)
      push(t("metrics.dropped"), t("metrics.droppedValue", {
        count: a.fusion.rejected.length,
      }), "warn");
    if (a.fusion.mirrored.length)
      push(t("metrics.mirrored"), t("metrics.mirroredValue", {
        count: a.fusion.mirrored.length,
      }));
  }
  $("metrics").innerHTML = rows.join("");

  const payload = $("payload");
  payload.classList.toggle("miss", !a.ok);
  if (a.ok) {
    // Identify only formats evidenced by the recovered bytes. Product, brand and purpose remain
    // unknown unless the payload itself says otherwise; plain text is a valid, honest answer.
    let knowledge = "";
    if (a.payload_info) {
      const rows = Object.entries(a.payload_info.fields)
        .filter(([key]) => key !== "warning")
        .map(([key, value]) =>
          `<dt>${escapeHtml(key.replace(/_/g, " "))}</dt><dd>${escapeHtml(String(value))}</dd>`)
        .join("");
      knowledge =
        `<div class="knowledge"><div class="payload-kind">${escapeHtml(a.payload_info.label)}</div>
         <div class="note">${escapeHtml(a.payload_info.hint)}</div>
         <dl>${rows}</dl>
         <div class="note quiet">${escapeHtml(a.payload_info.fields.warning || "")}</div></div>`;
    }
    // A result that took thousands of attempts or leaned on erasures is honest work, not a
    // lie -- but Reed-Solomon can produce valid-and-wrong answers, and a confidently wrong
    // install code costs more than none. One sentence buys the check that settles it.
    const caveat = a.candidates_tried > 100
      ? `<div class="note"><span class="warn">${escapeHtml(t("result.hardWon", {
          count: Number(a.candidates_tried),
        }))}</span> ${escapeHtml(t("result.verifyAdvice"))}</div>`
      : "";
    payload.innerHTML =
      `<h2 id="resultHeading" class="label" tabindex="-1" style="color:var(--pink)">${escapeHtml(t("result.recovered", {
        count: a.text.length,
      }))}</h2>
       <code>${escapeHtml(a.text)}</code>${knowledge}${caveat}
       <div class="actions"><button id="copy">${escapeHtml(t("action.copy"))}</button></div>`;
    $("copy").addEventListener("click", async () => {
      const button = $("copy");
      try { await navigator.clipboard.writeText(a.text); button.textContent = t("clipboard.copied"); }
      catch { button.textContent = t("clipboard.failure"); }
      setTimeout(() => { button.textContent = t("clipboard.copy"); }, 1600);
    });
    $("resultHeading").focus();
    companionDetail.payloadReady = true;
  } else {
    // The moment of failure is the one moment advice is worth anything. The order follows
    // what actually rescues photographs, measured: geometry first, then the fusion.
    const tips = [];
    if (a.finders.length < 3 && single) {
      tips.push(t("assistance.photographCloser"));
    }
    if (single) {
      tips.push(t("assistance.markFinders"));
    }
    if (informationGone(a)) {
      tips.push(t("assistance.informationLimited"));
    } else {
      tips.push(t("assistance.morePhotographs"));
    }
    payload.innerHTML =
      `<h2 id="resultHeading" class="label" tabindex="-1" style="color:var(--bad)">${escapeHtml(t("result.notRecovered"))}</h2>
       <div class="note">${escapeHtml(a.failure || t("result.unknownReason"))}</div>
       <ul class="tips">${tips.map((tip) => `<li>${escapeHtml(tip)}</li>`).join("")}</ul>
       <div class="actions"><button id="addMore">${escapeHtml(t("action.addPhotographs"))}</button></div>`;
    $("addMore").addEventListener("click", () => fileInput.click());
  }

  const offerManual = single && !a.ok;
  $("retry").hidden = !offerManual || picking;
  $("outlineRetry").hidden = !offerManual || outlineEditing;
  $("outlineSolve").hidden = true;
  $("cancel").hidden = true;

  const images = $("images");
  images.innerHTML = "";
  if (a.reconstructed_png)
    images.appendChild(panel(t("panel.recoveredMatrix"), a.reconstructed_png, "reconstructed.png",
      t("panel.recoveredMatrixNote")));
  if (a.clean_png)
    images.appendChild(panel(t("panel.cleanMatrix"), a.clean_png, "qrsalvage.png",
      t("panel.cleanMatrixNote")));

  $("grid").textContent = a.grid || t("result.noGridSampled");

  token = a.token || null;
  $("exports").classList.toggle("hidden", !a.exportable);
  // Plain text is identified for the result card but has no component fields to export.
  $("splitRow").style.display = a.ok && a.payload_info && a.payload_info.kind !== "text"
    ? "flex" : "none";
}

async function download(format) {
  if (!token || document.body.classList.contains("busy")) return;
  const owner = Symbol("export");
  document.body.classList.add("busy");
  progressWorking(owner);
  status.textContent = t("export.preparing", { format: format.toUpperCase() });
  announce(t("export.preparingAnnouncement", { format: format.toUpperCase() }));
  let file;
  try {
    file = await window.qrBackend.file("export", {
      token,
      format,
      size_mm: parseFloat($("sizeMm").value) || 40,
      ecc: $("ecc").value || null,
      split: $("split").checked,
    });
  } catch (err) {
    if (progressIdle(owner)) {
      document.body.classList.remove("busy");
      status.textContent = t("export.failure", { message: err.message });
      announce(t("export.failureAnnouncement"));
    }
    return;
  }
  if (progressOwner !== owner) return;
  const url = URL.createObjectURL(file.blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = file.filename || `qrsalvage.${format}`;
  link.click();
  URL.revokeObjectURL(url);
  document.body.classList.remove("busy");
  progressComplete(t("export.downloaded", { format: format.toUpperCase() }));
}

for (const button of document.querySelectorAll("#exports button")) {
  button.addEventListener("click", () => download(button.dataset.format));
}

function panel(title, dataUrl, filename, note) {
  const div = document.createElement("div");
  div.className = "panel";
  div.innerHTML = `<h2>${escapeHtml(title)}</h2><img src="${escapeHtml(dataUrl)}" alt="${escapeHtml(title)}">
    <div class="note">${escapeHtml(note || "")}</div>
    <div class="actions"><a download="${escapeHtml(filename)}" href="${escapeHtml(dataUrl)}"><button>${escapeHtml(t("export.downloadPng"))}</button></a></div>`;
  return div;
}

$("retry").addEventListener("click", () => {
  companionDetail.assistance = "finders";
  dispatchStudio({ type: "ASSISTANCE_REQUIRED" });
  clearOutlineEditor(false);
  picked = []; picking = true; draw();
  $("retry").hidden = true;
  $("outlineRetry").hidden = true;
  $("cancel").hidden = false;
  $("canvasNote").textContent = t("manual.finderInstructions");
});

$("outlineRetry").addEventListener("click", () => {
  companionDetail.assistance = "outline";
  dispatchStudio({ type: "ASSISTANCE_REQUIRED" });
  picked = []; picking = false;
  outlineEditing = true;
  outlineCorners = [];
  outlineMidpoints = [];
  outlineDrag = null;
  outlineKeyboardCursor = nextOutlineKeyboardCursor();
  outlineKeyboardHandle = null;
  canvas.classList.add("outline-editing");
  canvas.classList.remove("outline-ready", "outline-dragging");
  $("retry").hidden = true;
  $("outlineRetry").hidden = true;
  $("outlineSolve").hidden = true;
  $("cancel").hidden = false;
  updateOutlineInstructions();
  draw();
  canvas.focus();
});

$("outlineSolve").addEventListener("click", () => {
  if (!outlineEditing || outlineCorners.length !== 4 || outlineMidpoints.length !== 4) return;
  const outlineHint = {
    corners: outlineCorners.map((point) => ({ ...point })),
    edgeMidpoints: outlineMidpoints.map((point) => ({ ...point })),
  };
  freezeOutlineEditor();
  $("outlineSolve").hidden = true;
  $("cancel").hidden = true;
  $("canvasNote").textContent = t("manual.outlineReady");
  draw();
  solve(null, outlineHint);
});

$("cancel").addEventListener("click", () => {
  picked = []; picking = false;
  clearOutlineEditor(false);
  draw();
  $("cancel").hidden = true;
  $("retry").hidden = false;
  $("outlineRetry").hidden = false;
  $("canvasNote").textContent = "";
});

function escapeHtml(s) {
  return String(s).replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
}
