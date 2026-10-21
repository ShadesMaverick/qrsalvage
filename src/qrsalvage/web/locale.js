(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
    return;
  }

  let storage;
  let stored = null;
  try { storage = root.localStorage; } catch { storage = null; }
  try { stored = storage ? storage.getItem("qrsalvage.locale") : null; } catch { stored = null; }
  const preferred = Array.isArray(root.navigator.languages)
    ? root.navigator.languages
    : (root.navigator.language ? [root.navigator.language] : []);
  const controller = api.createLocaleController({
    locale: api.chooseLocale(stored, preferred),
    document: root.document,
    storage,
  });
  const browserApi = {
    ...api,
    t: controller.t,
    setLocale: controller.setLocale,
    apply: controller.apply,
  };
  Object.defineProperty(browserApi, "locale", { get: () => controller.locale });
  root.qrLocale = browserApi;
})(typeof window === "undefined" ? globalThis : window, function () {
  "use strict";

  const en = {
    "a11y.skip": "Skip to the tool",
    "nav.studio": "Studio",
    "nav.method": "Method",
    "nav.github": "GitHub",
    "nav.privacy": "Privacy",
    "mode.easy": "Easy",
    "mode.pro": "Pro",
    "hero.eyebrow": "Recover the signal",
    "hero.title": "A damaged QR code is still data.",
    "hero.lead": "Reconstruct curved, faded and incomplete codes entirely on your device.",
    "hero.action": "Open Signal Studio",
    "studio.eyebrow": "Signal Studio",
    "studio.title": "Reconstruction workspace",
    "method.title": "From damaged image to verified payload",
    "method.find": "Find the grid",
    "method.measure": "Measure uncertainty",
    "method.verify": "Verify the reconstruction",
    "situations.title": "Built for difficult surfaces",
    "privacy.title": "Private by construction, open by default",
    "stage.input": "Input",
    "stage.geometry": "Geometry",
    "stage.recover": "Recover",
    "stage.export": "Export",
    "action.choose": "Choose a photograph",
    "action.camera": "Use the camera",
    "action.reset": "Start over",
    "action.cancel": "Cancel",
    "action.copy": "Copy",
    "action.addPhotographs": "Add photographs",
    "boot.ready": "Recovery engine ready",
    "boot.starting": "Starting the recovery engine: {stage}",
    "boot.startingIn": "starting the recovery engine in {mode}",
    "boot.once": "once only, then it stays warm",
    "boot.failure": "The recovery engine could not start",
    "input.readingOne": "reading the selected photograph…",
    "input.readingMany": "reading {count} selected photographs…",
    "input.readingOneAnnouncement": "Reading the selected photograph",
    "input.readingManyAnnouncement": "Reading {count} selected photographs",
    "input.unreadable": "could not read: {names} — likely HEIC (iPhone). Export or share the photo as JPEG and drop it again.",
    "input.unreadableAnnouncement": "One or more selected photographs could not be read",
    "input.drop": "Drop a photograph here",
    "input.choose": "or click to choose one",
    "input.loadedOne": "1 photograph loaded",
    "input.loadedMany": "{count} photographs loaded",
    "input.more": "drop more of the same code to add them",
    "input.remove": "remove",
    "camera.requesting": "requesting camera access…",
    "camera.requestingAnnouncement": "Requesting camera access",
    "camera.unavailable": "no camera: {name} — dropping a photograph works exactly the same",
    "camera.unavailableAnnouncement": "Camera access failed; dropping a photograph still works",
    "camera.noteBurst": "Fill the frame with the code. One press takes four frames over two seconds — move the camera slowly around the code while it counts. They are read together.",
    "camera.noteSingle": "Fill the frame with the code — one press, one photograph, one catalogue entry.",
    "camera.captureBurst": "Capture 4 frames",
    "camera.captureSingle": "Capture",
    "camera.lightOn": "Light on",
    "camera.lightOff": "Light off",
    "camera.starting": "the camera is still starting…",
    "camera.capturing": "capturing photographs…",
    "camera.capturingAnnouncement": "Capturing photographs",
    "camera.frame": "frame {current} of {total} — keep moving slowly…",
    "camera.captured": "captured.",
    "camera.preparing": "preparing the captured photographs…",
    "camera.preparingAnnouncement": "Preparing the captured photographs",
    "camera.failure": "camera capture failed: {message}",
    "camera.failureAnnouncement": "Camera capture failed",
    "progress.photoCount": "{count} photographs are read together",
    "progress.preparing": "Preparing the recovery engine…",
    "progress.recovering": "Reading what remains…",
    "progress.readingOne": "reading the photograph",
    "progress.readingTogether": "reading {count} photographs together",
    "progress.largePhoto": "a large photograph can take a minute",
    "progress.started": "Recovery started",
    "progress.startedWarning": "Recovery started; some selected photographs could not be read",
    "progress.preparingAnnouncement": "Preparing the recovery engine",
    "progress.stage": "Recovery stage: {stage}",
    "manual.finderProgress": "{count} of 3 marked — click the centre of the next corner square.",
    "manual.findersReady": "Three marked, recovering…",
    "manual.outlineProgress": "Tap the four QR corners in order: top left, top right, bottom right, bottom left. {count} of 4 marked — next: {next}.",
    "manual.outlineAdjust": "Drag the numbered corners and the smaller diamond edge handles until the curve follows the QR code.",
    "manual.finderInstructions": "Click the centre of each of the three large corner squares, in any order. Roughly is enough — the click only picks the candidate, the position comes from the image.",
    "manual.outlineReady": "Outline marked, recovering…",
    "manual.topLeft": "top left",
    "manual.topRight": "top right",
    "manual.bottomRight": "bottom right",
    "manual.bottomLeft": "bottom left",
    "result.success": "QR code recovered",
    "result.failure": "Recovery failed",
    "result.showingFirst": "showing the first photograph — {count} are read together",
    "result.recovered": "recovered · {count} characters",
    "result.notRecovered": "not recovered",
    "result.unknownReason": "unknown reason",
    "verdict.direct": "decoded directly from the photograph — no reconstruction was needed",
    "verdict.noGrid": "no grid — {count} finder candidates found",
    "verdict.noGridOne": "no grid — 1 finder candidate found",
    "verdict.clean": "grid seated cleanly — the payload fell out almost by itself",
    "verdict.recovered": "recovered — the numbers below say how hard it fought",
    "verdict.geometry": "the grid did not seat — none of the cell counts below can be trusted yet",
    "verdict.informationGone": "the grid is clean across {count} photographs and the data still does not read — that usually means modules are physically gone. Only a genuinely different view of the damaged area might help; more of the same will not",
    "verdict.outOfReach": "the grid seats but the payload is out of reach — more photographs are the strongest lever",
    "catalogue.untitled": "untitled",
    "catalogue.preparing": "preparing the recovery engine…",
    "catalogue.preparingAnnouncement": "Preparing the recovery engine for the catalogue",
    "catalogue.preparingWarning": "Preparing the catalogue; some selected photographs could not be read",
    "catalogue.recovering": "recovering {current} of {total}…",
    "catalogue.recoveringAnnouncement": "Recovering catalogue photograph {current} of {total}",
    "catalogue.recoveryFailure": "Catalogue recovery failed",
    "catalogue.complete": "Catalogue recovery complete",
    "catalogue.preparingDownload": "preparing the catalogue download…",
    "catalogue.preparingDownloadAnnouncement": "Preparing the catalogue download",
    "catalogue.exportFailure": "catalogue failed: {message}",
    "catalogue.exportFailureAnnouncement": "Catalogue export failed",
    "catalogue.downloaded": "Catalogue downloaded",
    "export.preparing": "preparing the {format} download…",
    "export.preparingAnnouncement": "Preparing the {format} download",
    "export.failure": "export failed: {message}",
    "export.failureAnnouncement": "Export failed",
    "export.downloaded": "{format} downloaded",
    "clipboard.copied": "copied ✓",
    "clipboard.failure": "copy failed — select the text",
    "clipboard.copy": "Copy",
    "companion.outline": "I found the outline. I’ll ask only if a damaged corner needs help.",
    "companion.success": "Recovered. Your result is ready.",
    "donation.prompt": "Did qrsalvage help? You can support its development on Ko-fi.",
    "donation.action": "Support on Ko-fi",
    "donation.dismiss": "Not now",
  };

  const de = {
    "a11y.skip": "Zum Werkzeug springen",
    "nav.studio": "Studio",
    "nav.method": "Methode",
    "nav.github": "GitHub",
    "nav.privacy": "Datenschutz",
    "mode.easy": "Einfach",
    "mode.pro": "Pro",
    "hero.eyebrow": "Das Signal retten",
    "hero.title": "Ein beschädigter QR-Code enthält noch immer Daten.",
    "hero.lead": "Rekonstruiere gewölbte, verblasste und unvollständige Codes vollständig auf deinem Gerät.",
    "hero.action": "Signal Studio öffnen",
    "studio.eyebrow": "Signal Studio",
    "studio.title": "Arbeitsbereich für die Rekonstruktion",
    "method.title": "Vom beschädigten Bild zu geprüften Nutzdaten",
    "method.find": "Raster finden",
    "method.measure": "Unsicherheit messen",
    "method.verify": "Rekonstruktion prüfen",
    "situations.title": "Für schwierige Oberflächen gemacht",
    "privacy.title": "Privat konstruiert, standardmäßig offen",
    "stage.input": "Eingabe",
    "stage.geometry": "Geometrie",
    "stage.recover": "Rettung",
    "stage.export": "Export",
    "action.choose": "Foto auswählen",
    "action.camera": "Kamera verwenden",
    "action.reset": "Neu beginnen",
    "action.cancel": "Abbrechen",
    "action.copy": "Kopieren",
    "action.addPhotographs": "Fotos hinzufügen",
    "boot.ready": "Recovery-Engine bereit",
    "boot.starting": "Recovery-Engine wird gestartet: {stage}",
    "boot.startingIn": "Recovery-Engine wird in {mode} gestartet",
    "boot.once": "nur einmal, danach bleibt sie bereit",
    "boot.failure": "Die Recovery-Engine konnte nicht gestartet werden",
    "input.readingOne": "Ausgewähltes Foto wird gelesen…",
    "input.readingMany": "{count} ausgewählte Fotos werden gelesen…",
    "input.readingOneAnnouncement": "Das ausgewählte Foto wird gelesen",
    "input.readingManyAnnouncement": "{count} ausgewählte Fotos werden gelesen",
    "input.unreadable": "Nicht lesbar: {names} — wahrscheinlich HEIC (iPhone). Exportiere oder teile das Foto als JPEG und lege es erneut ab.",
    "input.unreadableAnnouncement": "Mindestens ein ausgewähltes Foto konnte nicht gelesen werden",
    "input.drop": "Foto hier ablegen",
    "input.choose": "oder zum Auswählen klicken",
    "input.loadedOne": "1 Foto geladen",
    "input.loadedMany": "{count} Fotos geladen",
    "input.more": "weitere Fotos desselben Codes hier ablegen",
    "input.remove": "entfernen",
    "camera.requesting": "Kamerazugriff wird angefragt…",
    "camera.requestingAnnouncement": "Kamerazugriff wird angefragt",
    "camera.unavailable": "Keine Kamera: {name} — ein abgelegtes Foto funktioniert genauso",
    "camera.unavailableAnnouncement": "Kamerazugriff fehlgeschlagen; ein abgelegtes Foto funktioniert weiterhin",
    "camera.noteBurst": "Fülle das Bild mit dem Code. Ein Druck nimmt vier Bilder in zwei Sekunden auf — bewege die Kamera beim Zählen langsam um den Code. Sie werden gemeinsam gelesen.",
    "camera.noteSingle": "Fülle das Bild mit dem Code — ein Druck, ein Foto, ein Katalogeintrag.",
    "camera.captureBurst": "4 Bilder aufnehmen",
    "camera.captureSingle": "Aufnehmen",
    "camera.lightOn": "Licht an",
    "camera.lightOff": "Licht aus",
    "camera.starting": "Die Kamera startet noch…",
    "camera.capturing": "Fotos werden aufgenommen…",
    "camera.capturingAnnouncement": "Fotos werden aufgenommen",
    "camera.frame": "Bild {current} von {total} — langsam weiterbewegen…",
    "camera.captured": "aufgenommen.",
    "camera.preparing": "Aufgenommene Fotos werden vorbereitet…",
    "camera.preparingAnnouncement": "Aufgenommene Fotos werden vorbereitet",
    "camera.failure": "Kameraaufnahme fehlgeschlagen: {message}",
    "camera.failureAnnouncement": "Kameraaufnahme fehlgeschlagen",
    "progress.photoCount": "{count} Fotos werden gemeinsam gelesen",
    "progress.preparing": "Recovery-Engine wird vorbereitet…",
    "progress.recovering": "Vorhandene Spuren werden gelesen…",
    "progress.readingOne": "Foto wird gelesen",
    "progress.readingTogether": "{count} Fotos werden gemeinsam gelesen",
    "progress.largePhoto": "ein großes Foto kann eine Minute dauern",
    "progress.started": "Rettung gestartet",
    "progress.startedWarning": "Rettung gestartet; einige ausgewählte Fotos konnten nicht gelesen werden",
    "progress.preparingAnnouncement": "Recovery-Engine wird vorbereitet",
    "progress.stage": "Rettungsschritt: {stage}",
    "manual.finderProgress": "{count} von 3 markiert — klicke in die Mitte des nächsten großen Eckquadrats.",
    "manual.findersReady": "Drei markiert, Rettung läuft…",
    "manual.outlineProgress": "Tippe die vier QR-Ecken der Reihe nach an: oben links, oben rechts, unten rechts, unten links. {count} von 4 markiert — als Nächstes: {next}.",
    "manual.outlineAdjust": "Ziehe die nummerierten Ecken und die kleineren rautenförmigen Kantengriffe, bis die Kurve dem QR-Code folgt.",
    "manual.finderInstructions": "Klicke in beliebiger Reihenfolge in die Mitte der drei großen Eckquadrate. Ungefähr genügt — der Klick wählt nur den Kandidaten, die Position kommt aus dem Bild.",
    "manual.outlineReady": "Umriss markiert, Rettung läuft…",
    "manual.topLeft": "oben links",
    "manual.topRight": "oben rechts",
    "manual.bottomRight": "unten rechts",
    "manual.bottomLeft": "unten links",
    "result.success": "QR-Code wiederhergestellt",
    "result.failure": "Rettung fehlgeschlagen",
    "result.showingFirst": "Das erste Foto wird gezeigt — {count} werden gemeinsam gelesen",
    "result.recovered": "wiederhergestellt · {count} Zeichen",
    "result.notRecovered": "nicht wiederhergestellt",
    "result.unknownReason": "unbekannter Grund",
    "verdict.direct": "direkt aus dem Foto decodiert — keine Rekonstruktion war nötig",
    "verdict.noGrid": "kein Raster — {count} Finder-Kandidaten gefunden",
    "verdict.noGridOne": "kein Raster — 1 Finder-Kandidat gefunden",
    "verdict.clean": "Raster sitzt sauber — die Nutzdaten ließen sich fast von selbst lesen",
    "verdict.recovered": "wiederhergestellt — die Zahlen unten zeigen, wie schwer es war",
    "verdict.geometry": "das Raster sitzt nicht — den Zellzahlen unten kann noch nicht vertraut werden",
    "verdict.informationGone": "Das Raster ist über {count} Fotos hinweg sauber und die Daten bleiben unlesbar — wahrscheinlich fehlen Module physisch. Nur eine wirklich andere Ansicht des beschädigten Bereichs könnte helfen; mehr vom Gleichen nicht",
    "verdict.outOfReach": "Das Raster sitzt, aber die Nutzdaten bleiben außer Reichweite — weitere Fotos sind der stärkste Hebel",
    "catalogue.untitled": "ohne Titel",
    "catalogue.preparing": "Recovery-Engine wird vorbereitet…",
    "catalogue.preparingAnnouncement": "Recovery-Engine für den Katalog wird vorbereitet",
    "catalogue.preparingWarning": "Katalog wird vorbereitet; einige ausgewählte Fotos konnten nicht gelesen werden",
    "catalogue.recovering": "{current} von {total} werden gerettet…",
    "catalogue.recoveringAnnouncement": "Katalogfoto {current} von {total} wird gerettet",
    "catalogue.recoveryFailure": "Katalogrettung fehlgeschlagen",
    "catalogue.complete": "Katalogrettung abgeschlossen",
    "catalogue.preparingDownload": "Katalog-Download wird vorbereitet…",
    "catalogue.preparingDownloadAnnouncement": "Katalog-Download wird vorbereitet",
    "catalogue.exportFailure": "Katalog fehlgeschlagen: {message}",
    "catalogue.exportFailureAnnouncement": "Katalogexport fehlgeschlagen",
    "catalogue.downloaded": "Katalog heruntergeladen",
    "export.preparing": "{format}-Download wird vorbereitet…",
    "export.preparingAnnouncement": "{format}-Download wird vorbereitet",
    "export.failure": "Export fehlgeschlagen: {message}",
    "export.failureAnnouncement": "Export fehlgeschlagen",
    "export.downloaded": "{format} heruntergeladen",
    "clipboard.copied": "kopiert ✓",
    "clipboard.failure": "Kopieren fehlgeschlagen — Text auswählen",
    "clipboard.copy": "Kopieren",
    "companion.outline": "Ich habe den Umriss gefunden. Nur bei einer beschädigten Ecke frage ich nach Hilfe.",
    "companion.success": "Gerettet. Dein Ergebnis ist bereit.",
    "donation.prompt": "Hat qrsalvage geholfen? Du kannst die Entwicklung auf Ko-fi unterstützen.",
    "donation.action": "Auf Ko-fi unterstützen",
    "donation.dismiss": "Nicht jetzt",
  };

  function chooseLocale(stored, preferred) {
    if (stored === "de" || stored === "en") return stored;
    return preferred.some((value) => value.toLowerCase().startsWith("de")) ? "de" : "en";
  }

  function interpolate(template, values = {}) {
    return template.replace(
      /\{([a-zA-Z0-9_]+)\}/g,
      (_, key) => String(values[key] ?? `{${key}}`),
    );
  }

  function translate(locale, key, values) {
    const dictionary = locale === "de" ? de : en;
    if (!(key in dictionary) && !(key in en)) throw new Error(`Unknown translation key: ${key}`);
    return interpolate(dictionary[key] ?? en[key], values);
  }

  function dictionaryKeys() {
    return { en: Object.keys(en).sort(), de: Object.keys(de).sort() };
  }

  function createLocaleController(options = {}) {
    const document = options.document;
    const storage = options.storage;
    let locale = options.locale === "de" ? "de" : "en";
    const t = (key, values) => translate(locale, key, values);

    function apply() {
      if (!document) return;
      document.documentElement.lang = locale;
      for (const element of document.querySelectorAll("[data-lang]")) {
        element.hidden = element.dataset.lang !== locale;
      }
      for (const button of document.querySelectorAll("[data-locale]")) {
        button.setAttribute("aria-pressed", String(button.dataset.locale === locale));
      }
      for (const element of document.querySelectorAll("[data-i18n]")) {
        element.textContent = t(element.dataset.i18n);
      }
      for (const element of document.querySelectorAll("[data-i18n-aria]")) {
        element.setAttribute("aria-label", t(element.dataset.i18nAria));
      }
    }

    function setLocale(next) {
      locale = next === "de" ? "de" : "en";
      apply();
      try { if (storage) storage.setItem("qrsalvage.locale", locale); } catch { /* memory wins */ }
      return locale;
    }

    if (document) {
      for (const button of document.querySelectorAll("[data-locale]")) {
        if (button.addEventListener) {
          button.addEventListener("click", () => setLocale(button.dataset.locale));
        }
      }
    }
    apply();
    return {
      get locale() { return locale; },
      setLocale,
      t,
      apply,
    };
  }

  return { chooseLocale, translate, dictionaryKeys, createLocaleController };
});
