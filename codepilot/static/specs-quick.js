"use strict";
// Quick specs: the Plan › Implement steps, with the three documents under Plan and one approval. A quick spec has the
// same phases as a full one, so only the steps differ. Also the hint on long documents. Uses app.js's helpers.

const QUICK_HINT = "A sentence or two. One review: codepilot drafts requirements, design and tasks together.";
const SPEC_DOCS = SPEC_PHASES.slice(0, 3);
const LONG_DOC = 200;

const isQuick = (spec) => spec.profile === "quick";
const quickTag = (spec) => (isQuick(spec) ? `<span class="incl">quick</span>` : "");
const specKindOf = (text) => (/\b(bug|broken|fails?|failing|error|crash|regression|wrong)\b/i.test(text) ? "bugfix" : "feature");

// "/spec quick add x" asks for a quick spec of "add x". The agent reads Spec mode messages the same way.
function specRequest(arg) {
  const m = /^quick(?:\s+(.*))?$/is.exec(arg.trim());
  return m ? { profile: "quick", description: (m[1] || "").trim() } : { profile: "full", description: arg };
}

// While planning any document can be shown; "implement" only exists once the plan is approved.
function quickView(spec, wanted) {
  const shown = spec.phase === "implement" ? SPEC_PHASES : SPEC_DOCS;
  return shown.includes(wanted) ? wanted : spec.phase;
}

function quickSteps(spec, view) {
  const building = spec.phase === "implement", planning = view !== "implement";
  return `<button class="sp-step ${building ? "done" : "current"} ${planning ? "on" : ""}" data-sp-view="requirements">${building ? icon("check") : `<span class="n">1</span>`}Plan</button><span class="sp-sep">›</span>`
    + `<button class="sp-step ${building ? "current" : "todo"} ${planning ? "" : "on"}" data-sp-view="implement" ${building ? "" : "disabled"}><span class="n">2</span>Implement</button>`;
}

const quickDocs = (spec, view) => `<div class="sp-sub">${SPEC_DOCS.map((doc) => `<button class="sp-step ${doc === view ? "on" : ""}" data-sp-view="${doc}">${esc(phaseLabel(spec, doc))}</button>`).join("")}</div>`;

function quickActions(spec) {
  if (spec.phase === "implement") return "";
  return `<button class="btn sm" id="spToFull" title="Keep these documents, and approve each one in turn">Switch to full review</button><button class="btn sm primary" id="spApprovePlan">${icon("check")}Approve plan &amp; continue</button>`;
}

async function switchToFull(spec, tab) {
  try {
    await api(`/api/sessions/${state.sid}/specs/${encodeURIComponent(spec.name)}/profile`, { method: "POST", body: { profile: "full" } });
    tab.view = null; await loadSpecs(true);
  } catch (err) { toast(err.message, true); }
}

function lengthHint(content) {
  const lines = (content ?? "").trimEnd().split("\n").length;
  return lines > LONG_DOC ? `<div class="hint sp-tip sp-long">This document is ${lines} lines. Long documents cost review time; consider trimming or splitting the spec.</div>` : "";
}
