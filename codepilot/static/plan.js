"use strict";
// The plan checklist (update_plan). The plan is a card in the chat where it started (taskcard.js), with the work done
// under each step; the update_plan steps themselves don't show, since the card says what they did. When a plan is
// completed, replaced, cleared or dismissed, its card says so and folds away, so a plan never just vanishes. The server
// classifies each update (new / update / complete / clear / restore), live and on reload alike.
//
// The live plan is also pinned above the message box as one line, which says what's really happening, from what's
// running rather than from the model's last checklist: working, waiting for an approval, or paused (with Continue and
// Dismiss) instead of looking busy forever. A click takes you to the card, opened at the step in progress.

const planCount = (p) => `${p[0]} of ${p[1]} done`;

function resetPlan() { state.plan = null; state.planCard = null; resetTaskCards(); renderPinnedPlan(); }

// The update_plan step behind this event (one that didn't fail): the card takes its place, or it just goes.
const planRow = () => [...$$("#transcript details.tool[data-plan]")].filter((r) => !r.querySelector(":scope > summary .st.err")).at(-1);

function placePlanCard(row) {
  const card = newTaskCard("Plan");
  if (row?.dataset.filed) { card.dataset.filed = "1"; card._turn = row._turn; } // under a spec task: it goes with that turn
  (row || add("<div></div>")).replaceWith(card);
  return card;
}

const openCard = () => state.planCard?.isConnected && !state.planCard.classList.contains("complete") ? state.planCard : null;

function onPlanEvent(ev) {
  const row = ev.dismissed || ev.kind === "restore" ? null : planRow();
  if (ev.retired) {
    const title = ev.dismissed ? "Plan dismissed" : ev.kind === "clear" ? "Plan cleared" : "Plan replaced";
    const card = openCard() || placePlanCard(null);
    setTaskItems(card, ev.retired.items, planCount(ev.retired.progress));
    endTaskCard(card, title, "retired");
    state.planCard = null;
  }
  const live = openCard();
  if (!ev.items.length) state.planCard = null;
  else if (ev.kind === "restore") {
    state.planCard = [...$$("#transcript .plan-card:not(.spec-card)")].at(-1) || placePlanCard(null);
    reviveTaskCard(state.planCard); // live again only if the server says so
  } else if (ev.kind === "new" || !live) state.planCard = placePlanCard(row); // a new plan starts where it was made
  if (ev.kind === "restore") settleRewound();
  if (row?.isConnected) row.remove(); // its update is on the card
  const done = ev.items.length > 0 && ev.items.every((i) => i.status === "done");
  const card = state.planCard;
  if (card) {
    setTaskItems(card, ev.items, planCount(ev.progress));
    if (done && !card.classList.contains("complete")) endTaskCard(card, "✓ Plan complete", "complete");
    else if (!done) startFiling(card);
  } else if (!filingCard?.classList.contains("spec-card")) stopFiling(); // no plan; a spec run files on
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

// To the plan's card, opened at the step in progress (or the next one to do).
function showPlanCard() {
  const card = state.planCard;
  if (!card?.isConnected) return;
  card.open = true;
  const item = card.querySelector(":scope > .plan-list > .pi.doing") || card.querySelector(":scope > .plan-list > .pi.todo");
  if (item) item.open = true;
  (item || card).scrollIntoView({ block: "center", behavior: "smooth" });
}

function renderPinnedPlan() {
  for (const card of $$("#transcript .plan-card.live")) refreshTaskCard(card); // a step in progress spins only while a turn runs
  const el = $("#plan");
  const p = state.plan;
  if (!p) { el.hidden = true; el.innerHTML = ""; return; }
  const hadFocus = document.activeElement?.classList.contains("plan-head");
  const pct = p.progress[1] ? Math.round((p.progress[0] / p.progress[1]) * 100) : 0;
  const status = planStatus(p), next = planNext(p.items);
  const said = { running: `<span class="plan-status">working…</span>`, waiting: `<span class="plan-status">Waiting for your approval</span>`,
    paused: next >= 0 ? `<span class="plan-status paused">Paused at step ${next + 1} of ${p.items.length}</span>` : "", complete: "" }[status];
  el.hidden = false;
  el.classList.toggle("complete", p.complete);
  // One line: the header (a click goes to the card) and, when paused, its buttons beside it.
  el.innerHTML = `<div class="plan-line"><div class="plan-head" role="button" tabindex="0" title="Show the plan in the chat">${icon("list")}<b>${p.complete ? "✓ Plan complete" : "Plan"}</b>${said}<span class="muted">${planCount(p.progress)}</span><span class="spacer"></span><span class="pbar"><i style="width:${pct}%"></i></span></div>
    ${status === "paused" && next >= 0 ? `<div class="plan-acts"><button class="btn sm" id="planContinue" title="Ask codepilot to carry on from step ${next + 1}">Continue</button><button class="btn sm ghost" id="planDismiss" title="Put this plan away; codepilot is told">Dismiss</button></div>` : ""}</div>`;
  const head = $(".plan-head", el);
  head.onclick = showPlanCard;
  head.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); showPlanCard(); } };
  if (status === "paused") { $("#planContinue", el)?.addEventListener("click", continuePlan); $("#planDismiss", el)?.addEventListener("click", dismissPlan); }
  if (hadFocus) head.focus(); // re-rendering replaces the element; keep the keyboard where it was
}
