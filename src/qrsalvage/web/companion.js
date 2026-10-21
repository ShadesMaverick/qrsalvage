(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
    return;
  }
  root.qrCompanion = api;
})(typeof window === "undefined" ? globalThis : window, function () {
  "use strict";

  const POSE_FOR_PHASE = Object.freeze({
    welcome: Object.freeze(["idle", "hero"]),
    ready: Object.freeze(["point", "studio"]),
    preparing: Object.freeze(["inspect", "progress"]),
    recovering: Object.freeze(["walk", "canvas"]),
    assistance: Object.freeze(["point", "manual"]),
    success: Object.freeze(["celebrate", "result"]),
    failure: Object.freeze(["inspect", "recovery"]),
  });
  const POSE_POSITION = Object.freeze({
    idle: "0%", walk: "20%", point: "60%", inspect: "80%", celebrate: "100%",
  });
  const HINT_KEYS = Object.freeze(["companion.finders", "companion.outline"]);

  // These are the only runtime-selected locale keys in this module. Keeping the finite set
  // beside the consumer lets the repository-wide locale gate catch a missing translation.
  // DYNAMIC-LOCALE-CONSUMERS: START
  const COMPANION_HINT_KEYS = Object.freeze(["companion.finders", "companion.outline"]);
  // DYNAMIC-LOCALE-CONSUMERS: END

  function companionDecision(state, memory = {}) {
    const [pose, anchor] = POSE_FOR_PHASE[state.phase] || POSE_FOR_PHASE.welcome;
    const hintKey = state.phase === "assistance" && state.assistance
      ? `companion.${state.assistance}`
      : null;
    const seenHints = Array.isArray(memory.seenHints) ? memory.seenHints : [];
    return {
      pose,
      anchor,
      hintKey: hintKey && !seenHints.includes(hintKey) ? hintKey : null,
      offerDonation: state.phase === "success" && state.payloadReady === true &&
        !memory.donationShown,
      motion: state.reducedMotion ? "still" : "active",
    };
  }

  function readMemory(local, session) {
    return {
      seenHints: HINT_KEYS.filter((key) => local.get(`qrsalvage.hints.${key}`) === "true"),
      donationShown: session.get("qrsalvage.donationShown") === "true",
    };
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>"]/g, (character) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[character]);
  }

  function createCompanionController({ root, bubble, anchors, t, local, session, media }) {
    const sprite = root.querySelector("#companionSprite");
    let currentAnimation = null;
    let observer = null;
    let currentTarget = null;
    let currentRectangle = null;
    let currentPlacement = null;
    let currentDecision = null;
    let activeBubble = null;

    function moveTo(anchor, motion) {
      const target = anchors[anchor];
      currentAnimation?.cancel();
      currentAnimation = null;
      if (!target) return;
      if (target !== currentTarget) {
        currentTarget = target;
        currentRectangle = target.getBoundingClientRect();
      }
      const rootWidth = root.offsetWidth || 96;
      const rootHeight = root.offsetHeight || 96;
      const bubbleLeft = bubble.hidden ? 0 : bubble.offsetLeft;
      const bubbleTop = bubble.hidden ? 0 : bubble.offsetTop;
      const bubbleWidth = bubble.hidden ? 0 : bubble.offsetWidth;
      const bubbleHeight = bubble.hidden ? 0 : bubble.offsetHeight;
      const placement = [
        anchor, bubble.hidden, bubbleLeft, bubbleTop, bubbleWidth, bubbleHeight,
      ].join(":");
      if (placement === currentPlacement) return;
      currentPlacement = placement;
      const leftExtent = Math.min(0, bubbleLeft);
      const rightExtent = Math.max(rootWidth, bubbleLeft + bubbleWidth);
      const topExtent = Math.min(0, bubbleTop);
      const bottomExtent = Math.max(rootHeight, bubbleTop + bubbleHeight);
      const rectangle = currentRectangle;
      const viewport = root.ownerDocument.defaultView;
      const clamp = (value, minimum, maximum) =>
        Math.max(minimum, Math.min(value, Math.max(minimum, maximum)));
      const x = clamp(
        rectangle.right - rootWidth + 8,
        8 - leftExtent,
        viewport.innerWidth - 8 - rightExtent,
      );
      const y = clamp(
        rectangle.top + 16,
        8 - topExtent,
        viewport.innerHeight - 8 - bottomExtent,
      );
      const nextTransform = `translate3d(${Math.round(x)}px, ${Math.round(y)}px, 0)`;
      if (motion === "still" || typeof root.animate !== "function") {
        root.style.transform = nextTransform;
        return;
      }
      const previousTransform = viewport.getComputedStyle(root).transform;
      root.style.transform = nextTransform;
      currentAnimation = root.animate(
        [
          { transform: previousTransform === "none" ? nextTransform : previousTransform },
          { transform: nextTransform },
        ],
        { duration: 260, easing: "cubic-bezier(.2,.8,.2,1)" },
      );
    }

    function hideBubble() {
      bubble.hidden = true;
      bubble.replaceChildren();
      activeBubble = null;
    }

    function renderHint(decision) {
      if (activeBubble?.kind === "hint" && activeBubble.key === decision.hintKey) return;
      bubble.innerHTML = `<p>${escapeHtml(t(decision.hintKey))}</p>` +
        `<button type="button">${escapeHtml(t("companion.dismiss"))}</button>`;
      bubble.querySelector("button").addEventListener("click", () =>
        dismissHint(decision.hintKey));
      bubble.hidden = false;
      activeBubble = { kind: "hint", key: decision.hintKey, anchor: decision.anchor };
    }

    function renderDonation(decision) {
      if (activeBubble?.kind === "donation") return;
      session.set("qrsalvage.donationShown", "true");
      bubble.innerHTML = `<p>${escapeHtml(t("donation.successPrompt"))}</p>` +
        `<div class="companion-actions">` +
        `<a href="https://ko-fi.com/shadesmaverick" target="_blank" ` +
        `rel="noopener noreferrer">${escapeHtml(t("donation.action"))}</a>` +
        `<button type="button">${escapeHtml(t("donation.dismiss"))}</button></div>`;
      bubble.querySelector("button").addEventListener("click", hideBubble);
      bubble.hidden = false;
      activeBubble = { kind: "donation", anchor: decision.anchor };
    }

    function renderDecision(decision) {
      currentDecision = decision;
      root.dataset.pose = decision.pose;
      root.dataset.motion = decision.motion;
      sprite.style.backgroundPosition = POSE_POSITION[decision.pose] || POSE_POSITION.idle;
      if (decision.offerDonation) {
        renderDonation(decision);
      } else if (decision.hintKey && COMPANION_HINT_KEYS.includes(decision.hintKey)) {
        renderHint(decision);
      } else if (activeBubble && activeBubble.anchor !== decision.anchor) {
        hideBubble();
      }
      moveTo(decision.anchor, decision.motion);
    }

    function update(state) {
      const reducedMotion = media.matches || local.get("qrsalvage.motionReduced") === "true";
      const decision = companionDecision({ ...state, reducedMotion }, readMemory(local, session));
      renderDecision(decision);
      return decision;
    }

    function dismissHint(key) {
      local.set(`qrsalvage.hints.${key}`, "true");
      hideBubble();
    }

    const reverseAnchors = new Map(
      Object.entries(anchors).map(([name, element]) => [element, name]),
    );
    const IntersectionObserver = root.ownerDocument.defaultView.IntersectionObserver;
    if (typeof IntersectionObserver === "function") {
      observer = new IntersectionObserver((entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((left, right) => right.intersectionRatio - left.intersectionRatio);
        if (!currentDecision || !visible.length) return;
        const preferred = visible.find(
          (entry) => reverseAnchors.get(entry.target) === currentDecision.anchor,
        );
        const target = preferred || visible[0];
        moveTo(reverseAnchors.get(target.target), currentDecision.motion);
      }, { threshold: [0.2, 0.6] });
      for (const anchor of Object.values(anchors)) observer.observe(anchor);
    }

    function destroy() {
      root.dataset.motion = "still";
      const animations = new Set(
        typeof root.getAnimations === "function" ? root.getAnimations({ subtree: true }) : [],
      );
      if (currentAnimation) animations.add(currentAnimation);
      for (const animation of animations) animation.cancel();
      currentAnimation = null;
      observer?.disconnect();
    }

    return { update, dismissHint, destroy };
  }

  return { companionDecision, createCompanionController };
});
