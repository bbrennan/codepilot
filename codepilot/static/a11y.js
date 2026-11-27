"use strict";
// Everything by keyboard (spec keyboard-access). The app draws by replacing innerHTML, so roles and tab stops aren't
// written into each template: this script decorates what was drawn, by selector, and owns the keys. A new kind of
// clickable row is a selector added here. Loaded after app.js and using its helpers.

// Click-only elements: each gets a tab stop and a role, and Enter or Space clicks it (a link: Enter only). One that
// already has a tabindex has keys of its own (the plan line, Progress markers) and is left alone.
const A11Y_BUTTONS = [
  ".session", ".grep-file > .row", ".grep-hit", "#proposalList .row", "#gitList .row", ".rv-item", "#specsView .row",
  "#steeringView .row", "#traceList .row", ".welcome .link", "#sbContext", "[data-spec-open]", "#fdPlaces .row",
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
// Menus, dialogs and the session switcher sit over the page; focus goes back from them to what had it before.
const A11Y_OVERLAYS = "#ctxMenu, .palette, #sessPop";
document.addEventListener("focusin", (e) => {
  const el = e.target, box = el.parentElement?.closest("[id]");
  a11yState.last = { el, key: a11yKey(el), box: box && "#" + CSS.escape(box.id) };
  if (!el.closest(A11Y_OVERLAYS)) a11yState.outside = a11yState.last;
});
// Where to give focus back to: the element that had it, or the same thing redrawn since.
function a11yBack(to) {
  if (!to) return null;
  if (to.el.isConnected && to.el.getClientRects().length) return to.el;
  try { return document.querySelector(to.key); } catch { return null; }
}
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
    const own = "[role=tab], [role=treeitem], [role=option]"; // (a list's own tab stop first)
    el = rows.find((r) => r.tabIndex === 0 && r.matches(own)) || rows[0];
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

// ---- menus (3.1, 3.2)
// showMenu ends here. Focus moves to the first item; Up and Down (round the ends), Home, End and a letter move; Enter
// or Space runs an item; Escape or Tab closes it. When it closes by a key or by running an item, focus goes back to
// what opened it, unless the item put focus somewhere itself (a dialog). A click elsewhere puts focus where it went.
function a11yMenu(m) {
  m.setAttribute("role", "menu");
  for (const it of m.querySelectorAll("[data-mi]")) { it.setAttribute("role", "menuitem"); it.tabIndex = -1; }
  for (const sep of m.querySelectorAll(".sep")) sep.setAttribute("role", "separator");
  const opener = a11yState.menuOpener = a11yState.outside;
  if (opener?.el.hasAttribute("aria-haspopup")) opener.el.setAttribute("aria-expanded", "true");
  m.querySelector("[data-mi]")?.focus({ preventScroll: true });
}
new MutationObserver(() => {
  const m = $("#ctxMenu"), opener = a11yState.menuOpener;
  if (!m.hidden || !opener) return;
  a11yState.menuOpener = null;
  if (opener.el.hasAttribute("aria-expanded")) opener.el.setAttribute("aria-expanded", "false");
  const now = document.activeElement;
  if (now === document.body || m.contains(now)) a11yBack(opener)?.focus({ preventScroll: true });
}).observe($("#ctxMenu"), { attributes: true, attributeFilter: ["hidden"] });
$("#ctxMenu").addEventListener("keydown", (e) => {
  const m = e.currentTarget, items = [...m.querySelectorAll("[data-mi]")], i = items.indexOf(e.target.closest("[data-mi]"));
  if (e.altKey || e.ctrlKey || e.metaKey || e.isComposing) return;
  let to = null;
  if (e.key === "ArrowDown") to = items[(i + 1) % items.length];
  else if (e.key === "ArrowUp") to = items[(i - 1 + items.length) % items.length];
  else if (e.key === "Home") to = items[0];
  else if (e.key === "End") to = items.at(-1);
  else if (e.key === "Enter" || e.key === " ") { e.preventDefault(); items[i]?.click(); return; }
  else if (e.key === "Escape" || e.key === "Tab") { e.preventDefault(); e.stopPropagation(); m.hidden = true; return; }
  else if (e.key.length === 1) {
    const label = (it) => (it.querySelector("span")?.textContent || "").toLowerCase();
    to = [...items.slice(i + 1), ...items.slice(0, i + 1)].find((it) => label(it).startsWith(e.key.toLowerCase()));
  }
  if (!to) return;
  e.preventDefault(); to.focus({ preventScroll: true });
});

// ---- F6: the next pane (2.5)
// Sidebar, editor, bottom panel and chat, those shown, in order (Shift: backwards). Each pane's place to land: the
// sidebar view's first tab stop, the editor's tab (or its first control with no tabs), the panel's tab, the message box.
const A11Y_TABBABLE = "a[href], button:not([disabled]), input:not([disabled]):not([type=hidden]), select:not([disabled]),"
  + " textarea:not([disabled]), summary, [tabindex]:not([tabindex='-1'])";
const a11yFirst = (box) => [...(box?.querySelectorAll(A11Y_TABBABLE) || [])].find((el) => el.getClientRects().length);
const A11Y_PANES = [
  { in: ".sidebar", shown: () => layoutShown(ide, "sidebar"),
    land: () => a11yFirst($(".sidebar .view.on .view-body")) || a11yFirst($(".sidebar .view.on")) },
  { in: ".center > :not(.panel)", shown: () => true,
    land: () => $("#editorTabs .tab[tabindex='0']") || a11yFirst($("#editor")) },
  { in: ".panel", shown: () => !ide.classList.contains("no-panel"), land: () => $(".panel-tabs [data-ptab].on") },
  { in: ".chat", shown: () => layoutShown(ide, "chat"), land: () => $("#input") },
];
document.addEventListener("keydown", (e) => {
  if (e.key !== "F6" || e.altKey || e.ctrlKey || e.metaKey) return;
  const at = A11Y_PANES.findIndex((p) => document.activeElement?.closest(p.in));
  const n = A11Y_PANES.length, step = e.shiftKey ? -1 : 1;
  for (let k = 1; k <= n; k++) {
    const p = A11Y_PANES[((at < 0 ? (e.shiftKey ? 0 : -1) : at) + step * k + n * 2) % n];
    const el = p.shown() && p.land();
    if (el) { e.preventDefault(); a11yDecorateIn(el); el.focus(); return; }
  }
});

// ---- dialogs (3.3, 3.4)
// The four overlays toggle `hidden`. Shown: focus moves in (to its text box, else its first control) unless its own
// code already put it there, and Tab and Shift+Tab go round inside it. Hidden: focus goes back to what had it before
// (the last thing focused outside an overlay, or the same thing redrawn), unless something else has taken it since;
// Chromium leaves focus on a hidden element, so this is always needed. Escape closes from anywhere inside.
const A11Y_DIALOGS = [
  { sel: "#dialog", label: "dialogTitle", cancel: "#dialogCancel" },
  { sel: "#folderDialog", label: "fdTitle", cancel: "#fdCancel" },
  { sel: "#reportDialog", label: "rpHeading", cancel: "#rpClose" },
  { sel: "#palette", name: "Go to file", close: () => closePalette() },
];
const a11yShown = (el) => el.getClientRects().length > 0;
for (const d of A11Y_DIALOGS) {
  const el = $(d.sel);
  el.setAttribute("role", "dialog"); el.setAttribute("aria-modal", "true");
  if (d.label) el.setAttribute("aria-labelledby", d.label); else el.setAttribute("aria-label", d.name);
  new MutationObserver(() => {
    const now = document.activeElement;
    if (!el.hidden) {
      el._opener = a11yState.outside;
      if (!el.contains(now)) (el.querySelector("input:not([type=checkbox]):not([hidden])") || a11yFirst(el))?.focus();
    } else if (now === document.body || el.contains(now)) {
      // After the key that closed it is done: Enter in a prompt's text box would otherwise go on to click the button
      // that opened the prompt (New File…), and open it again.
      setTimeout(() => {
        const at = document.activeElement;
        if (el.hidden && (at === document.body || el.contains(at))) a11yBack(el._opener)?.focus({ preventScroll: true });
      });
    }
  }).observe(el, { attributes: true, attributeFilter: ["hidden"] });
  el.addEventListener("keydown", (e) => {
    if (el.hidden) return; // (its own keys closed it already)
    if (e.key === "Escape") { e.preventDefault(); if (d.cancel) $(d.cancel).click(); else d.close(); return; }
    if (e.key !== "Tab" || e.altKey || e.ctrlKey || e.metaKey) return;
    const all = [...el.querySelectorAll(A11Y_TABBABLE)].filter(a11yShown), at = document.activeElement;
    if (!all.length) return;
    const next = e.shiftKey ? all.findLast((x) => at.compareDocumentPosition(x) & Node.DOCUMENT_POSITION_PRECEDING)
      : all.find((x) => at.compareDocumentPosition(x) & Node.DOCUMENT_POSITION_FOLLOWING);
    if (!next) { e.preventDefault(); (e.shiftKey ? all.at(-1) : all[0]).focus(); }
  });
}

// The folder dialog's list: one tab stop, Up, Down, Home and End move, and the row you're on is selected as a click
// selects it, so Enter (the dialog's own key) goes into it. Its places are buttons (above).
function a11yFolderList() {
  const list = $("#fdList"), rows = [...list.querySelectorAll(".row")];
  list.setAttribute("role", "listbox"); list.setAttribute("aria-label", "Folders");
  for (const r of rows) {
    r.setAttribute("role", "option"); r.setAttribute("aria-selected", String(r.classList.contains("sel"))); r.tabIndex = -1;
  }
  (rows.find((r) => r.classList.contains("sel")) || rows[0])?.setAttribute("tabindex", "0");
  a11yKeepFocus();
}
new MutationObserver(a11yFolderList).observe($("#fdList"), { childList: true });
$("#fdList").addEventListener("focusin", (e) => {
  const row = e.target.closest(".row[data-fdpath]");
  if (row && !row.classList.contains("sel")) { row.click(); a11yFolderList(); }
});
$("#fdList").addEventListener("keydown", (e) => {
  const rows = [...$$("#fdList .row[data-fdpath]")], i = rows.indexOf(e.target.closest(".row"));
  if (i < 0 || e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;
  const to = { ArrowDown: rows[i + 1], ArrowUp: rows[i - 1], Home: rows[0], End: rows.at(-1) }[e.key];
  if (!to) return;
  e.preventDefault(); e.stopPropagation();
  for (const r of rows) r.tabIndex = r === to ? 0 : -1;
  to.focus(); to.scrollIntoView({ block: "nearest" });
});

// ---- the @, / and # suggestion lists (4.4)
// The session switcher's pattern (sessions.js): a listbox of options with ids, and the current one as the text box's
// active descendant, so focus stays in the message box while the list says which option Enter takes.
function a11ySuggestions() {
  const pop = $("#mentionPop"), box = $("#input");
  pop.setAttribute("role", "listbox"); pop.setAttribute("aria-label", "Suggestions");
  box.setAttribute("aria-controls", "mentionPop"); box.setAttribute("aria-autocomplete", "list");
  [...pop.querySelectorAll(".opt")].forEach((o, i) => {
    o.id = "mention-opt-" + i; o.setAttribute("role", "option");
    o.setAttribute("aria-selected", String(o.classList.contains("on")));
  });
  const on = !pop.hidden && pop.querySelector(".opt.on");
  if (on) box.setAttribute("aria-activedescendant", on.id); else box.removeAttribute("aria-activedescendant");
}
new MutationObserver(a11ySuggestions).observe($("#mentionPop"), { childList: true, attributes: true, attributeFilter: ["hidden"] });
a11ySuggestions();

// ---- being told (5.1–5.3)
// Two visually hidden live regions in index.html: #srPolite (status) for what can wait, #srNow (alert) for what can't.
// Each announcement replaces the region's content with a new node, so the same words twice are said twice. The
// transcript is no live region: a streamed reply would be read word by word (5.3).
function a11yAnnounce(text, now) {
  const el = $(now ? "#srNow" : "#srPolite");
  if (!el || !text) return;
  const said = document.createElement("div"); said.textContent = text;
  el.replaceChildren(said);
}
// A turn, in the words on screen: working (once a turn), a command waiting ("Wants to run: ls", as its step says,
// steps.js), an error (the banner's own message, at once), finished (unless it ended with an error). app.js tells this
// only for live events, never for a session's history drawn again.
// (Approving a waiting command resumes the same turn as a new stream: it isn't said to start again.)
const a11yTurn = { busy: false, ended: false, waiting: false };
function a11yTurnState(kind, detail) {
  if (kind === "busy" || kind === "idle") {
    if (kind === "busy" && !a11yTurn.busy) {
      if (!a11yTurn.waiting) { a11yTurn.ended = false; a11yAnnounce("codepilot is working"); }
      a11yTurn.waiting = false;
    }
    a11yTurn.busy = kind === "busy";
  } else if (kind === "approval") {
    a11yTurn.waiting = true;
    a11yAnnounce(detail.map((t) => `${waitingVerb(t)}: ${cmdShort(t.command || "")}`.replace(/: $/, "")).join("; "), true);
  } else if (kind === "error") { a11yTurn.ended = true; a11yAnnounce(detail, true); }
  else if (kind === "done" && !a11yTurn.ended) { a11yTurn.ended = true; a11yAnnounce("codepilot finished"); }
}

// What app.js calls. focus(selector): put focus somewhere deliberate, on an element that may not be decorated yet.
function a11yFocus(sel) {
  const el = document.querySelector(sel); if (!el) return;
  a11yDecorateIn(el); el.focus({ preventScroll: true });
}
// (window.a11y?.…: app.js may draw before this script has loaded, and this catches up below.)
window.a11y = { treeRendered: a11yTreeRendered, tabsRendered: a11yTabsRendered, panelTabsShown: a11yPanelTabsShown,
  viewChanged: a11yViewChanged, menu: a11yMenu, focus: a11yFocus, announce: a11yAnnounce, turnState: a11yTurnState };
a11yTabsRendered();
if ($("#tree .row")) a11yTreeRendered();
