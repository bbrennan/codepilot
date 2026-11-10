"use strict";
// Progress: the session's plans and spec runs, as task cards (taskcard.js) in a sidebar view, so they don't scroll away
// while the conversation goes on. The chat keeps one line where each started (its marker): how far it got, or how it
// ended, and a link that opens the view at it. The activity-bar icon counts while one is live. The sidebar switches
// here when a card starts during a turn (once: a card is placed once), never while a session's history is replayed.

// Where filed work can be: the chat, or under a step of a card in the view.
const CHAT_AND_PROGRESS = ":is(#transcript, #progressList)";

// Put a card in the view (newest first) and its marker in the chat: in place of `at`, else at the end.
function placeTaskCard(card, at = null) {
  const mark = document.createElement("div");
  mark.className = "progress-mark"; mark.setAttribute("role", "button"); mark.tabIndex = 0;
  mark.title = "Show it in Progress";
  mark.innerHTML = `${icon("list")}<span class="pm-t"></span><span class="btn sm ghost" data-progress-open>View progress</span>`;
  mark._card = card; card._marker = mark;
  (at || add("<div></div>")).replaceWith(mark);
  $("#progressList").prepend(card);
  if (!state.replaying) setView("progress");
  refreshProgress();
  return card;
}

// The newest of the cards a selector finds (the view lists newest first, but a plan made inside a spec task sits under
// it, so document order isn't age).
const newestCard = (sel) => [...$$(sel)].reduce((a, c) => (!a || c._seq > a._seq ? c : a), null);

// Markers say what their card says; the icon counts the live card's steps.
function refreshProgress() {
  for (const m of $$("#transcript .progress-mark")) {
    const card = m._card;
    m.querySelector(".pm-t").textContent = card ? `${card.querySelector(".ttl").textContent} ${card.querySelector(".cnt").textContent}`.trim() : "";
    m.classList.toggle("live", !!card?.classList.contains("live"));
  }
  // The run (or plan) under way; else a plan still live inside a run that ended.
  const live = newestCard("#progressList > .plan-card.live") || newestCard("#progressList .plan-card.live"), badge = $("#progressBadge");
  const items = live ? [...live.querySelectorAll(":scope > .plan-list > .pi:not(.before):not(.gone)")] : [];
  const done = items.filter((i) => i.classList.contains("done")).length;
  badge.hidden = !items.length;
  badge.textContent = items.length ? `${done}/${items.length}` : "";
  // (the badge's text would otherwise become the button's name)
  $("#activitybar [data-view=progress]").setAttribute("aria-label", items.length ? `Progress, ${done} of ${items.length} done` : "Progress");
  $("#progressList > .progress-empty").hidden = !!$("#progressList > .plan-card");
}

// Open the view at a card, unfolded at its step in progress (or the next to do).
function showProgress(card) {
  if (!card?.isConnected) return;
  setView("progress");
  card.open = true;
  const item = card.querySelector(":scope > .plan-list > .pi.doing") || card.querySelector(":scope > .plan-list > .pi.todo");
  if (item) item.open = true;
  (item || card).scrollIntoView({ block: "nearest" });
}

// After a rewind: a card whose marker went with the rewound messages goes too (one made under a spec task goes with
// its filed work, taskcard.js).
function dropRewoundCards() {
  for (const card of $$("#progressList > .plan-card")) if (card._marker && !card._marker.isConnected) card.remove();
}

function clearProgress() { for (const card of $$("#progressList > .plan-card")) card.remove(); refreshProgress(); }

const openMark = (e) => { const m = e.target.closest(".progress-mark"); if (m) showProgress(m._card); return !!m; };
$("#transcript").addEventListener("click", openMark);
$("#transcript").addEventListener("keydown", (e) => { if ((e.key === "Enter" || e.key === " ") && e.target.matches(".progress-mark") && openMark(e)) e.preventDefault(); });
