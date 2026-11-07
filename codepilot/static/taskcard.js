"use strict";
// Task cards: a list of steps in the chat (a plan's items; a spec run's tasks), each holding the work done under it.
// While a card is filing, each step row that arrives (a tool call, a group of reads, a change) goes under the card's
// item in progress, or the last one that was, or "Before the plan" while none has started. codepilot's words stay in
// the chat. Each filed row remembers the message it came from, so Edit and Retry, which rewind the chat to a message,
// take that work back out of the card, and a card that ended after that message comes back to life.

let filingCard = null;
const itemKey = (text) => String(text).toLowerCase().split(/\s+/).filter(Boolean).join(" ");
const lastUserMsg = () => [...document.querySelectorAll("#transcript > .msg.user:not(.queued)")].at(-1) || null;

function newTaskCard(title) {
  const d = document.createElement("div");
  d.innerHTML = `<details class="card plan-card live" open><summary class="hd">${icon("list")}<span class="ttl"></span><span class="muted cnt"></span></summary><div class="plan-list"></div></details>`;
  const card = d.firstElementChild;
  card.dataset.title = title; card.querySelector(".ttl").textContent = title;
  return card;
}

function taskItemEl(text, cls) {
  const d = document.createElement("div");
  d.innerHTML = `<details class="pi it ${cls}"><summary><span class="mk"></span><span class="t"></span><span class="n muted"></span></summary><div class="pi-steps"></div></details>`;
  const el = d.firstElementChild; el.querySelector(".t").textContent = text;
  return el;
}

// The card's items, in order, keeping the work already filed under each (matched by text, and by which occurrence
// for two steps of the same name). An item dropped from the list keeps its work, marked as dropped; one with no work
// just goes. The item in progress becomes where work is filed, and the card remembers which message made it so: a
// rewind past that message files under the one before again.
function setTaskItems(card, items, count) {
  const list = card.querySelector(":scope > .plan-list");
  const old = new Map([...list.querySelectorAll(":scope > .pi[data-key]")].map((e) => [e.dataset.key, e]));
  const keep = [], seen = new Map();
  for (const it of items) {
    const base = itemKey(it.text), nth = (seen.get(base) || 0) + 1; seen.set(base, nth);
    const key = `${base}#${nth}`;
    const el = old.get(key) || taskItemEl(it.text, ""); old.delete(key);
    el.dataset.key = key; el.className = `pi it ${it.status}`; el.querySelector(".t").textContent = it.text;
    if (it.status === "doing" && card.dataset.active !== key) {
      card.dataset.active = key; (card._actives ||= []).push({ key, by: lastUserMsg() });
    }
    keep.push(el);
  }
  for (const el of old.values()) if (stepsIn(el).length) { el.className = "pi it gone"; keep.push(el); } else el.remove();
  list.append(...keep);
  card.querySelector(".cnt").textContent = count ? `· ${count}` : "";
  refreshTaskCard(card);
}

const stepsIn = (item) => [...item.querySelector(":scope > .pi-steps").children];

// Marks and counts. Only the item in progress of a card that's filing spins, and only while a turn runs. The mark says
// its status in words too, for a screen reader.
const MARK_LABEL = { done: "Done", doing: "In progress", todo: "To do", before: "Before any step", gone: "Dropped from the plan" };
function refreshTaskCard(card, running = state.streams.has(state.sid)) {
  for (const item of card.querySelectorAll(":scope > .plan-list > .pi")) {
    const spin = running && card === filingCard && item.classList.contains("doing");
    const mk = item.querySelector(".mk"), status = Object.keys(MARK_LABEL).find((c) => item.classList.contains(c));
    mk.innerHTML = spin ? '<span class="spinner"></span>' : '<span class="box"></span>';
    mk.setAttribute("role", "img"); mk.setAttribute("aria-label", MARK_LABEL[status] || "");
    const n = stepsIn(item).length;
    item.querySelector(".n").textContent = n ? `${n} step${n === 1 ? "" : "s"}` : "";
  }
}

function startFiling(card) { if (filingCard && filingCard !== card) refreshTaskCard(filingCard, false); filingCard = card; }
function stopFiling(card) { if (!card || card === filingCard) { const was = filingCard; filingCard = null; if (was) refreshTaskCard(was, false); } }

// A card that's done (finished, replaced, dismissed): its title says how, it folds away, and it stops filing.
function endTaskCard(card, title, cls) {
  stopFiling(card);
  card.classList.remove("live", "retired", "complete"); card.classList.add(cls);
  card.querySelector(".ttl").textContent = title; card.open = false;
  card._endedBy = lastUserMsg();
}

// A tool step as it's drawn. update_plan steps make the plan card rather than work under it (plan.js).
function fileToolStep(el, ev) {
  if (ev.name === "update_plan") el.dataset.plan = "1";
  else fileStep(el);
}

function fileStep(el) {
  const card = filingCard;
  if (!card?.isConnected || !el) return;
  const list = card.querySelector(":scope > .plan-list");
  let item = card.dataset.active && list.querySelector(`:scope > .pi[data-key="${CSS.escape(card.dataset.active)}"]`);
  if (!item) {
    item = list.querySelector(":scope > .pi.before");
    if (!item) { item = taskItemEl(card.dataset.before || "Before the plan", "before"); list.prepend(item); }
  }
  // What the chat showed just before this step (thinking aside): two reads are a run only if nothing came between.
  let tail = el.previousElementSibling; while (tail?.matches(".thinking")) tail = tail.previousElementSibling;
  el._tail = tail;
  item.querySelector(":scope > .pi-steps").append(el);
  el.dataset.filed = "1"; el._turn = lastUserMsg();
  refreshTaskCard(card);
}

// After a rewind: the work from the removed messages leaves the cards. A card they ended may be live again, which the
// server's restore event decides (reviveTaskCard): a plan you dismissed after them stays dismissed.
function unfileRewound() {
  for (const el of document.querySelectorAll("#transcript .pi-steps [data-filed]")) if (!el._turn?.isConnected) el.remove();
  for (const g of document.querySelectorAll("#transcript .pi-steps details.step-group")) refreshReadGroup(g);
  for (const item of document.querySelectorAll("#transcript .pi.before, #transcript .pi.gone")) if (!stepsIn(item).length) item.remove();
  for (const card of document.querySelectorAll("#transcript .plan-card")) {
    card._actives = (card._actives || []).filter((a) => a.by?.isConnected);
    if (card._actives.length) card.dataset.active = card._actives.at(-1).key; else delete card.dataset.active;
    card._rewound = !!card._endedBy && !card._endedBy.isConnected; // may come back: the restore event decides
    refreshTaskCard(card);
  }
}

// After a rewind, the card whose plan the server says is live again (not one you dismissed, which stays put away).
function reviveTaskCard(card) {
  if (!card?._rewound) return;
  card.classList.remove("retired", "complete"); card.classList.add("live"); card.open = true;
  card.querySelector(".ttl").textContent = card.dataset.title; card._endedBy = null;
}
function settleRewound() { for (const card of document.querySelectorAll("#transcript .plan-card")) card._rewound = false; }

function resetTaskCards() { filingCard = null; }
