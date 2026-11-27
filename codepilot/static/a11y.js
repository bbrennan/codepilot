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

const a11yState = {
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
  const gutter = root.id === "gutter" ? root : root.querySelector("#gutter");
  if (gutter && !gutter.hasAttribute("tabindex")) a11yGutter(gutter);
}

// What was drawn is decorated once a frame (a streamed reply redraws on every word) and before any key is handled,
// so a key never lands where a row isn't ready yet. Only added nodes are looked at, and never the terminal's.
function a11yFlush() {
  cancelAnimationFrame(a11yState.frame); a11yState.frame = 0;
  for (const root of a11yState.pending) if (root.isConnected) a11yDecorateIn(root);
  a11yState.pending.clear();
}
new MutationObserver((records) => {
  for (const r of records) {
    if (!r.addedNodes.length || r.target.closest?.(".xterm")) continue;
    for (const n of r.addedNodes) if (n.nodeType === 1) a11yState.pending.add(n);
  }
  if (a11yState.pending.size && !a11yState.frame) a11yState.frame = requestAnimationFrame(a11yFlush);
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
  a11yState.last = { el, key: a11yKey(el), box: box && "#" + CSS.escape(box.id) };
});
// A click on something that can't take focus leaves focus on the page: that's where you put it, not a redraw.
document.addEventListener("mousedown", () => { a11yState.last = null; }, true);

function a11yKeepFocus() {
  const last = a11yState.last, now = document.activeElement;
  if (!last || last.el.isConnected || (now && now !== document.body)) return;
  const shown = (el) => el?.getClientRects().length > 0;
  let el = null;
  try { el = document.querySelector(last.key); } catch { /* not a selector: fall through */ }
  if (!shown(el)) {
    const box = last.box && document.querySelector(last.box);
    if (box) a11yDecorateIn(box); // (a row, never a button: a second Enter mustn't do something you didn't aim at)
    const rows = box ? [...box.querySelectorAll(A11Y_ROWS)].filter(shown) : [];
    el = rows.find((r) => r.tabIndex === 0 && r.matches("[role=tab], [role=treeitem]")) || rows[0]; // (a list's own stop)
  }
  if (!el) return;
  a11yDecorateIn(el);
  el.focus({ preventScroll: true });
}

// ---- the file tree (1.1–1.5)
// One tab stop: the picked row (else the open file's, else the first) has tabindex 0, the rest -1. Moving with the
// keys picks the row as a click does (state.picked, state.pickedDir), so New File, F2 and Delete keep their target.
// Opening and closing go through the row's own click, so a folder of the session (folders.js) works the same way.
const A11Y_TREE_ROWS = "#tree .row[data-file], #tree .row[data-dir], #tree .row.root";
const a11yTreeRows = () => [...document.querySelectorAll(A11Y_TREE_ROWS)].filter((r) => r.getClientRects().length);
const a11yLevel = (r) => (parseInt(r.style.getPropertyValue("--depth"), 10) || 0) + 1;
const a11yPath = (r) => r.dataset.file ?? r.dataset.dir ?? null;
const a11yIsFolder = (r) => r.dataset.dir != null || r.classList.contains("root");

function a11yTreePick(row) {
  for (const r of a11yTreeRows()) {
    r.tabIndex = r === row ? 0 : -1;
    r.setAttribute("aria-selected", String(r === row));
    r.classList.toggle("picked", r === row);
  }
  if (a11yPath(row) != null) { state.picked = a11yPath(row); state.pickedDir = row.dataset.dir != null; }
  row.focus({ preventScroll: true }); row.scrollIntoView({ block: "nearest" });
}

// renderTree ends here: roles, levels, open or closed, and the tab stop. Focus stays on the same path through the
// redraw by the same rule as every list (a11yKeepFocus).
function a11yTreeRendered() {
  const tree = $("#tree");
  tree.setAttribute("role", "tree"); tree.setAttribute("aria-label", "Files");
  tree.tabIndex = -1; // a click on empty space puts focus here, and the keys act on the picked row
  const rows = [...tree.querySelectorAll(A11Y_TREE_ROWS)];
  for (const r of rows) {
    r.setAttribute("role", "treeitem"); r.setAttribute("aria-level", a11yLevel(r)); r.tabIndex = -1;
    if (a11yIsFolder(r)) r.setAttribute("aria-expanded", String(!!r.querySelector(".caret.open")));
    for (const b of r.querySelectorAll("button")) b.tabIndex = -1; // "@" is in the row's menu: Add to chat
  }
  // The tab stop only: which row is picked (New File's folder, F2's target) changes when you move, never on a redraw.
  const cur = rows.find((r) => r.classList.contains("picked")) || rows.find((r) => r.classList.contains("on")) || rows[0];
  for (const r of rows) r.setAttribute("aria-selected", String(r.classList.contains("picked")));
  if (cur) cur.tabIndex = 0;
  a11yKeepFocus();
}

const a11yFind = { text: "", at: 0 };
$("#tree").addEventListener("keydown", (e) => {
  if (e.target.closest("button, input") || e.isComposing) return; // (a missing folder's Remove button)
  const rows = a11yTreeRows(); if (!rows.length) return;
  const row = e.target.closest(".row") || rows.find((r) => r.tabIndex === 0) || rows[0];
  const i = rows.indexOf(row), mod = isMac ? e.metaKey : e.ctrlKey, path = a11yPath(row);
  const open = row.getAttribute("aria-expanded") === "true", plain = !mod && !e.altKey;
  let to = null;
  if (e.key === "ArrowDown" && plain) to = rows[i + 1];
  else if (e.key === "ArrowUp" && plain) to = rows[i - 1];
  else if (e.key === "Home" && plain) to = rows[0];
  else if (e.key === "End" && plain) to = rows.at(-1);
  else if (e.key === "ArrowRight" && plain) {
    if (a11yIsFolder(row) && !open) row.click();
    else if (open && rows[i + 1] && a11yLevel(rows[i + 1]) > a11yLevel(row)) to = rows[i + 1];
  } else if (e.key === "ArrowLeft" && plain) {
    if (a11yIsFolder(row) && open) row.click();
    else to = rows.slice(0, i).reverse().find((r) => a11yLevel(r) < a11yLevel(row));
  } else if ((e.key === "Enter" || e.key === " ") && plain && !e.shiftKey) row.click();
  else if (e.key === "F2" && plain && path != null) renamePath(path);
  else if ((e.key === "Delete" || (mod && e.key === "Backspace")) && path != null) deletePath(path, row.dataset.dir != null);
  else if (mod && e.key.toLowerCase() === "c" && path != null && !String(getSelection())) copyText(path);
  else if ((e.key === "F10" && e.shiftKey) || e.key === "ContextMenu") {
    const r = row.getBoundingClientRect();
    row.dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, cancelable: true, clientX: r.left + 16, clientY: r.bottom }));
  } else if (e.key.length === 1 && plain && e.key !== " ") { // typing finds the next row whose name starts so
    const now = performance.now();
    a11yFind.text = now - a11yFind.at > 700 ? e.key.toLowerCase() : a11yFind.text + e.key.toLowerCase();
    a11yFind.at = now;
    const from = a11yFind.text.length > 1 ? i : i + 1, order = [...rows.slice(from), ...rows.slice(0, from)];
    to = order.find((r) => (r.querySelector(".name")?.textContent || "").toLowerCase().startsWith(a11yFind.text));
    if (!to) return;
  } else return;
  e.preventDefault(); e.stopPropagation();
  if (to) a11yTreePick(to);
});

// ---- the code view's line numbers
// One tab stop (a list whose current line is its active descendant): Up, Down, Page Up, Page Down, Home and End move;
// Enter or Space selects the line as a click does, Shift extends. The line you were on is kept per tab.
const a11yLines = new Map(); // tab id -> the line the gutter was on
function a11yGutter(g) {
  g.tabIndex = 0;
  g.setAttribute("role", "listbox"); g.setAttribute("aria-label", "Line numbers"); g.setAttribute("aria-multiselectable", "true");
  const sel = state.tabs.find((t) => t.id === state.active)?.sel;
  a11yGutterAt(g, a11yLines.get(state.active) || sel?.a || 1, false);
}
function a11yGutterAt(g, n, scroll) {
  n = Math.max(1, Math.min(n, g.children.length));
  const old = g.querySelector(".at"); if (old) { old.classList.remove("at"); old.removeAttribute("id"); }
  const el = g.children[n - 1]; if (!el) return;
  el.classList.add("at"); el.id = "ln-" + n; el.setAttribute("role", "option");
  el.setAttribute("aria-selected", String(el.classList.contains("sel")));
  g.setAttribute("aria-activedescendant", el.id);
  a11yLines.set(state.active, n);
  if (scroll) el.scrollIntoView({ block: "nearest" });
}
document.addEventListener("keydown", (e) => {
  const g = e.target; if (g.id !== "gutter" || e.altKey || e.metaKey || e.ctrlKey) return;
  const n = +(g.querySelector(".at")?.dataset.ln || 1), page = Math.max(1, Math.floor(($("#edScroll")?.clientHeight || 400) / 20) - 1);
  const to = { ArrowDown: n + 1, ArrowUp: n - 1, PageDown: n + page, PageUp: n - page, Home: 1, End: g.children.length }[e.key];
  if (to && !e.shiftKey) { e.preventDefault(); a11yGutterAt(g, to, true); return; }
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    g.children[n - 1]?.dispatchEvent(new MouseEvent("click", { bubbles: true, shiftKey: e.shiftKey }));
  }
});

// ---- tab strips: the editor's tabs and the bottom panel's (2.1–2.3)
// One tab stop each, on the tab that's shown; Left and Right (Home, End) move and show; Delete closes an editor tab
// (closeTab asks first when it has unsaved edits). Each close button is named, and out of the Tab order.
function a11yTabsRendered() {
  const strip = $("#editorTabs"), tabs = [...strip.querySelectorAll(".tab")];
  strip.setAttribute("role", "tablist"); strip.setAttribute("aria-label", "Open files");
  $("#editor").setAttribute("role", "tabpanel");
  for (const t of tabs) {
    const on = t.classList.contains("on");
    t.setAttribute("role", "tab"); t.setAttribute("aria-selected", String(on)); t.setAttribute("aria-controls", "editor");
    t.tabIndex = on ? 0 : -1;
    t.querySelector("[data-close]")?.setAttribute("tabindex", "-1");
  }
  if (tabs.length && !tabs.some((t) => t.tabIndex === 0)) tabs[0].tabIndex = 0;
  a11yKeepFocus();
}
function a11yPanelTabsShown() {
  for (const b of $$(".panel-tabs [data-ptab]")) {
    const on = b.classList.contains("on");
    b.setAttribute("aria-selected", String(on)); b.tabIndex = on ? 0 : -1;
  }
}
a11yPanelTabsShown();
// Which tab of a strip a key moves to, or null.
function a11yStep(e, list, i) {
  if (e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return null;
  return { ArrowLeft: list[i - 1], ArrowRight: list[i + 1], Home: list[0], End: list.at(-1) }[e.key] || null;
}
$("#editorTabs").addEventListener("keydown", (e) => {
  const tab = e.target.closest(".tab"); if (!tab || e.target.closest("button")) return;
  const tabs = [...$$("#editorTabs .tab")], to = a11yStep(e, tabs, tabs.indexOf(tab));
  if (to) {
    e.preventDefault();
    state.active = to.dataset.tab; renderEditor();
    a11yFocus(`#editorTabs .tab[data-tab="${CSS.escape(to.dataset.tab)}"]`);
  } else if (e.key === "Delete" && !e.altKey && !e.ctrlKey && !e.metaKey) { e.preventDefault(); closeTab(tab.dataset.tab); }
});
// A click on a tab leaves focus on the page, as a click on one always did, so Review's keys work after it; only the
// keyboard puts focus on a tab.
$("#editorTabs").addEventListener("mousedown", (e) => {
  if (!e.target.closest(".tab") || e.button !== 0) return;
  e.preventDefault(); document.activeElement?.blur();
});
$(".panel-tabs").addEventListener("keydown", (e) => {
  const b = e.target.closest("[data-ptab]"); if (!b) return;
  const tabs = [...$$(".panel-tabs [data-ptab]")], to = a11yStep(e, tabs, tabs.indexOf(b));
  if (to) { e.preventDefault(); showPanelTab(to.dataset.ptab); to.focus(); }
});

// ---- the activity bar and the chat's title (2.3, 2.4)
// Each view's button says whether its view is the one shown (not just picked: the sidebar may be hidden, by you or
// because it stepped aside for room, which layout.js knows). A count keeps the button's name: "Changes, 2 waiting
// for review". (Progress names its own count: progress.js.)
function a11yViewChanged() {
  const shown = layoutShown(ide, "sidebar");
  for (const b of $$("#activitybar button")) b.setAttribute("aria-pressed", String(shown && b.classList.contains("on")));
  const n = $("#changesBadge").hidden ? 0 : +$("#changesBadge").textContent || 0;
  $("#activitybar [data-view=changes]").setAttribute("aria-label", n ? `Changes, ${n} waiting for review` : "Changes");
}
new MutationObserver(a11yViewChanged).observe(ide, { attributes: true, attributeFilter: ["class"] }); // (shown, hidden)
a11yViewChanged();
// The title is the session's name; the button switches sessions. Said so, so it isn't a second "New session".
function a11yChatTitle() { $("#chatTitleBtn").setAttribute("aria-label", `Switch session: ${$("#chatTitle").textContent}`); }
new MutationObserver(a11yChatTitle).observe($("#chatTitle"), { childList: true, characterData: true, subtree: true });
a11yChatTitle();

// What app.js calls. focus(selector): put focus somewhere deliberate, on an element that may not be decorated yet.
function a11yFocus(sel) {
  const el = document.querySelector(sel); if (!el) return;
  a11yDecorateIn(el); el.focus({ preventScroll: true });
}
// (window.a11y?.…: app.js may draw before this script has loaded, and this catches up below.)
window.a11y = { treeRendered: a11yTreeRendered, tabsRendered: a11yTabsRendered, panelTabsShown: a11yPanelTabsShown,
  viewChanged: a11yViewChanged, focus: a11yFocus };
a11yTabsRendered();
if ($("#tree .row")) a11yTreeRendered();
