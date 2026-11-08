"use strict";
// Spec runs in the chat. "Run all remaining" (or one task's Run) shows its tasks as a task card (taskcard.js): each
// task holds the work its turn did, and ends done, paused (saying why) or failed, with its test result. The Spec tab
// stays the place for the documents; the card links to it rather than repeating them.
//
// The browser runs the tasks, one turn each, so it records the card with the session at each step (before a task's
// message, and when its turn ends): a reload draws the same card, and Edit/Retry take back what the rewound turns did.
// state.specRun is the run going on: { card, all, stopped, receipt }.

const RECEIPT_NOTE = { pass: "✓ verified", preexisting: "✓ no new failures", unverified: "⚠ may have tested the workspace's code", inconclusive: "⚠ verification inconclusive", error: "✗ couldn't verify", timeout: "verification timed out" };

function specRunCard(ev) {
  const card = newTaskCard(`Spec ${ev.spec}`);
  card.classList.add("spec-card"); card.dataset.run = ev.run; card.dataset.before = "Before the first task";
  const link = document.createElement("button");
  link.className = "btn sm ghost"; link.dataset.specOpen = ev.spec; link.textContent = "Open spec";
  link.title = "Open this spec's documents and tasks in the Spec tab";
  link.addEventListener("click", (e) => e.preventDefault()); // app.js opens the spec; the card stays open or folded
  card.querySelector(":scope > summary").append(link);
  add("<div></div>").replaceWith(card);
  return card;
}

// A state of a run's card, live (recordSpecRun) or replayed on reload.
function onSpecRun(ev) {
  const card = [...$$("#transcript .spec-card")].find((c) => c.dataset.run === ev.run) || specRunCard(ev);
  (card._states ||= []).push({ ev, by: lastUserMsg() }); // what a rewind past that message goes back to
  drawSpecRun(card, ev);
  return card;
}

function drawSpecRun(card, ev) {
  card._run = { run: ev.run, spec: ev.spec, items: ev.items.map((i) => ({ ...i })), ended: ev.ended, why: ev.why, receipt: ev.receipt };
  const n = ev.items.filter((i) => i.status === "done").length, was = card.dataset.active;
  setTaskItems(card, ev.items, `${n} of ${ev.items.length} done`);
  if (ev.ended === "complete") endTaskCard(card, `✓ Spec ${ev.spec} · ${plural(n, "task")} done`, "complete");
  else if (ev.ended) endTaskCard(card, `Spec ${ev.spec} · ${ev.ended === "stopped" ? "stopped" : `paused: ${ev.why}`}`, "retired");
  else {
    liveTaskCard(card);
    // A new task files here; the same task, now waiting for you, keeps filing where it was (a plan made inside it).
    if (card.dataset.active !== was || !card.contains(filingCard)) startFiling(card);
  }
}

// Draw the run's card as it is now (if its session is still the one open) and keep it with that session (before the
// message that follows, so a reload agrees). `receipt`: the verification before the task in progress, so a reload can
// tell its own from an older one.
async function recordSpecRun(run, sid = state.sid) {
  const ev = { type: "spec_run", run: run.run, spec: run.spec, items: run.items.map((i) => ({ ...i })), ended: run.ended || null,
    ...(run.why ? { why: run.why } : {}), ...(run.receipt !== undefined ? { receipt: run.receipt } : {}) };
  const card = sid === state.sid ? onSpecRun(ev) : null;
  try { await api(`/api/sessions/${sid}/spec-run`, { method: "POST", body: ev }); }
  catch (err) { toast(`The spec run's card won't survive a reload: ${err.message}`, true); }
  return card;
}

// Run one task (task given) or all that remain.
async function startSpecRun(spec, task = null) {
  if (state.streams.has(state.sid)) return toast("Wait for codepilot to finish (or press Stop) first.", true);
  if (state.specRun && state.specRun.card?.isConnected !== false) return toast("A spec run is already going: it carries on once you've answered what it's waiting for.", true);
  const tasks = task ? [task] : spec.tasks.filter((t) => t.status !== "done");
  if (!tasks.length) return toast("All tasks are done.");
  const run = { run: Date.now().toString(36), spec: spec.name, items: tasks.map((t) => ({ id: t.id, text: `${t.id}. ${t.title}`, status: "todo" })) };
  state.specRun = { all: !task, stopped: false }; // (set now: a second click while this starts runs nothing)
  await runSpecItem(spec, run, run.items[0]);
}

async function runSpecItem(spec, run, item) {
  const sid = state.sid, going = state.specRun;
  item.status = "doing"; delete item.note;
  run.receipt = going.receipt = state.receipt?.id ?? null; // a verification after this is this task's
  going.card = await recordSpecRun(run, sid);
  let failed = null;
  if (state.sid === sid && state.specRun === going) await ensureSpecActive(spec).catch((err) => { failed = err; });
  if (failed) { // the task would run against whichever spec is active: it doesn't start
    item.status = "todo"; run.ended = "paused"; run.why = `couldn't make spec ${spec.name} the active spec (${failed.message})`;
    state.specRun = null; toast(`Spec run paused: ${run.why}.`, true);
    return recordSpecRun(run, sid);
  }
  if (state.sid !== sid || state.specRun !== going) { // you opened another session meanwhile: this task doesn't start
    item.status = "todo"; run.ended = "stopped";
    return recordSpecRun(run, sid);
  }
  const task = spec.tasks.find((t) => t.id === item.id);
  setInput(`Implement task ${item.id} of spec ${spec.name}: ${task?.title ?? item.text}`); send();
}

// The run whose card is live: this one, or one left live by a reload or a Retry (it ends with the turn, not going on).
// `receipt` is the verification before its task's turn, when known.
function specRunGoing(receipt = undefined) {
  if (state.specRun?.card?.isConnected) return state.specRun;
  const card = [...$$("#transcript .spec-card.live")].at(-1);
  return card?._run ? (state.specRun = { card, all: false, stopped: false, receipt: receipt !== undefined ? receipt : card._run.receipt }) : null;
}

// The tests that marked it done (codepilot ran them: task_tests.py), or why it had none; or that they failed, the last
// time it tried (not a refusal for another reason, such as changes waiting for review).
const TESTS_FAILED = "The task's tests failed"; // task_tests.check's words
function doneNote(el) {
  const tried = [...(el?.querySelectorAll(".pi-steps details.tool[data-tool=update_task]") || [])].map((d) => {
    let input = null; try { input = JSON.parse(d.querySelector(":scope > .traw pre").textContent); } catch { /* not JSON */ }
    const ok = !!d.querySelector(":scope > summary .st.ok"), failed = !ok && !!d.querySelector(":scope > pre")?.textContent.startsWith(TESTS_FAILED);
    return input?.status === "done" && (ok || failed) ? { input, ok } : null;
  }).filter(Boolean).at(-1);
  if (!tried) return "";
  if (!tried.ok) return "✗ its tests fail";
  const n = (Array.isArray(tried.input.tests) ? tried.input.tests : String(tried.input.tests || "").split("\n")).filter((t) => String(t).trim()).length;
  return n ? `✓ ${plural(n, "test")} pass${n === 1 ? "es" : ""}` : tried.input.untested ? `not tested: ${tried.input.untested}` : "";
}

// What the task's turn shows of its tests: the tests that marked it done, else the verification made in it, else the
// last test run under it.
function testNote(going, el) {
  const marked = doneNote(el);
  if (marked) return marked;
  const r = state.receipt;
  if (r && going.receipt !== undefined && r.id !== going.receipt) return r.status === "fail" ? `✗ ${plural(r.newly_failing.length, "test")} newly failing` : RECEIPT_NOTE[r.status] || "";
  const ran = [...(el?.querySelectorAll(".pi-steps details.tool[data-tool=run_tests]") || [])]
    .map((d) => d.querySelector(":scope > summary .st")).filter((st) => st.matches(".ok, .warn, .err")).at(-1); // finished
  if (!ran) return "";
  return ran.classList.contains("ok") ? "tests pass" : ran.classList.contains("warn") ? "tests fail" : "tests didn't run";
}
function endedInError(msg) {
  for (let e = msg?.nextElementSibling; e; e = e.nextElementSibling) if (e.matches(".banner.error")) return true;
  return false;
}

// When a turn ends: how the task in progress went, then the next task, or the run ends (saying why).
async function afterSpecTurn() {
  const sid = state.sid;
  await loadSpecs(true);
  if (state.sid !== sid || state.streams.has(sid)) return; // e.g. you approved meanwhile: that turn's end settles it
  const going = specRunGoing();
  if (!going) return;
  const run = going.card._run, item = run.items.find((i) => i.status === "doing");
  if (!item) { state.specRun = null; return; }
  const spec = findSpec(run.spec), task = spec?.tasks.find((t) => t.id === item.id);
  const el = going.card.querySelector(":scope > .plan-list > .pi.doing");
  const pending = [...state.proposals.values()].some((p) => p.status === "pending");
  const tests = testNote(going, el);
  const note = (...parts) => parts.filter(Boolean).join(" · ");
  if (going.receipt !== undefined) run.receipt = going.receipt; // (a Retry's turn has its own)
  if (task?.status !== "done" && spec && !going.stopped && (state.approval || pending)) {
    // Not finished, but waiting for you: it carries on (and is filed here) once you approve or review.
    const waiting = note(state.approval ? "waiting for your approval" : "waiting for your review", tests);
    if (waiting !== item.note) { item.note = waiting; await recordSpecRun(run); } // (reopening a session changes nothing)
    return;
  }
  let why = null;
  if (!spec) { item.status = "paused"; item.note = "the spec is gone"; why = "the spec is gone"; }
  else if (task?.status === "done") { item.status = "done"; item.note = tests; }
  else if (endedInError(lastUserMsg())) { item.status = "failed"; item.note = note("ended in an error", tests); why = `task ${item.id} ended in an error`; }
  else { item.status = "paused"; item.note = note(going.stopped ? "stopped" : "not marked done", tests); why = `task ${item.id} isn't marked done`; }
  if (!item.note) delete item.note;
  const next = run.items.find((i) => i.status === "todo");
  if (!why && pending) why = "changes are waiting for your review (or tick auto-apply edits)";
  if (!why && state.approval) why = "a command needs your approval";
  if (!why && next && going.all && !going.stopped) return runSpecItem(spec, run, next);
  run.ended = !why && run.items.every((i) => i.status === "done") ? "complete" : going.stopped ? "stopped" : "paused";
  run.why = run.ended === "paused" ? why || "not all tasks ran" : undefined;
  state.specRun = null;
  await recordSpecRun(run);
  if (run.ended === "paused") toast(`Spec run paused: ${run.why}. Press Run next task to continue.`, true);
  else if (run.ended === "complete" && spec && !spec.tasks.some((t) => t.status !== "done")) toast(`Spec ${spec.name}: all tasks done.`);
}

// Stop: the task in progress ends as stopped, and the run doesn't go on.
function stopSpecRun() { if (state.specRun) state.specRun.stopped = true; }

// After Edit/Retry: each card goes back to what it said before the rewound messages (the server forgot the rest).
function specRunsRewound() {
  for (const card of $$("#transcript .spec-card")) {
    const states = (card._states || []).filter((s) => !s.by || s.by.isConnected);
    if (states.length === (card._states || []).length) continue;
    card._states = states;
    if (states.length) drawSpecRun(card, states.at(-1).ev); else card.remove();
  }
  // A card left live by that carries on with the retried turn, then ends: a verification from here on is that turn's.
  state.specRun = null;
  specRunGoing(state.receipt?.id ?? null);
}
