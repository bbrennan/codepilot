"use strict";
// Approvals that depend on the moment: warnings on the approval, and the "external content" chip in the chat header.
// Once a session has read content from outside, saved "always allow" rules pause and outbound calls ask.
// Uses app.js's helpers.

function renderTaintChip() {
  const chip = $("#taintChip");
  const sources = state.taint || [];
  chip.hidden = !sources.length;
  chip.innerHTML = sources.length ? `${icon("alert")}<span>external content</span>` : "";
  chip.title = sources.length ? `This session read: ${sources.map((s) => s.detail).join(", ")}. Saved "always allow" rules are paused and outbound calls ask.` : "";
}

function onTaint(ev) {
  state.taint = ev.sources;
  renderTaintChip();
  if ($(".view.on")?.dataset.view === "memory") renderMemory();
}

async function clearTaint() {
  const sid = state.sid;
  const ok = await confirmDialog("Clear the external content mark?", "Only clear this if you've checked what it read. Saved rules apply again, and outbound calls stop asking.", "Clear");
  if (!ok || state.sid !== sid) return;
  try {
    await api(`/api/sessions/${sid}`, { method: "PATCH", body: { taint: [] } });
    if (state.sid === sid) onTaint({ sources: [] });
  } catch (err) { toast(err.message, true); }
}

$("#taintChip").onclick = (e) => menuBelow(e.currentTarget, [
  ...(state.taint || []).map((s) => ({ label: s.detail, icon: "alert", run() {} })), "-",
  { label: "Clear…", icon: "x", run: clearTaint },
]);

// Under a command in the approval: why it's dangerous, or why it's asking at all.
const warningLines = (tool) => (tool.warnings || []).map((w) => `<div class="rb-warn ${esc(w.level)}">${icon("alert")}<span>${esc(w.text)}</span></div>`).join("");

const allowPausedNote = () => ((state.taint || []).length && (state.allow || []).length ? " · paused while this session has external content" : "");
