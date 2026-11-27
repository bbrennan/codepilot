"use strict";
// Pane sizes: the sidebar and chat widths and the bottom panel's height. What you drag is saved per browser as your
// preference; what's shown is that preference fitted to the window. A window that moves to a smaller screen (a laptop
// leaving its external monitor) shrinks the panes instead of pushing the chat and message box off the edge, and gets
// your sizes back when it's big again. Loaded before app.js, whose init restores the sizes before the first paint, so
// it uses none of app.js's helpers.

const LAYOUT = {
  vars: { "--sidebar-w": { min: 180, max: 560, def: 280 }, "--chat-w": { min: 300, max: 820, def: 440 },
          "--panel-h": { min: 90, max: 640, def: 220 } },
  ACTIVITY_W: 48, RESIZER: 4, CENTER_MIN: 280, // as in app.css's grid
  // The editor's width that fitting keeps (the sidebar and chat shrink first), and the least it may have before the
  // sidebar steps aside. Dragging still goes down to CENTER_MIN: a size you drag to is your choice.
  CENTER_COMFORT: 440, CENTER_FLOOR: 400,
  keepSidebar: false, // you showed the sidebar since the window was last resized: it stays, room or not
  CHROME_H: 38 + 24 + 35 + 4, EDITOR_MIN: 120, // title bar, status bar, editor tabs, panel resizer; the editor's floor
};

function layoutPref(name) {
  let saved = null;
  try { saved = localStorage.getItem("cp" + name); } catch { /* storage blocked: defaults */ }
  const n = parseFloat(saved);
  const v = LAYOUT.vars[name];
  return Number.isFinite(n) ? Math.max(v.min, Math.min(v.max, n)) : v.def;
}

function layoutSavePref(name, px) {
  try { localStorage.setItem("cp" + name, Math.round(px) + "px"); } catch { /* not remembered: still shown */ }
}

// Whether a side pane is shown: not hidden by you, nor (the sidebar) stepped aside for room.
function layoutShown(ide, pane) {
  return !ide.classList.contains("no-" + pane) && !(pane === "sidebar" && ide.classList.contains("auto-no-sidebar"));
}

// Whether the sidebar steps aside: even with it and the chat at their narrowest, the editor would be under
// CENTER_FLOOR. Decided from the window and your own choices as if the sidebar were shown, never from whether it is
// shown now: hiding it frees room, so asking about the room left would show it again, and so on for ever.
function layoutSidebarSteps(ide) {
  const stacked = matchMedia("(max-width: 820px)").matches; // app.css's stacked layout: no columns to fit
  if (stacked || ide.classList.contains("no-sidebar") || LAYOUT.keepSidebar) return false;
  const V = LAYOUT.vars, chat = layoutShown(ide, "chat") ? LAYOUT.RESIZER + V["--chat-w"].min : 0;
  return innerWidth - LAYOUT.ACTIVITY_W - LAYOUT.RESIZER - V["--sidebar-w"].min - chat < LAYOUT.CENTER_FLOOR;
}

// You showed the sidebar (app.js: its toggle, ⌘B, an activity-bar icon): it stays shown until the window is resized.
function layoutUserShowedSidebar(ide) {
  LAYOUT.keepSidebar = true;
  ide.classList.remove("auto-no-sidebar");
}

// The widest each side pane may be right now, given the other's shown width and the editor's width to keep.
function layoutRoom(ide, name, other, center = LAYOUT.CENTER_MIN) {
  const sidebar = layoutShown(ide, "sidebar"), chat = layoutShown(ide, "chat");
  const fixed = LAYOUT.ACTIVITY_W + center + (sidebar ? LAYOUT.RESIZER : 0) + (chat ? LAYOUT.RESIZER : 0);
  if (name === "--panel-h") return innerHeight - LAYOUT.CHROME_H - LAYOUT.EDITOR_MIN;
  return innerWidth - fixed - (other ?? 0);
}

function fitLayout(ide = document.getElementById("ide")) {
  if (!ide) return;
  const V = LAYOUT.vars;
  const steps = layoutSidebarSteps(ide);
  // Only a change: the class observer runs this again, and a write of the same class would still notify it.
  if (ide.classList.contains("auto-no-sidebar") !== steps) ide.classList.toggle("auto-no-sidebar", steps);
  const sidebarOn = layoutShown(ide, "sidebar"), chatOn = layoutShown(ide, "chat");
  let side = layoutPref("--sidebar-w"), chat = layoutPref("--chat-w");
  const room = layoutRoom(ide, "--sidebar-w", 0, LAYOUT.CENTER_COMFORT);
  const want = (sidebarOn ? side : 0) + (chatOn ? chat : 0);
  if (want > room) {
    // Share the shortfall by how far each pane is above its minimum, so neither collapses while the other stays wide.
    const slackS = sidebarOn ? side - V["--sidebar-w"].min : 0, slackC = chatOn ? chat - V["--chat-w"].min : 0;
    const cut = Math.min(want - room, slackS + slackC);
    if (slackS + slackC > 0) {
      side -= (cut * slackS) / (slackS + slackC);
      chat -= (cut * slackC) / (slackS + slackC);
    }
  }
  const panel = Math.max(V["--panel-h"].min, Math.min(layoutPref("--panel-h"), layoutRoom(ide, "--panel-h")));
  ide.style.setProperty("--sidebar-w", Math.floor(side) + "px");
  ide.style.setProperty("--chat-w", Math.floor(chat) + "px");
  ide.style.setProperty("--panel-h", Math.floor(panel) + "px");
}

function makeResizer(el, varName, axis, invert) {
  const v = LAYOUT.vars[varName];
  el.addEventListener("mousedown", (e) => {
    e.preventDefault(); el.classList.add("drag");
    const ide = document.getElementById("ide");
    const start = axis === "x" ? e.clientX : e.clientY;
    const startVal = parseFloat(getComputedStyle(ide).getPropertyValue(varName));
    const other = { "--sidebar-w": "--chat-w", "--chat-w": "--sidebar-w" }[varName];
    const otherShown = other && layoutShown(ide, other === "--chat-w" ? "chat" : "sidebar")
      ? parseFloat(getComputedStyle(ide).getPropertyValue(other)) : 0;
    const max = Math.max(v.min, Math.min(v.max, layoutRoom(ide, varName, otherShown))); // never past the window
    let value = startVal;
    const move = (ev) => {
      const delta = (axis === "x" ? ev.clientX : ev.clientY) - start;
      value = Math.max(v.min, Math.min(max, startVal + (invert ? -delta : delta)));
      ide.style.setProperty(varName, value + "px");
    };
    const up = () => {
      el.classList.remove("drag"); document.removeEventListener("mousemove", move); document.removeEventListener("mouseup", up);
      layoutSavePref(varName, value); // only the pane you dragged: the other keeps the size you chose for it
    };
    document.addEventListener("mousemove", move); document.addEventListener("mouseup", up);
  });
}

function initLayout() {
  const ide = document.getElementById("ide");
  fitLayout(ide);
  makeResizer(document.getElementById("sidebarResizer"), "--sidebar-w", "x", false);
  makeResizer(document.getElementById("chatResizer"), "--chat-w", "x", true);
  makeResizer(document.getElementById("panelResizer"), "--panel-h", "y", true);
  // A window moved to another display, resized, or zoomed; or a pane shown or hidden, which changes the room left.
  addEventListener("resize", () => { LAYOUT.keepSidebar = false; fitLayout(ide); });
  new MutationObserver(() => fitLayout(ide)).observe(ide, { attributes: true, attributeFilter: ["class"] });
}
