"use strict";
// The plan checklist (update_plan). The live plan is pinned above the message box. When it's completed, replaced by
// a new plan, or cleared, it moves into the transcript as a card with its progress, so a plan never just vanishes.
// The server classifies each update (new / update / complete / clear / restore), live and on reload alike.

const PLAN_MARK = { done: "✓", doing: "→", todo: "○" };
const planItems = (items) => items.map((i) => `<div class="it ${esc(i.status)}"><span class="box"></span><span>${esc(i.text)}</span></div>`).join("");
const planCount = (p) => `${p[0]} of ${p[1]} done`;

function resetPlan() { state.plan = null; renderPinnedPlan(); }

function planCard(title, items, prog, cls) {
  return `<details class="card plan-card ${cls}"><summary class="hd">${icon("list")}<span>${esc(title)}</span><span class="muted">· ${planCount(prog)}</span></summary><div class="plan-list">${planItems(items)}</div></details>`;
}

function onPlanEvent(ev) {
  if (ev.retired) add(planCard(ev.kind === "clear" ? "Plan cleared" : "Plan replaced", ev.retired.items, ev.retired.progress, "retired"));
  if (ev.kind === "complete") add(planCard("✓ Plan complete", ev.items, ev.progress, "complete"));
  const done = ev.items.length && ev.items.every((i) => i.status === "done");
  // A finished plan restored by Edit/Retry stays out of the way, as after a reload: its card is in the transcript.
  state.plan = ev.items.length && !(ev.kind === "restore" && done) ? { items: ev.items, progress: ev.progress, complete: ev.kind === "complete" } : null;
  renderPinnedPlan();
}

// A finished plan stays pinned until you next write; by then it's in the transcript.
function planOnUserMessage() { if (state.plan?.complete) { state.plan = null; renderPinnedPlan(); } }

function renderPinnedPlan() {
  const el = $("#plan");
  const p = state.plan;
  if (!p) { el.hidden = true; el.innerHTML = ""; return; }
  const collapsed = store("cp-plan-collapsed") === "1";
  const hadFocus = document.activeElement?.classList.contains("plan-head");
  const pct = p.progress[1] ? Math.round((p.progress[0] / p.progress[1]) * 100) : 0;
  el.hidden = false;
  el.classList.toggle("complete", p.complete);
  el.innerHTML = `<div class="plan-head" role="button" tabindex="0" aria-expanded="${!collapsed}" aria-controls="planItems" title="${collapsed ? "Show" : "Hide"} the steps"><span class="chev" aria-hidden="true">${collapsed ? "▸" : "▾"}</span><b>${p.complete ? "✓ Plan complete" : "Plan"}</b><span class="muted">${p.progress[0]} of ${p.progress[1]} done</span><span class="spacer"></span><span class="pbar"><i style="width:${pct}%"></i></span></div>
    <div class="plan-items" id="planItems" ${collapsed ? "hidden" : ""}>${planItems(p.items)}</div>`;
  const head = $(".plan-head", el);
  const toggle = () => { store("cp-plan-collapsed", collapsed ? "0" : "1"); renderPinnedPlan(); };
  head.onclick = toggle;
  head.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); } };
  if (hadFocus) head.focus(); // re-rendering replaces the element; keep the keyboard where it was
}
