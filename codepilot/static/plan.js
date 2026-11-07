"use strict";
// The plan checklist (update_plan). The live plan is pinned above the message box. When it's completed, replaced by
// a new plan, cleared or dismissed, it moves into the transcript as a card with its progress, so a plan never just
// vanishes. The server classifies each update (new / update / complete / clear / restore), live and on reload alike.
//
// The pinned plan says what's really happening, from what's running rather than from the model's last checklist: the
// step in progress spins only while a turn runs, it says when it's waiting for an approval, and a turn that ended with
// steps left shows where it paused, with Continue and Dismiss, instead of looking busy forever.

const PLAN_MARK = { done: "✓", doing: "→", todo: "○" };
const planItems = (items, running = false) => items.map((i) => `<div class="it ${esc(i.status)}">${running && i.status === "doing" ? '<span class="spinner"></span>' : '<span class="box"></span>'}<span>${esc(i.text)}</span></div>`).join("");
const planCount = (p) => `${p[0]} of ${p[1]} done`;

function resetPlan() { state.plan = null; renderPinnedPlan(); }

function planCard(title, items, prog, cls) {
  return `<details class="card plan-card ${cls}"><summary class="hd">${icon("list")}<span>${esc(title)}</span><span class="muted">· ${planCount(prog)}</span></summary><div class="plan-list">${planItems(items)}</div></details>`;
}

function onPlanEvent(ev) {
  if (ev.retired) add(planCard(ev.dismissed ? "Plan dismissed" : ev.kind === "clear" ? "Plan cleared" : "Plan replaced", ev.retired.items, ev.retired.progress, "retired"));
  if (ev.kind === "complete") add(planCard("✓ Plan complete", ev.items, ev.progress, "complete"));
  const done = ev.items.length && ev.items.every((i) => i.status === "done");
  // A finished plan restored by Edit/Retry stays out of the way, as after a reload: its card is in the transcript.
  state.plan = ev.items.length && !(ev.kind === "restore" && done) ? { items: ev.items, progress: ev.progress, complete: ev.kind === "complete" } : null;
  renderPinnedPlan();
}

// A finished plan stays pinned until you next write; by then it's in the transcript.
function planOnUserMessage() { if (state.plan?.complete) { state.plan = null; renderPinnedPlan(); } }

function planStatus(p) {
  if (p.complete) return "complete";
  if (state.streams.has(state.sid)) return "running";
  return state.approval ? "waiting" : "paused";
}
// The step to carry on from: the one in progress, else the first that isn't done.
function planNext(items) {
  const doing = items.findIndex((i) => i.status === "doing");
  return doing >= 0 ? doing : items.findIndex((i) => i.status !== "done");
}

function continuePlan() {
  const p = state.plan; if (!p) return;
  const n = planNext(p.items); if (n < 0) return;
  setInput(`Continue with the plan: next is step ${n + 1}, "${p.items[n].text}".`); send();
}

async function dismissPlan() {
  try { onPlanEvent(await api(`/api/sessions/${state.sid}/plan/dismiss`, { method: "POST" })); }
  catch (err) { toast(err.message, true); }
}

function renderPinnedPlan() {
  const el = $("#plan");
  const p = state.plan;
  if (!p) { el.hidden = true; el.innerHTML = ""; return; }
  const collapsed = store("cp-plan-collapsed") === "1";
  const hadFocus = document.activeElement?.classList.contains("plan-head");
  const pct = p.progress[1] ? Math.round((p.progress[0] / p.progress[1]) * 100) : 0;
  const status = planStatus(p), next = planNext(p.items);
  const said = { running: `<span class="plan-status">working…</span>`, waiting: `<span class="plan-status">Waiting for your approval</span>`,
    paused: next >= 0 ? `<span class="plan-status paused">Paused at step ${next + 1} of ${p.items.length}</span>` : "", complete: "" }[status];
  el.hidden = false;
  el.classList.toggle("complete", p.complete);
  el.innerHTML = `<div class="plan-head" role="button" tabindex="0" aria-expanded="${!collapsed}" aria-controls="planItems" title="${collapsed ? "Show" : "Hide"} the steps"><span class="chev" aria-hidden="true">${collapsed ? "▸" : "▾"}</span><b>${p.complete ? "✓ Plan complete" : "Plan"}</b>${said}<span class="muted">${planCount(p.progress)}</span><span class="spacer"></span><span class="pbar"><i style="width:${pct}%"></i></span></div>
    ${status === "paused" && next >= 0 ? `<div class="plan-acts"><button class="btn sm" id="planContinue" title="Ask codepilot to carry on from step ${next + 1}">Continue</button><button class="btn sm ghost" id="planDismiss" title="Put this plan away; codepilot is told">Dismiss</button></div>` : ""}
    <div class="plan-items" id="planItems" ${collapsed ? "hidden" : ""}>${planItems(p.items, status === "running")}</div>`;
  const head = $(".plan-head", el);
  const toggle = () => { store("cp-plan-collapsed", collapsed ? "0" : "1"); renderPinnedPlan(); };
  head.onclick = toggle;
  head.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); } };
  if (status === "paused") { $("#planContinue", el)?.addEventListener("click", continuePlan); $("#planDismiss", el)?.addEventListener("click", dismissPlan); }
  if (hadFocus) head.focus(); // re-rendering replaces the element; keep the keyboard where it was
}
