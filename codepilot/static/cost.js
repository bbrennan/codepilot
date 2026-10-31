"use strict";
// The cost meter: dollars in the status bar, Memory and Activity, an estimate before "Run all remaining", and the
// banner when the daily budget is reached. A model with no price shows as $?, never as free. Uses app.js's helpers.

const fmtUsd = (x) => (x == null ? "$?" : x > 0 && x < 0.01 ? "$" + x.toFixed(4) : x < 100 ? "$" + x.toFixed(2) : "$" + Math.round(x));
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

// A total that leaves models out says so, and is unknown if it's all it has.
const partialUsd = (total, unpriced) => (unpriced.length ? (total ? fmtUsd(total) + " + $?" : "$?") : fmtUsd(total));

// " · $0.31" for the status bar: nothing without a prices file, "local" when everything ran on a local model.
function costText(u) {
  if (!u?.cost || !(u.by_model || []).length) return "";
  const { total, unpriced } = u.cost;
  if (!u.prices?.loaded && unpriced.length) return "";
  if (!unpriced.length && total === 0) return " · local";
  return ` · ${partialUsd(total, unpriced)}`;
}

function costTip(u) {
  if (!u?.cost) return "";
  const lines = (u.by_model || []).map((r) => `${shortModel(r.model)}: ${fmtUsd(r.cost)}`);
  const limit = u.budget?.limit;
  lines.push(`Today: ${partialUsd(u.today.total, u.today.unpriced)}${limit ? ` of ${fmtUsd(limit)}${u.budget.overridden ? " (lifted until midnight)" : ""}` : ""} across all sessions`);
  const missing = [...new Set([...u.cost.unpriced, ...u.today.unpriced])];
  if (u.prices?.loaded && missing.length) lines.push(`No price for ${missing.map(shortModel).join(", ")} in ${u.prices.path}: not counted`);
  if (u.prices?.error) lines.push(`Prices can't be read: ${u.prices.error}`);
  return lines.join("\n");
}

// With no prices at all there's nothing to say; with prices, a missing one is worth saying.
const costOr = (cost, priced) => (cost == null && !priced ? "" : ` · ${fmtUsd(cost)}`);
const costCell = (r, u) => costOr(r.cost, u?.prices?.loaded);
const costOfCall = (ev) => costOr(ev.cost, ev.priced);

// Under Memory → Token usage.
function costFooter(u) {
  if (!u?.prices) return "";
  if (u.prices.error) return `<div class="hint">Prices can't be read: ${esc(u.prices.error)}</div>`;
  if (!u.prices.loaded) return `<div class="hint">Add prices to see dollars: copy <span class="mono">bench/prices.example.toml</span> to <span class="mono">${esc(tilde(u.prices.path))}</span>.</div>`;
  const limit = u.budget?.limit, missing = u.today.unpriced;
  return `<div class="mono" style="font-size:11.5px;margin-top:4px">Today ${partialUsd(u.today.total, missing)}${limit ? ` of ${fmtUsd(limit)}` : ""} (all sessions)</div>`
    + (missing.length ? `<div class="hint">Not counted: no price for ${esc(missing.map(shortModel).join(", "))} in <span class="mono">${esc(tilde(u.prices.path))}</span>.</div>` : "");
}

// Before "Run all remaining": what the tasks so far suggest. With nothing to go on, it just runs.
async function estimateRunAll(spec, run) {
  const sid = state.sid;
  const left = (findSpec(spec.name) || spec).tasks.filter((t) => t.status !== "done").length;
  const d = await api(`/api/sessions/${sid}/turn-costs`).catch(() => null);
  if (state.sid !== sid) return;  // run() acts on the open session, and this click was for the other one
  const past = (d?.turns || []).filter((t) => t.cost != null && t.text.startsWith("Implement task ") && t.text.includes(` of spec ${spec.name}:`)).slice(-5);
  if (past.length) {
    const each = past.reduce((sum, t) => sum + t.cost, 0) / past.length;
    const ok = await confirmDialog("Run all remaining?", `About ${fmtUsd(each * left)} for ${plural(left, "task")} (average of the last ${plural(past.length, "task")}).`, "Run all");
    if (!ok || state.sid !== sid) return;
  }
  run();
}

function budgetBanner(ev) {
  const missing = ev.unpriced?.length ? ` Not counted, for lack of a price: ${esc(ev.unpriced.map(shortModel).join(", "))}.` : "";
  add(`<div class="banner error budget">Daily budget reached: ${fmtUsd(ev.spent)} of ${fmtUsd(ev.limit)}.${missing} <button class="btn sm" data-budget-continue>Continue anyway today</button></div>`);
}

$("#transcript").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-budget-continue]"); if (!b) return;
  try {
    await api("/api/budget/override", { method: "POST" });
    b.disabled = true; toast("Budget lifted until midnight. Send a message to carry on.");
  } catch (err) { toast(err.message, true); }
});
