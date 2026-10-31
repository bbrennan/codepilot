"use strict";
// Package guard: what the registry says about dependencies a change adds. Install commands show it on the approval
// (policy.js); this is for changes, in the Review tab and on their line in the chat. Uses app.js's helpers.

const depMark = (p) => ((p.advice || []).some((a) => a.level !== "info") ? `<span class="dep-mark" title="Check this dependency: see Review">${icon("alert")}</span>` : "");

function depAdvice(p) {
  if (!(p.advice || []).length) return "";
  return `<div class="dep-advice">${p.advice.map((a) => `<div class="dep ${esc(a.level)}">${icon("alert")}<span><b class="mono">${esc(a.name)}</b> ${esc(a.text)}</span></div>`).join("")}</div>`;
}
