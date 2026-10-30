"use strict";
// Verification receipts: pending changes are tested on a copy of the workspace before review. The receipt shows in
// the review bar and the Review tab, where you decide, and as a card in the chat. Uses app.js's helpers.

const pendingIds = () => [...state.proposals.values()].filter((p) => p.status === "pending").map((p) => p.id).sort((a, b) => a - b);
const idList = (ids) => ids.map((i) => `#${i}`).join(", ");

// A receipt speaks for exactly the changes it tested: any change to the pending set makes it stale.
function receiptIsCurrent(r) {
  const now = pendingIds(), then = [...(r?.proposal_ids || [])].sort((a, b) => a - b);
  return !!r && now.length === then.length && now.every((id, i) => id === then[i]);
}

function runWord(run) {
  if (run.exit == null) return `${run.name} timed out`;
  if (run.name === "tests") return run.exit === 0 ? "tests pass" : "tests fail";
  return run.exit === 0 ? `${run.name} clean` : `${run.name} found issues`;
}

// The one-line receipt for the pending changes ("" when there's nothing to say).
function receiptHtml() {
  if (state.cfg?.verify === false || !pendingIds().length) return "";
  if (state.verifying) return `<div class="rb-receipt"><span class="spinner"></span><span class="muted">verifying on a copy of the workspace…</span><button class="btn sm ghost" data-verify-cancel>Cancel</button></div>`;
  const r = state.receipt;
  const verify = (label) => `<button class="btn sm" data-verify title="Apply the pending changes to a copy of the workspace and run its tests and analysers there">${label}</button>`;
  if (!r) return `<div class="rb-receipt"><span class="muted">○ not verified</span>${verify("Verify")}</div>`;
  if (!receiptIsCurrent(r)) return `<div class="rb-receipt"><span class="muted">○ not verified: changed since the last check</span>${verify("Re-verify")}</div>`;
  const runs = `<span class="muted">${esc(r.runs.map(runWord).join(" · "))}${r.runs.length ? " · " : ""}${r.seconds}s</span>`;
  const details = `<button class="btn sm ghost" data-receipt-details>Details</button>`;
  const line = (mark, text, rest = "") => `<div class="rb-receipt">${mark}${text}${rest}</div>`;
  switch (r.status) {
    case "pass": return line(`<span class="ok">✓ verified</span>`, runs, details);
    case "preexisting": return line(`<span class="ok">✓ no new failures</span>`, `<span class="muted">(some fail without the changes too)</span>${runs}`, details);
    case "fail": return line(`<span class="bad">✗ ${r.newly_failing.length} newly failing</span>`, `<span class="muted rb-first">${esc(r.newly_failing[0] || "")}</span>`, `${details}<button class="btn sm" data-receipt-fix>Ask codepilot to fix</button>`);
    case "unverified": return line(`<span class="warn">⚠ passed, but may have tested the workspace's code</span>`, "", details);
    case "nothing": return line(`<span class="muted">○ nothing to run: no test command or analysers (set CODEPILOT_TEST_CMD)</span>`, "", verify("Verify"));
    case "inconclusive": return line(`<span class="warn">⚠ failing, and it fails without the changes too</span>`, `<span class="muted">the output doesn't show whether they caused it</span>`, details);
    case "error": return line(`<span class="bad">✗ couldn't verify</span>`, `<span class="muted">${esc(r.conflict)}</span>`, details);
    case "timeout": return line(`<span class="warn">⏱ verification timed out</span>`, runs, details + verify("Re-verify"));
    default: return line(`<span class="muted">○ verification ${esc(r.status)}</span>`, "", verify("Verify"));
  }
}

// Analyser findings on one file, from the current receipt, for the Review tab.
function receiptFindings(path) {
  const r = state.receipt;
  if (!receiptIsCurrent(r)) return "";
  const lines = r.runs.filter((run) => run.name !== "tests" && run.exit)
    .flatMap((run) => run.output.split("\n").filter((l) => l.startsWith(path + ":")).map((l) => `${run.name}: ${l}`));
  return lines.length ? `<details class="rv-findings" open><summary>${icon("alert")}${lines.length} analyser finding${lines.length > 1 ? "s" : ""} in this file</summary><pre>${esc(lines.join("\n"))}</pre></details>` : "";
}

function bindReceipt(root) {
  root.querySelectorAll("[data-verify]").forEach((b) => (b.onclick = startVerify));
  root.querySelectorAll("[data-verify-cancel]").forEach((b) => (b.onclick = () => api(`/api/sessions/${state.sid}/cancel`, { method: "POST" }).catch(() => null)));
  root.querySelectorAll("[data-receipt-details]").forEach((b) => (b.onclick = showReceiptCard));
  root.querySelectorAll("[data-receipt-fix]").forEach((b) => (b.onclick = askToFix));
}

function startVerify() {
  const sid = state.sid;
  if (!sid || state.streams.has(sid)) return toast("Wait for codepilot to finish (or press Stop) first.", true);
  state.verifying = pendingIds(); renderReviewBar();
  streamTo(sid, `/api/sessions/${sid}/verify`, {}).then(() => { if (state.sid === sid && state.verifying) { state.verifying = null; renderReviewBar(); } });
}

function receiptCard(r) {
  const word = { inconclusive: "⚠ inconclusive", pass: "✓ pass", fail: `✗ ${r.newly_failing.length} newly failing`, preexisting: "✓ no new failures", unverified: "⚠ may have tested the workspace's code", nothing: "nothing to run", error: "✗ couldn't apply together", timeout: "timed out", cancelled: "cancelled" }[r.status] || r.status;
  const cls = { pass: "ok", preexisting: "ok", fail: "bad", error: "bad" }[r.status] || "muted";
  const runs = r.runs.map((run) => `<div class="vf-run"><div><b>${esc(run.name)}</b> <code>${esc(run.argv)}</code> <span class="${run.exit === 0 ? "ok" : "bad"}">${run.exit == null ? "timed out" : "exit " + run.exit}</span>${run.baseline_exit != null ? ` <span class="muted">· without the changes: exit ${run.baseline_exit}</span>` : ""}</div>${run.exit ? `<pre>${esc(run.output)}</pre>` : ""}</div>`).join("");
  return `<details class="card verify" data-receipt="${r.id}"><summary class="hd">${icon("beaker")}<span>Verified change${r.proposal_ids.length > 1 ? "s" : ""} ${idList(r.proposal_ids)} on a copy: <b class="${cls}">${esc(word)}</b></span><span class="spacer"></span><span class="muted">${r.seconds}s</span></summary>
    <div class="vf-runs">${runs || `<div class="muted">Nothing ran.</div>`}
      ${r.newly_failing.length ? `<div class="vf-new"><b>Newly failing</b> (not failing without the changes)<ul>${r.newly_failing.map((f) => `<li><code>${esc(f)}</code></li>`).join("")}</ul></div>` : ""}
      ${r.conflict ? `<div class="bad">${esc(r.conflict)}</div>` : ""}
      ${r.isolation.length ? `<div class="warn">These copied files still point at the workspace, so the copy may have run its code: ${esc(r.isolation.join(", "))}</div>` : ""}
      <div class="hint">Nothing was applied: this ran on a temporary copy with the changes applied.</div></div></details>`;
}

function showReceiptCard() {
  const r = state.receipt; if (!r) return;
  let card = $(`#transcript .card.verify[data-receipt="${r.id}"]`);
  if (!card) card = add(receiptCard(r)); // e.g. after a reload: the card of an automatic run isn't in the history
  card.open = true; card.scrollIntoView({ block: "nearest" });
}

function askToFix() {
  const r = state.receipt; if (!r) return;
  setInput(`The verification of pending changes ${idList(r.proposal_ids)} found these newly failing: ${r.newly_failing.join("; ")}. Fix them with new proposals (the earlier ones are still pending).`);
  send();
}

// Stream events.
function onVerifying(ev) { state.verifying = ev.ids; renderReviewBar(); }
// A stream that errors or ends without a receipt (e.g. the copy couldn't be made) mustn't leave the bar spinning.
function onStreamSettled() { if (state.verifying) { state.verifying = null; renderReviewBar(); } }
function onVerification(ev, replay) {
  state.verifying = null;
  if (ev.receipt) { state.receipt = ev.receipt; add(receiptCard(ev.receipt)); }
  renderReviewBar();
  if (!replay && state.active === "review") renderEditor();
}
