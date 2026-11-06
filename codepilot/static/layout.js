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

// The widest each side pane may be right now, given the other's shown width.
function layoutRoom(ide, name, other) {
  const shown = (cls) => !ide.classList.contains(cls);
  const sidebar = shown("no-sidebar"), chat = shown("no-chat");
  const fixed = LAYOUT.ACTIVITY_W + LAYOUT.CENTER_MIN + (sidebar ? LAYOUT.RESIZER : 0) + (chat ? LAYOUT.RESIZER : 0);
  if (name === "--panel-h") return innerHeight - LAYOUT.CHROME_H - LAYOUT.EDITOR_MIN;
  return innerWidth - fixed - (other ?? 0);
}

function fitLayout(ide = document.getElementById("ide")) {
  if (!ide) return;
  const V = LAYOUT.vars;
  const sidebarOn = !ide.classList.contains("no-sidebar"), chatOn = !ide.classList.contains("no-chat");
  let side = layoutPref("--sidebar-w"), chat = layoutPref("--chat-w");
  const room = layoutRoom(ide, "--sidebar-w", 0);
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
    const otherShown = other && !ide.classList.contains(other === "--chat-w" ? "no-chat" : "no-sidebar")
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
  addEventListener("resize", () => fitLayout(ide));
  new MutationObserver(() => fitLayout(ide)).observe(ide, { attributes: true, attributeFilter: ["class"] });
}
