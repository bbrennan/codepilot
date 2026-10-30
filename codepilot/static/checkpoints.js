"use strict";
// Turn checkpoints: undo the file changes codepilot applied from a message onwards, alone (↶ on the message) or
// along with Edit / Retry. Uses app.js's helpers (api, esc, icon, toast, confirmDialog, state, ...).

// The changes applied from message `mid` of session `sid` onwards. Throws if they couldn't be fetched: that's not
// the same as "none", which would skip the question.
async function checkpointFor(sid, mid) {
  return (await api(`/api/sessions/${sid}/checkpoint?mid=${encodeURIComponent(mid)}`)).changes;
}

// Still looking at the session (and message) the user acted on? Any await can outlast a session switch.
const stillOn = (sid, el) => state.sid === sid && el.isConnected;

// The confirmation, with the list of changes (and, for Edit/Retry, a box to undo them too). Resolves to null when
// cancelled, else {undo: {ids, keep} | null}: ids to undo, and the ones listed as left (reported, never undone).
async function checkpointDialog(title, hint, okLabel, changes, optional) {
  const ok = changes.filter((c) => c.ok);
  const n = ok.length;
  const box = $("#dialogExtra");
  box.innerHTML = `<div class="cp-list">${changes.map((c) => `<div class="cp-row ${c.ok ? "ok" : "left"}">${icon("file")}<span class="mono">${esc(c.path)}</span><span class="muted">#${c.id}</span>${c.ok ? "" : `<span class="muted">· ${esc(c.reason)}, left as is</span>`}</div>`).join("")}</div>
    ${optional && n ? `<label class="toggle cp-restore"><input type="checkbox" id="cpRestore" checked><span>Also undo ${n === 1 ? "this file change" : `these ${n} file changes`}</span></label>` : ""}
    <div class="hint cp-note">Changes made by commands, the terminal or other editors aren't undone.</div>`;
  box.hidden = false;
  const go = await confirmDialog(title, hint, okLabel);
  const restore = optional ? !!$("#cpRestore")?.checked : true;
  box.hidden = true; box.innerHTML = "";
  if (!go) return null;
  return { undo: restore && n ? { ids: ok.map((c) => c.id), keep: changes.filter((c) => !c.ok).map((c) => c.id) } : null };
}

// Before Edit or Retry rewinds to `el`: today's confirmation, plus the changes it would leave behind.
async function confirmRewind(el, kind) {
  const sid = state.sid;
  let changes;
  try { changes = await checkpointFor(sid, el.dataset.mid); }
  catch (err) { toast(`Couldn't check which file changes this would leave: ${err.message}`, true); return null; }
  if (!stillOn(sid, el)) return null;
  const isLast = el === lastTurnBubble();
  const words = kind === "edit"
    ? ["Rewind to this message?", "Everything after it in this conversation is removed, then your edited message is sent.", "Rewind & send"]
    : ["Retry from here?", "Everything after this message is removed and it's sent again.", "Retry"];
  let choice;
  if (!changes.length) {
    const hint = words[1] + (kind === "edit" ? " File changes you already applied stay (undo them in Changes if needed)." : "");
    choice = isLast || (await confirmDialog(words[0], hint, words[2])) ? { undo: null } : null;
  } else {
    choice = await checkpointDialog(words[0], words[1], words[2], changes, true);
  }
  return choice && stillOn(sid, el) ? choice : null;
}

// ↶ on a message: undo what was applied from there on, keeping the conversation.
async function undoFrom(el) {
  const sid = state.sid;
  if (!sid || state.streams.has(sid)) return toast("Wait for codepilot to finish (or press Stop) first.", true);
  let changes;
  try { changes = await checkpointFor(sid, el.dataset.mid); }
  catch (err) { return toast(`Couldn't check the file changes: ${err.message}`, true); }
  if (!stillOn(sid, el)) return;
  if (!changes.some((c) => c.ok)) return toast(changes.length ? "Those changes can't be undone: their files changed since." : "Nothing was applied from here on.", true);
  const choice = await checkpointDialog("Undo file changes from here?", "The conversation stays as it is; codepilot hears what you undid with your next message.", "Undo changes", changes, false);
  if (!choice || !stillOn(sid, el)) return;
  const res = await fetch(`/api/sessions/${sid}/restore`, { method: "POST", headers: H, body: JSON.stringify(choice.undo) });
  const data = await res.json().catch(() => ({}));
  if (state.sid !== sid) return; // done on the server; its proposals and notice belong to the session we left
  for (const p of data.reverted || []) { const known = state.proposals.get(p.id); state.proposals.set(p.id, { ...known, ...p }); refreshProposalViews(p.id); }
  loadGit(); reloadOpenFiles(data.reverted || []);
  if (!res.ok) return toast(data.error || res.statusText, true);
  add(`<div class="banner notice">${esc(data.message)}</div>`); scrollEnd(true);
  el.querySelector("[data-act=undo]").hidden = true;
}

// The ↶ button shows only when something applied from that message on can be undone. Checked on hover, at most
// every few seconds per message, since later turns can apply more.
$("#transcript").addEventListener("mouseover", async (e) => {
  const el = e.target.closest(".msg.user[data-mid]");
  if (!el || !state.sid || Date.now() - (+el.dataset.cpAt || 0) < 3000) return;
  el.dataset.cpAt = Date.now();
  const btn = el.querySelector("[data-act=undo]");
  if (btn) btn.hidden = !(await checkpointFor(state.sid, el.dataset.mid).catch(() => [])).some((c) => c.ok);
});

// After Edit/Retry with undo. If undoing failed partway the server didn't rewind (no turn started, so the new
// bubble never got its message id): redraw the conversation as the server kept it, and say why.
async function afterRestoreRewind(sid, fresh, ids) {
  if (state.sid !== sid) return;
  loadGit(); reloadOpenFiles([...state.proposals.values()].filter((p) => ids.includes(p.id)));
  if (fresh.dataset.mid) return;
  let why = "", el = fresh;
  while ((el = el.nextElementSibling)) if (el.matches(".banner.error")) why = el.textContent;
  await openSession(sid);
  if (why) toast(why, true, { label: "OK", run() {} }); // the action keeps it up long enough to read
}
