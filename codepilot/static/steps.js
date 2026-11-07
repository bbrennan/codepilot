"use strict";
// Steps in plain words: each tool call in the chat reads as a verb and its object ("Read agent/core.py", "Ran the
// tests"), not as a tool name and its JSON, which stay one click away in the row. Live and on reload alike, since both
// go through toolEl. A tool without a phrasing here still reads "Used <tool> …".

const base_ = (p) => String(p || "").replace(/\/+$/, "").split("/").pop();
const firstLine = (s) => String(s || "").split("\n")[0].trim();
const STEP_TEXT = {
  open_workspace: (i) => ["Opened", base_(i.path)],
  list_files: (i) => ["Listed", `${i.pattern ? i.pattern + " " : ""}files in ${!i.path || i.path === "." ? "the workspace" : i.path}`],
  // Without end_line, read_file reads a window from start_line, not the rest of the file: say "from line", not "–end".
  read_file: (i) => ["Read", i.path + (i.end_line ? ` lines ${i.start_line || 1}–${i.end_line}`
    : i.start_line > 1 ? ` from line ${i.start_line}` : "")],
  search_code: (i) => ["Searched for", i.pattern + (i.path && i.path !== "." ? ` in ${i.path}` : "")],
  git: (i) => ["Ran", `git ${i.args || ""}`.trim()],
  explore: (i) => ["Explored:", firstLine(i.task)],
  run_tests: (i) => ["Ran the tests", i.args || ""],
  run_checks: (i) => [i.kind && i.kind !== "all" ? `Ran the ${i.kind} checks` : "Ran the checks", i.paths || ""],
  run_command: (i) => ["Ran", firstLine(i.command) + (String(i.command || "").includes("\n") ? " …" : "")],
  list_traces: () => ["Listed the traces", ""],
  trace_outline: (i) => ["Outlined the trace", i.path],
  search_traces: (i) => ["Searched the traces for", i.query],
  read_trace: (i) => ["Read the trace", i.path],
  write_scratch: (i) => ["Wrote a scratch file", i.name],
  propose_edit: (i) => [i.old_text === "" ? "Proposed a new file" : "Proposed a change to", i.path],
  update_plan: (i) => Array.isArray(i.items)
    ? ["Updated the plan", `${i.items.filter((x) => x.status === "done").length} of ${i.items.length} done`]
    : ["Updated the plan", ""],
  load_skill: (i) => ["Loaded the skill", i.name],
  recall: (i) => ["Recalled", i.query],
  write_spec: (i) => ["Wrote", `${i.doc || "spec"}.md · ${String(i.content || "").split("\n").length} lines`],
  update_task: (i) => [`Marked task ${i.task}`, String(i.status || "").replace("_", " ")],
  verify_changes: () => ["Verified the pending changes", ""],
  view_image: (i) => ["Looked at", /^https?:/i.test(i.source || "") ? i.source : base_(i.source)],
  remember: () => ["Saved a note for this folder", ""],
  library_docs: (i) => ["Looked up", `${i.library} docs`],
  web_fetch: (i) => ["Fetched", i.url],
  web_search: (i) => ["Searched the web for", i.query],
  github: (i) => ["Ran", `gh ${String(i.args || "").replace(/^gh /, "")}`],
  cloudwatch_logs: (i) => ["Searched the logs in", i.log_group],
};

// [verb, object] for a tool call. The object may be "" (nothing more to say).
function stepText(name, input) {
  const phrase = STEP_TEXT[name];
  if (phrase && input) {
    try {
      const [verb, object] = phrase(input);
      return [verb, String(object ?? "")];
    } catch { /* odd arguments: fall through to the generic form */ }
  }
  return [`Used ${name}`, input ? argSummary(name, input) : ""];
}

// One row per change: a propose_edit step that made a change gives its place to the change's own row (file, +/−,
// Apply/Reject), which says what the step would. Live, the change arrives before the step's result; on reload, after
// it; so whichever comes second makes the swap. Anything the result adds after its first line (what the checks found
// after an auto-apply, a package that doesn't exist) moves into the change row. A step that failed stays, error and all.
function changeStepDone(el, ev) {
  const m = ev.name === "propose_edit" && !ev.is_error && /^(?:Proposed|Applied) change #(\d+)[^\n]*\n?([\s\S]*)/.exec(ev.output);
  if (!m) return;
  el.dataset.change = m[1]; el.dataset.note = m[2].trim();
  foldChangeStep(m[1]);
}
function foldChangeStep(id) {
  const step = document.querySelector(`#transcript details.tool[data-change="${id}"]`);
  const card = document.querySelector(`#transcript .card.prop[data-prop="${id}"]`);
  if (!step || !card) return;
  if (step.dataset.note) card.insertAdjacentHTML("beforeend", `<pre class="step-note">${esc(step.dataset.note)}</pre>`);
  step.replaceWith(card);
}
