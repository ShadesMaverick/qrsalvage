/* The interface's single script. Split from index.html for one reason only: a
   1200-line file was the largest mental hurdle in the repository. Still no build
   step -- three static files instead of one, served as they are. An external file
   also lets the Content-Security-Policy say script-src 'self' with no inline-hash
   machinery behind it. */

"use strict";
const $ = (id) => document.getElementById(id);

/* Where the thanks go, once the accounts exist. Fill in the URLs — for example
   "https://ko-fi.com/yourname" and "https://liberapay.com/yourname" — and the card appears;
   empty URLs keep the page silent about money. The ask lives on the success card and nowhere
   else: a donation is reciprocity, and reciprocity has a moment. It shares its sentence with
   the privacy fact because that answers the unspoken question of what this tool lives on. */
const DONATE = [
  // PayPal first: for a German audience it is the button people recognise and already have.
  { label: "PayPal", url: "" },      // e.g. "https://paypal.me/yourname"
  { label: "Ko-fi", url: "https://ko-fi.com/shadesmaverick" },
  { label: "LiberaPay", url: "" },   // e.g. "https://liberapay.com/yourname"
];

function thanksHtml() {
  const targets = DONATE.filter((d) => d.url);
  if (!targets.length) return "";
  const links = targets
    .map((d) => `<a href="${escapeHtml(d.url)}" target="_blank" rel="noopener noreferrer">` +
                `<button>${escapeHtml(d.label)}</button></a>`)
    .join("");
  return `<div class="thanks"><img src="axolotl.png" alt="">
    <span>${escapeHtml(window.qrBackend.privacyNote)}
    Saved your lamp? A small donation keeps the tool alive.</span>
    <span class="links">${links}</span></div>`;
}
const drop = $("drop"), fileInput = $("file"), status = $("status");
const canvas = $("photo"), ctx = canvas.getContext("2d");

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
let token = null;   // identifies the result the backend is holding for export
let seq = 0;        // solve sequence; a late answer from a superseded run must not render
let timerId = null;
let mode = "one";   // "one": several photographs of one code; "many": a catalogue
let lastSolved = false;  // a fresh drop after a success starts a fresh recovery

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
    if (!document.body.classList.contains("busy")) status.textContent = "";
    return;
  }
  const seconds = event.seconds ? ` <span class="mono">${Number(event.seconds)} s</span>` : "";
  status.innerHTML =
    `<span class="spin"></span> starting the recovery engine in ${escapeHtml(window.qrBackend.mode)}` +
    ` — ${escapeHtml(event.stage)}${seconds}` +
    `<span class="quiet"> — once only, then it stays warm</span>`;
});

/** Wait until recovering is possible at all. Answers false if it never will be. */
async function backendReady() {
  try {
    await window.qrBackend.ready;
    return true;
  } catch (err) {
    status.textContent = window.qrBackend.failurePrefix + err;
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
let torchOn = false;

if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
  $("cameraOpen").classList.remove("hidden");
}

$("cameraOpen").addEventListener("click", (e) => { e.stopPropagation(); openCamera(); });
$("cameraClose").addEventListener("click", closeCamera);
$("capture").addEventListener("click", captureBurst);
$("torch").addEventListener("click", toggleTorch);

async function openCamera() {
  if (cameraStream) return;
  try {
    cameraStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment", width: { ideal: 2560 }, height: { ideal: 1440 } },
      audio: false,
    });
  } catch (err) {
    status.textContent =
      "no camera: " + err.name + " — dropping a photograph works exactly the same";
    return;
  }
  $("cameraFeed").srcObject = cameraStream;
  $("cameraPanel").classList.remove("hidden");
  $("cameraNote").innerHTML = mode === "one"
    ? "Fill the frame with the code. One press takes <em>four frames over two seconds</em> — " +
      "move the camera slowly around the code while it counts. They are read together."
    : "Fill the frame with the code — one press, one photograph, one catalogue entry.";
  $("capture").textContent = mode === "one" ? "Capture 4 frames" : "Capture";

  // A torch helps exactly where this tool gets used: lamp sockets and dark corners.
  const track = cameraStream.getVideoTracks()[0];
  const capabilities = track.getCapabilities ? track.getCapabilities() : {};
  $("torch").classList.toggle("hidden", !capabilities.torch);
  torchOn = false;
  $("torch").textContent = "Light on";
}

function closeCamera() {
  if (cameraStream) for (const track of cameraStream.getTracks()) track.stop();
  cameraStream = null;
  $("cameraFeed").srcObject = null;
  $("cameraPanel").classList.add("hidden");
}

async function toggleTorch() {
  if (!cameraStream) return;
  torchOn = !torchOn;
  try {
    await cameraStream.getVideoTracks()[0].applyConstraints({ advanced: [{ torch: torchOn }] });
    $("torch").textContent = torchOn ? "Light off" : "Light on";
  } catch { /* not every browser lets the page at the torch; the button just stays honest */ }
}

async function captureBurst() {
  if (!cameraStream || capturing) return;
  const video = $("cameraFeed");
  if (!video.videoWidth) { $("cameraNote").textContent = "the camera is still starting…"; return; }
  capturing = true;
  const count = mode === "one" ? 4 : 1;
  for (let i = 0; i < count; i++) {
    $("cameraNote").innerHTML =
      count > 1 ? `<em>frame ${i + 1} of ${count}</em> — keep moving slowly…` : "captured.";
    const frame = document.createElement("canvas");
    frame.width = video.videoWidth;
    frame.height = video.videoHeight;
    frame.getContext("2d").drawImage(video, 0, 0);
    loaded.push({
      // JPEG, not PNG: a camera frame is noise-limited anyway, and a 2560-wide PNG would
      // make every recovery haul megabytes to the backend for nothing.
      dataUrl: frame.toDataURL("image/jpeg", 0.92),
      bitmap: await createImageBitmap(frame),
      name: `camera ${loaded.length + 1}`,
    });
    if (i < count - 1) await new Promise((resolve) => setTimeout(resolve, 700));
  }
  capturing = false;
  closeCamera();
  refresh();
  run();
}

for (const radio of document.querySelectorAll('#modeRow input')) {
  radio.addEventListener("change", () => {
    mode = radio.value;
    picked = []; picking = false;
    if (loaded.length) run();
  });
}

function run() {
  if (mode === "many") { catalogRun(); } else { solve(); }
}

drop.addEventListener("click", () => fileInput.click());
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

  // After a success a fresh drop means a fresh code: adding to a solved one is always
  // pointless, because the already-solved member wins again before anything is fused.
  if (mode === "one" && lastSolved && loaded.length) {
    releaseBitmaps(loaded);
    loaded = []; token = null; lastSolved = false;
  }

  const refused = [];
  for (const file of images) {
    try {
      const bitmap = await createImageBitmap(file);
      // iPhones photograph HEIC. Where the browser can decode it (Safari), it is transcoded
      // to JPEG here, because the recovery backend cannot read HEIC bytes. Everything else
      // travels untouched -- recompressing a crisp PNG would only cost detail.
      const transcode = /hei[cf]/i.test(file.type || "");
      loaded.push({
        dataUrl: transcode ? bitmapToJpeg(bitmap) : await readAsDataURL(file),
        bitmap,
        name: file.name,
      });
    } catch {
      // The old behaviour on an undecodable file was silence -- the drop zone did not even
      // twitch. The most common cause is an iPhone HEIC on a browser without an HEIC decoder.
      refused.push(file.name);
    }
  }
  if (refused.length) {
    status.textContent =
      `could not read: ${refused.join(", ")} — likely HEIC (iPhone). ` +
      "Export or share the photo as JPEG and drop it again.";
  }
  if (!loaded.length) return;
  picked = []; picking = false;
  refresh();
  run();
}

function resetAll() {
  seq += 1;               // orphan any solve still in flight
  busy(false);
  closeCamera();
  releaseBitmaps(loaded);
  loaded = []; picked = []; picking = false; token = null;
  $("results").classList.add("hidden");
  $("catalogPanel").classList.add("hidden");
  drop.classList.remove("compact");
  $("reset").classList.add("hidden");
  $("dropTitle").textContent = "Drop a photograph here";
  $("dropMore").innerHTML = "&nbsp;or click to choose one";
  status.textContent = "";
}

function refresh() {
  drop.classList.add("compact");
  $("reset").classList.remove("hidden");
  $("dropTitle").textContent =
    loaded.length === 1 ? "1 photograph loaded" : `${loaded.length} photographs loaded`;
  $("dropMore").textContent = " — drop more of the same code to add them";

  const thumbs = $("thumbs");
  thumbs.classList.toggle("hidden", mode === "one" && loaded.length < 2);
  thumbs.innerHTML = loaded
    .map((l, i) => `<div class="thumb"><img src="${l.dataUrl}" alt="">` +
                   `<button data-index="${i}" title="remove">×</button></div>`)
    .join("");
  for (const button of thumbs.querySelectorAll("button")) {
    button.addEventListener("click", () => {
      releaseBitmaps(loaded.splice(parseInt(button.dataset.index, 10), 1));
      picked = []; picking = false;
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
  if (liveGrid) {
    // top-left, top-right, bottom-left, bottom-right — drawn as the quadrilateral the
    // descent currently holds. Watching it snap into place IS the method.
    const order = [0, 1, 3, 2];
    ctx.beginPath();
    order.forEach((i, k) => {
      const [x, y] = liveGrid[i];
      if (k === 0) ctx.moveTo(x * scale, y * scale); else ctx.lineTo(x * scale, y * scale);
    });
    ctx.closePath();
    ctx.strokeStyle = "rgba(10, 14, 18, .85)"; ctx.lineWidth = 4.5; ctx.stroke();
    ctx.strokeStyle = "#f07ea3"; ctx.lineWidth = 2; ctx.stroke();
  }
  picked.forEach((p, i) => {
    ring(p.x * scale, p.y * scale, 11, "#f07ea3", 2.5);
    ctx.font = "600 13px ui-monospace, monospace";
    ctx.strokeStyle = "rgba(10, 14, 18, .85)"; ctx.lineWidth = 3;
    ctx.strokeText(String(i + 1), p.x * scale + 15, p.y * scale + 5);
    ctx.fillStyle = "#f07ea3";
    ctx.fillText(String(i + 1), p.x * scale + 15, p.y * scale + 5);
  });
}

function ring(x, y, r, colour, width) {
  ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.strokeStyle = "rgba(10, 14, 18, .85)"; ctx.lineWidth = width + 3; ctx.stroke();
  ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.strokeStyle = colour; ctx.lineWidth = width; ctx.stroke();
}

canvas.addEventListener("click", (e) => {
  if (!picking) return;
  const rect = canvas.getBoundingClientRect();
  const scale = parseFloat(canvas.dataset.scale);
  const x = ((e.clientX - rect.left) * (canvas.width / rect.width)) / scale;
  const y = ((e.clientY - rect.top) * (canvas.height / rect.height)) / scale;
  picked.push({ x, y });
  draw();
  $("canvasNote").innerHTML = picked.length < 3
    ? `<em>${picked.length} of 3</em> marked — click the centre of the next corner square.`
    : "Three marked, recovering…";
  if (picked.length === 3) { picking = false; solve(picked); }
});

function busy(on) {
  document.body.classList.toggle("busy", on);
  clearInterval(timerId);
  if (!on) { status.textContent = ""; return; }
  const started = Date.now();
  const together = loaded.length > 1 ? ` · reading ${loaded.length} photographs together` : "";
  status.innerHTML =
    `<span class="spin"></span> recovering… <span class="mono" id="elapsed">0 s</span>${together}` +
    `<span class="quiet"> — a large photograph can take a minute</span>`;
  timerId = setInterval(() => {
    const el = $("elapsed");
    if (el) el.textContent = Math.round((Date.now() - started) / 1000) + " s";
  }, 1000);
}

async function solve(points) {
  if (!loaded.length) return;
  const my = ++seq;
  $("catalogPanel").classList.add("hidden");
  if (!(await backendReady()) || my !== seq) return;
  busy(true);
  liveStart();
  let answer = null;
  try {
    // Every event but the last is a step of the actual recovery — the grid snapping into
    // place, the versions competing, the probe counting. The last one is the result, and it
    // is what solve() answers with.
    answer = await window.qrBackend.solve(
      { images: loaded.map((l) => l.dataUrl), finder_points: points || null },
      (event) => { if (my === seq) liveEvent(event); }
    );
  } catch (err) {
    if (my === seq) { busy(false); liveEnd(); status.textContent = window.qrBackend.failurePrefix + err; }
    return;
  }
  if (my !== seq) return;  // superseded by a newer drop; this answer belongs to old inputs
  busy(false);
  liveEnd();
  if (answer) render(answer);
}

/* --- the live view: watch the method work ------------------------------------------- */
/* Everything shown here is a true intermediate state of the recovery, not an animation
   played over a black box. The grid drawn on the photograph is the grid the descent is
   holding right now; the numbers are the numbers it is scoring. */

let liveGrid = null;      // last accepted grid, drawn onto the photograph
let liveSizes = {};       // modules -> {wrong, total, quality}
let liveFrame = false;    // requestAnimationFrame throttle
let liveChosen = null;

const STAGES = {
  image:   ['reading the photograph', null],
  finders: ['looking for finder patterns', '/method#search'],
  polarity:['trying inverted polarity', '/method#search'],
  grid:    ['fitting the grid — coordinate descent on the known cells', '/method#grid'],
  chosen:  ['version chosen', '/method#search'],
  sampled: ['sampling — a probability for every module', '/method#posterior'],
  repair:  ['Reed-Solomon with erasures', '/method#rs'],
  probe:   ['probing the least certain cells', '/method#probe'],
  member:  ['reading photographs', null],
  fusion:  ['fusing the photographs', null],
};

function liveStart() {
  liveGrid = null; liveSizes = {}; liveChosen = null;
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

function liveEnd() {
  document.body.classList.remove("watching");
  $("live").classList.add("hidden");
  $("payload").classList.remove("hidden");
  liveGrid = null;
  scheduleDraw();
}

function liveEvent(e) {
  const stage = STAGES[e.type];
  if (stage) {
    const member = e.member !== undefined ? `photograph ${e.member + 1} · ` : "";
    const extra =
      e.type === "grid" && e.phase === "bow" ? " — letting it bow" :
      e.type === "grid" && e.phase === "restart" ? " — the grid sat badly, trying a wider step" :
      e.type === "probe" ? ` — ${e.tried} of ${e.budget} attempts` :
      e.type === "repair" ? (e.method === "ladder" ? ` — ${e.step} erasures` : ` — ${e.step} sets`) :
      e.type === "member" ? ` — ${e.index + 1} of ${e.total}` : "";
    $("liveStage").innerHTML = member + (stage[1]
      ? `<a href="${stage[1]}" target="_blank">${stage[0]}</a>` : stage[0]) + escapeHtml(extra);
  }
  if (e.type === "member") { liveGrid = null; liveSizes = {}; liveChosen = null; scheduleDraw(); }
  if (e.type === "finders" && loaded.length === 1 && e.member === undefined) {
    draw(e.points);
  }
  if (e.type === "grid") {
    liveSizes[e.modules] = { wrong: e.wrong, total: e.total, quality: e.quality };
    renderRace();
    // Only the primary photograph's grid is drawn — the canvas shows that one.
    if (loaded.length === 1 || e.member === 0 || e.member === undefined) {
      liveGrid = e.corners;
      scheduleDraw();
    }
  }
  if (e.type === "chosen") { liveChosen = e.modules; renderRace(); }
  if (e.type === "sampled" && e.posterior) { renderHeat(e); }
}

function renderRace() {
  const sizes = Object.keys(liveSizes).map(Number).sort((a, b) => a - b);
  const rows = sizes.map((m) => {
    const s = liveSizes[m];
    const share = Math.min(s.wrong / Math.max(s.total, 1) / 0.4, 1);
    const width = 4 + Math.round(76 * share);
    const best = liveChosen === m ? " best" : "";
    return `<dt>${Number(m)} modules</dt>` +
           `<dd><span class="racebar${best}" style="width:${width}px"></span>` +
           `${Number(s.wrong)} / ${Number(s.total)} wrong</dd>`;
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
  $("heatNote").textContent =
    `what the machine sees: ${e.modules}×${e.modules} cells, ` +
    `${e.uncertain} uncertain (red), ${e.wrong_known} known cells wrong`;
}

function scheduleDraw() {
  if (liveFrame) return;
  liveFrame = true;
  requestAnimationFrame(() => { liveFrame = false; draw(); });
}

/* --- catalogue mode: every photograph its own code ---------------------------------- */

function titleFrom(name) {
  return (name || "").replace(/\.[^.]+$/, "").replace(/[-_]+/g, " ").trim() || "untitled";
}

async function catalogRun() {
  const my = ++seq;
  $("results").classList.add("hidden");
  $("catalogPanel").classList.remove("hidden");
  if (!(await backendReady()) || my !== seq) return;
  document.body.classList.add("busy");

  // One photograph at a time, so the progress is real rather than a guess — and a photograph
  // already recovered in this session is not recovered again when one more lands in the pile.
  const pending = loaded.filter((l) => !l.result);
  let done = 0;
  for (const item of pending) {
    status.innerHTML =
      `<span class="spin"></span> recovering ${++done} of ${pending.length}… ` +
      `<span class="quiet">${escapeHtml(item.name)}</span>`;
    catalogRender();
    try {
      // A catalogue narrates its own progress card by card, so the events of the single
      // recovery running right now have nowhere to go.
      const answer = await window.qrBackend.solve({ images: [item.dataUrl] }, () => {});
      if (my !== seq) return;
      item.result = answer;
    } catch (err) {
      if (my !== seq) return;
      status.textContent = window.qrBackend.failurePrefix + err;
      document.body.classList.remove("busy");
      return;
    }
  }
  if (my !== seq) return;
  status.textContent = "";
  document.body.classList.remove("busy");
  catalogRender();
}

function catalogRender() {
  const seen = new Map();  // payload text -> index of the first card that carries it
  const cards = loaded.map((item, index) => {
    const r = item.result;
    if (item.title === undefined) item.title = titleFrom(item.name);
    if (!r) {
      return `<div class="card"><span class="state quiet">waiting…</span>
        <img src="${item.dataUrl}" alt=""></div>`;
    }
    if (!r.ok) {
      return `<div class="card miss"><span class="state bad">not recovered</span>
        <img src="${item.dataUrl}" alt="">
        <div class="snippet">${escapeHtml(item.name)} — ${escapeHtml(r.failure || "")}.
        Several photographs of it, read together in the other mode, often succeed.</div></div>`;
    }
    const first = seen.get(r.text);
    if (first !== undefined) {
      return `<div class="card dup"><span class="state quiet">same code as
        “${escapeHtml(loaded[first].title)}” — folded into one entry</span>
        <img src="${item.dataUrl}" alt=""></div>`;
    }
    seen.set(r.text, index);
    return `<div class="card"><span class="state ok">recovered</span>
      ${r.clean_png ? `<img src="${r.clean_png}" alt="">` : ""}
      <input class="title" data-index="${index}" value="${escapeHtml(item.title)}"
        placeholder="what is this code, to you?">
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
  const seen = new Set();
  const entries = [];
  for (const item of loaded) {
    const r = item.result;
    if (!r || !r.ok || seen.has(r.text)) continue;
    seen.add(r.text);
    const note = (r.version ? `version ${r.version}` : "") +
      (r.ecc ? ` · error correction ${r.ecc}` : "") + ` · ${r.text.length} characters`;
    entries.push({ title: item.title || titleFrom(item.name), text: r.text,
                   ecc: r.ecc || null, note: note.replace(/^ · /, "") });
  }
  if (!entries.length) return;
  let file;
  try {
    file = await window.qrBackend.file("catalog", {
      entries,
      size_mm: parseFloat($("catalogSizeMm").value) || 50,
    });
  } catch (err) {
    status.textContent = "catalogue failed: " + err.message;
    return;
  }
  const url = URL.createObjectURL(file.blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = file.filename || "catalog.pdf";
  link.click();
  URL.revokeObjectURL(url);
  $("catalogThanks").innerHTML = thanksHtml();
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
  if (!a.modules) {
    const n = a.finders.length;
    return ["bad", `no grid — ${n} finder candidate${n === 1 ? "" : "s"} found`];
  }
  const rate = a.wrong_known / a.known_total;
  const seated = rate <= 0.01 && a.timing >= 100;
  if (a.ok && seated) return ["ok", "grid seated cleanly — the payload fell out almost by itself"];
  if (a.ok) return ["ok", "recovered — the numbers below say how hard it fought"];
  if (rate > 0.05 || a.timing < 100) {
    return ["bad", "the grid did not seat — none of the cell counts below can be trusted yet"];
  }
  if (informationGone(a)) {
    return ["bad", `the grid is clean across ${a.images_given} photographs and the data still ` +
      "does not read — that usually means modules are physically gone. Only a genuinely " +
      "different view of the damaged area might help; more of the same will not"];
  }
  return ["warn", "the grid seats but the payload is out of reach — more photographs are the strongest lever"];
}

function render(a) {
  lastSolved = !!a.ok;
  $("results").classList.remove("hidden");
  $("payload").classList.remove("hidden");
  liveGrid = null;
  const single = loaded.length === 1;
  draw(single && !picked.length ? a.finders : null);
  $("canvasNote").textContent = single
    ? "" : `showing the first photograph — ${loaded.length} are read together`;

  const [cls, text] = verdictFor(a);
  const verdict = $("verdict");
  verdict.className = `verdict ${cls}`;
  verdict.textContent = text;

  const rows = [];
  const push = (k, v, klass) =>
    rows.push(
      `<dt>${escapeHtml(k)}</dt><dd${klass ? ` class="${klass}"` : ""}>${escapeHtml(String(v))}</dd>`
    );

  push("image", `${a.width} × ${a.height} px`);
  push("finders", a.finders.length, a.finders.length >= 3 ? "" : "bad");
  if (a.modules) {
    push("version", `${a.version} · ${a.modules} modules`);
    const rate = a.wrong_known / a.known_total;
    push("known cells wrong", `${a.wrong_known} / ${a.known_total}`,
         rate > 0.05 ? "bad" : rate > 0.01 ? "warn" : "ok");
    push("timing pattern", `${a.timing} %`, a.timing < 100 ? "warn" : "ok");
    push("uncertain", `${a.uncertain} / ${a.modules * a.modules}`);
    push("decode attempts", a.candidates_tried);
    if (a.repair) push("reed-solomon", a.repair);
  }
  if (a.fusion) {
    push("photographs fused", a.fusion.photographs);
    const worst = Math.min(...a.fusion.agreement.slice(1));
    if (isFinite(worst)) push("agreement", `${(worst * 100).toFixed(1)} % (lowest)`);
    push("cells in dispute", a.fusion.disagreeing);
    if (a.fusion.rejected.length)
      push("dropped", `${a.fusion.rejected.length} — did not match the best reading`, "warn");
    if (a.fusion.mirrored.length)
      push("mirrored", `${a.fusion.mirrored.length}, turned back`);
  }
  $("metrics").innerHTML = rows.join("");

  const payload = $("payload");
  payload.classList.toggle("miss", !a.ok);
  if (a.ok) {
    // The follow-up question, answered in place: what is this, and where does one type it.
    // For Matter the derived manual pairing code is the star -- it exists precisely for the
    // case where scanning is not an option, which is this tool's entire audience.
    let knowledge = "";
    if (a.payload_info) {
      const rows = Object.entries(a.payload_info.fields)
        .filter(([key]) => key !== "warning")
        .map(([key, value]) =>
          `<dt>${escapeHtml(key.replace(/_/g, " "))}</dt><dd>${escapeHtml(String(value))}</dd>`)
        .join("");
      knowledge =
        `<div class="knowledge"><div class="note">${escapeHtml(a.payload_info.hint)}</div>
         <dl>${rows}</dl>
         <div class="note quiet">${escapeHtml(a.payload_info.fields.warning || "")}</div></div>`;
    }
    // A result that took thousands of attempts or leaned on erasures is honest work, not a
    // lie -- but Reed-Solomon can produce valid-and-wrong answers, and a confidently wrong
    // install code costs more than none. One sentence buys the check that settles it.
    const caveat = a.candidates_tried > 100
      ? `<div class="note"><span class="warn">Hard-won (${Number(a.candidates_tried)} attempts).</span>
         Before typing a secret anywhere, scan the re-encoded code below with your own phone
         and check it shows the same text.</div>`
      : "";
    payload.innerHTML =
      `<div class="label" style="color:var(--pink)">recovered · ${a.text.length} characters</div>
       <code>${escapeHtml(a.text)}</code>${knowledge}${caveat}
       <div class="actions"><button id="copy">Copy</button></div>${thanksHtml()}`;
    $("copy").addEventListener("click", async () => {
      const button = $("copy");
      try { await navigator.clipboard.writeText(a.text); button.textContent = "copied ✓"; }
      catch { button.textContent = "copy failed — select the text"; }
      setTimeout(() => { button.textContent = "Copy"; }, 1600);
    });
  } else {
    // The moment of failure is the one moment advice is worth anything. The order follows
    // what actually rescues photographs, measured: geometry first, then the fusion.
    const tips = [];
    if (a.finders.length < 3 && single) {
      tips.push("Photograph closer, or crop away the surroundings — a busy background is the " +
                "most common reason the finder search comes up short.");
    }
    if (single) {
      tips.push("Mark the three corner squares by hand — the button under the photograph. " +
                "Roughly is enough.");
    }
    if (informationGone(a)) {
      tips.push(`This looks <em>information-limited, not geometry-limited</em>: the grid sits
                 cleanly and still nothing reads. If part of the label is scratched away or
                 missing, no amount of photographs restores it — only a view that shows those
                 modules intact would.`);
    } else {
      tips.push(`Add two or three <em>more photographs of the same code</em> — different angle,
               different light. They are read together, and photographs that fail alone
               regularly decode as a group.`);
    }
    payload.innerHTML =
      `<div class="label" style="color:var(--bad)">not recovered</div>
       <div class="note">${escapeHtml(a.failure || "unknown reason")}</div>
       <ul class="tips">${tips.map((t) => `<li>${t}</li>`).join("")}</ul>
       <div class="actions"><button id="addMore">Add photographs</button></div>`;
    $("addMore").addEventListener("click", () => fileInput.click());
  }

  const offerManual = single && (!a.ok || a.finders.length < 3);
  $("retry").classList.toggle("hidden", !offerManual || picking);
  $("cancel").classList.add("hidden");

  const images = $("images");
  images.innerHTML = "";
  if (a.reconstructed_png)
    images.appendChild(panel("Recovered matrix", a.reconstructed_png, "reconstructed.png",
      "As sampled from the photograph — repaired cells included."));
  if (a.clean_png)
    images.appendChild(panel("Re-encoded · standards clean", a.clean_png, "qrsalvage.png",
      "Freshly encoded from the recovered text. <em>This is the one to print.</em>"));

  $("grid").textContent = a.grid || "(no grid sampled)";

  token = a.token || null;
  $("exports").classList.toggle("hidden", !a.exportable);
  // The split is only offered when there is a recognised payload to split.
  $("splitRow").style.display = a.ok && a.payload_info ? "flex" : "none";
}

async function download(format) {
  if (!token) return;
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
    status.textContent = "export failed: " + err.message;
    return;
  }
  const url = URL.createObjectURL(file.blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = file.filename || `qrsalvage.${format}`;
  link.click();
  URL.revokeObjectURL(url);
}

for (const button of document.querySelectorAll("#exports button")) {
  button.addEventListener("click", () => download(button.dataset.format));
}

function panel(title, dataUrl, filename, note) {
  const div = document.createElement("div");
  div.className = "panel";
  div.innerHTML = `<h2>${title}</h2><img src="${dataUrl}" alt="${title}">
    <div class="note">${note || ""}</div>
    <div class="actions"><a download="${filename}" href="${dataUrl}"><button>Download PNG</button></a></div>`;
  return div;
}

$("retry").addEventListener("click", () => {
  picked = []; picking = true; draw();
  $("retry").classList.add("hidden");
  $("cancel").classList.remove("hidden");
  $("canvasNote").innerHTML =
    "Click the centre of each of the three large corner squares, <em>in any order</em>. " +
    "Roughly is enough — the click only picks the candidate, the position comes from the image.";
});
$("cancel").addEventListener("click", () => {
  picked = []; picking = false; draw();
  $("cancel").classList.add("hidden");
  $("retry").classList.remove("hidden");
  $("canvasNote").textContent = "";
});

function escapeHtml(s) {
  return String(s).replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
}
