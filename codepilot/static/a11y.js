"use strict";
// Everything by keyboard (spec keyboard-access). The app draws by replacing innerHTML, so roles and tab stops aren't
// written into each template: this script decorates what was drawn, by selector, and owns the keys. A new kind of
// clickable row is a selector added here. Loaded after app.js and using its helpers.

// Click-only elements: each gets a tab stop and a role, and Enter or Space clicks it (a link: Enter only). One that
// already has a tabindex has keys of its own (the plan line, Progress markers) and is left alone.
const A11Y_BUTTONS = [
  ".session", ".grep-file > .row", ".grep-hit", "#proposalList .row", "#gitList .row", ".rv-item", "#specsView .row",
  "#steeringView .row", "#traceList .row", ".welcome .link", "#sbContext", "[data-spec-open]",
];
const A11Y_LINKS = ["a.loc", ".msg.user .ref", ".attached span"];
const A11Y_ACT = [...A11Y_BUTTONS, ...A11Y_LINKS].join(",");
const A11Y_LINK = A11Y_LINKS.join(",");

const a11y = {
  pending: new Set(), frame: 0,
  last: null, // what last had focus, and how to find it again once a redraw has replaced it: { el, key, box }
};

function a11yDecorate(el) {
  if (el.hasAttribute("tabindex")) return;
  el.tabIndex = 0;
  el.setAttribute("role", el.matches(A11Y_LINK) ? "link" : "button");
  el.dataset.a11yAct = "";
}
function a11yDecorateIn(root) {
  if (root.matches(A11Y_ACT)) a11yDecorate(root);
  for (const el of root.querySelectorAll(A11Y_ACT)) a11yDecorate(el);
}

// What was drawn is decorated once a frame (a streamed reply redraws on every word) and before any key is handled,
// so a key never lands where a row isn't ready yet. Only added nodes are looked at, and never the terminal's.
function a11yFlush() {
  cancelAnimationFrame(a11y.frame); a11y.frame = 0;
  for (const root of a11y.pending) if (root.isConnected) a11yDecorateIn(root);
  a11y.pending.clear();
}
new MutationObserver((records) => {
  for (const r of records) {
    if (!r.addedNodes.length || r.target.closest?.(".xterm")) continue;
    for (const n of r.addedNodes) if (n.nodeType === 1) a11y.pending.add(n);
  }
  if (a11y.pending.size && !a11y.frame) a11y.frame = requestAnimationFrame(a11yFlush);
  a11yKeepFocus();
}).observe(document.body, { childList: true, subtree: true });
addEventListener("keydown", a11yFlush, true);
a11yDecorateIn(document.body); // what was drawn before this loaded

// Enter or Space on a decorated element clicks it. On a button inside one (a session's Delete) the key is the
// button's own: the event's target is the button, not the row.
document.addEventListener("keydown", (e) => {
  const el = e.target;
  if (!el.matches?.("[data-a11y-act]") || e.altKey || e.ctrlKey || e.metaKey || e.shiftKey || e.isComposing) return;
  if (e.key === "Enter" || (e.key === " " && el.getAttribute("role") === "button")) { e.preventDefault(); el.click(); }
});

// ---- focus survives a redraw
// Lists redraw when a row in them is used (Review, Changes, Sessions, Specs), and the row that had focus goes with
// the old list, leaving focus on the page. It moves to the same row in the new list, found by what identifies it (its
// id, or its data-* attributes and its parents'), else to the first row in the same container.
const A11Y_ROWS = "[data-a11y-act], [role=treeitem], [role=tab], [role=option], [role=menuitem]";
function a11yKey(el) {
  if (el.matches(".rv-item")) return ".rv-list .rv-item.on"; // Review: focus follows the selection (j, k)
  const parts = [];
  for (let n = el; n && n !== document.body; n = n.parentElement) {
    if (n.id) { parts.unshift("#" + CSS.escape(n.id)); break; }
    const data = [...n.attributes].filter((a) => a.name.startsWith("data-") && a.name !== "data-a11y-act");
    if (data.length) parts.unshift(data.map((a) => `[${a.name}="${CSS.escape(a.value)}"]`).join(""));
  }
  return parts.join(" ");
}
document.addEventListener("focusin", (e) => {
  const el = e.target, box = el.parentElement?.closest("[id]");
  a11y.last = { el, key: a11yKey(el), box: box && "#" + CSS.escape(box.id) };
});
// A click on something that can't take focus leaves focus on the page: that's where you put it, not a redraw.
document.addEventListener("mousedown", () => { a11y.last = null; }, true);

function a11yKeepFocus() {
  const last = a11y.last, now = document.activeElement;
  if (!last || last.el.isConnected || (now && now !== document.body)) return;
  const shown = (el) => el?.getClientRects().length > 0;
  let el = null;
  try { el = document.querySelector(last.key); } catch { /* not a selector: fall through */ }
  if (!shown(el)) {
    const box = last.box && document.querySelector(last.box);
    if (box) a11yDecorateIn(box); // (a row, never a button: a second Enter mustn't do something you didn't aim at)
    el = box && [...box.querySelectorAll(A11Y_ROWS)].find(shown);
  }
  if (!el) return;
  a11yDecorateIn(el);
  el.focus({ preventScroll: true });
}
