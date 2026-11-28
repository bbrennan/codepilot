"use strict";
// git where you work (spec git-changes): the Changes view's working tree, a list per repository in plain letters, and
// the Explorer's marks. app.js's loadGit fetches and calls renderGitView; renderTree ends with markTree. Loaded after
// app.js and folders.js, and uses their helpers.

const GIT_KINDS = {
  modified: { letter: "M", word: "Modified" }, untracked: { letter: "U", word: "Untracked" },
  added: { letter: "A", word: "Added" }, renamed: { letter: "R", word: "Renamed" },
  deleted: { letter: "D", word: "Deleted" }, conflict: { letter: "!", word: "Conflict" },
};

// Every repository's changed files and the folders that hold them, keyed as the Explorer names them: the main folder's
// relative, an added folder's by full path.
state.git = { files: new Map(), dirs: new Set(), roots: new Set() };

// The letter, with its tooltip in words. A screen reader is told in words by the row's own name ("core.py, modified":
// gitLabel), so the letter is hidden from it.
function gitMark(kind) {
  const k = GIT_KINDS[kind] || GIT_KINDS.modified;
  return `<span class="gmark" data-kind="${kind}" title="${k.word}" aria-hidden="true">${k.letter}</span>`;
}
const gitLabel = (name, kind) => `${name}, ${(GIT_KINDS[kind] || GIT_KINDS.modified).word.toLowerCase()}`;

// One repository's answer as the page uses it: its key (the commit request's `folder`: "" for the main folder, an added
// folder's full path), where its files are in the tree (prefix: "" or "<folder>/"), and the files.
function gitRepos(g) {
  const repos = [];
  if (g?.git) repos.push({ ...g, key: "", root: state.workspace, prefix: "", name: base(state.workspace) });
  for (const f of g?.folders || []) if (f.git) repos.push({ ...f, key: f.path, root: f.path, prefix: f.path + "/", name: base(f.path) });
  return repos;
}

// What you've done in each repository's part of the list, kept through a redraw (keyed as gitRepos does): the files you
// unticked (ticked is the default, so a new file arrives ticked), the message you're writing, and git's last refusal.
const gitWork = { unticked: new Map(), message: new Map(), refused: new Map(), committing: new Set(), shown: [] };
const gitUnticked = (key) => gitWork.unticked.get(key) || gitWork.unticked.set(key, new Set()).get(key);

function renderGitView(g) {
  state.git = { files: new Map(), dirs: new Set(), roots: new Set() };
  const repos = gitRepos(g);
  for (const r of repos) {
    for (const f of r.files || []) state.git.files.set(r.prefix + f.path, f);
    for (const d of r.dirs || []) state.git.dirs.add(r.prefix + d);
    if (r.files?.length) state.git.roots.add(r.root);
  }
  gitWork.shown = repos;
  const list = $("#gitList"), focus = gitFocusNow(list);
  list.innerHTML = (g?.git ? "" : `<div class="hint" style="padding:0 14px">Not a git repository.</div>`)
    + repos.map((r) => (r.key ? `<div class="group-head" title="${esc(tilde(r.path))}">${esc(r.name)} <span class="muted">· ${esc(r.branch)}</span></div>` : "") + gitListHtml(r)).join("");
  for (const r of repos) gitBoxState(r.key);
  gitFocusBack(list, focus);
  markTree();
}

function gitListHtml(r) {
  const files = r.files || [];
  if (!files.length) return '<div class="hint" style="padding:0 14px">Clean working tree.</div>';
  const more = r.total > files.length
    ? `<div class="hint git-more">${files.length.toLocaleString()} of ${r.total.toLocaleString()} changed files shown. A folder this big is usually one for .gitignore.</div>` : "";
  const off = gitUnticked(r.key), key = esc(r.key);
  const refused = gitWork.refused.get(r.key);
  return `<div class="git-head" data-groot="${key}"><input type="checkbox" class="gtick-all" data-gtickall="${key}" aria-label="Commit every file in ${esc(r.name)}"><span class="git-count"></span></div>`
    + (r.key ? "" : `<div class="row" id="openGitDiff">${icon("diff")}<span class="name">View working tree diff</span></div>`)
    + files.map((f) => gitRowHtml(r, f, !off.has(f.path))).join("") + more
    + `<div class="git-commit" data-groot="${key}">
        <textarea class="field" rows="2" data-gmsg="${key}" placeholder="Message" aria-label="Commit message for ${esc(r.name)}" spellcheck="true">${esc(gitWork.message.get(r.key) || "")}</textarea>
        <div class="git-commit-bar"><button class="btn primary sm gcommit" data-gcommit="${key}" aria-describedby="gitWhy-${esc(gitId(r.key))}"></button>
        <span class="hint git-why" id="gitWhy-${esc(gitId(r.key))}"></span></div>
        ${refused ? `<div class="banner error" role="alert">${esc(refused)}</div>` : ""}</div>`;
}
const gitId = (key) => key ? key.replace(/[^\w-]/g, "_") : "main";

// A row holds controls (a tick box, Discard), so the row itself isn't the button: the name is.
function gitRowHtml(r, f, on) {
  const path = r.prefix + f.path, k = GIT_KINDS[f.kind] || GIT_KINDS.modified;
  const tip = f.from ? `${k.word} from ${f.from}` : k.word;
  return `<div class="row git-row" data-git="${f.kind}" data-gitrow="${esc(path)}">`
    + `<input type="checkbox" class="gtick" data-gtick="${esc(f.path)}" data-groot="${esc(r.key)}" aria-label="Commit ${esc(f.path)}"${on ? " checked" : ""}>`
    + `<button class="gname" data-gitfile="${esc(path)}" title="${esc(shownPath(path))}: ${esc(tip)}" aria-label="${esc(gitLabel(f.path, f.kind))}">${fileIcon(path)}<span class="name">${esc(f.path)}</span>${gitMark(f.kind)}</button>`
    + `<button class="icon-btn sm gdiscard" data-gdiscard="${esc(path)}" data-grel="${esc(f.path)}" data-groot="${esc(r.key)}" title="Discard changes" aria-label="Discard changes to ${esc(f.path)}">${icon("history")}</button></div>`;
}

// The count, the tick-all box and Commit with the reason it can't be pressed, from what's ticked and typed: drawn in
// place on every tick and keystroke, never by redrawing the list (which would move focus).
function gitBoxState(key) {
  const r = gitWork.shown.find((x) => x.key === key); if (!r) return;
  const files = r.files || [], off = gitUnticked(key);
  const ticked = files.filter((f) => !off.has(f.path)).length;
  const sel = `[data-groot="${CSS.escape(key)}"]`;
  const head = $(`#gitList .git-head${sel}`), commitBox = $(`#gitList .git-commit${sel}`);
  if (!head || !commitBox) return;
  head.querySelector(".git-count").textContent = `${ticked} of ${files.length}`;
  const all = head.querySelector(".gtick-all");
  all.checked = ticked === files.length; all.indeterminate = ticked > 0 && ticked < files.length;
  const why = gitWhy(key, ticked), button = commitBox.querySelector(".gcommit");
  button.textContent = gitWork.committing.has(key) ? "Committing…" : `Commit ${ticked}`;
  button.disabled = !!why;
  commitBox.querySelector(".git-why").textContent = why;
}
function gitWhy(key, ticked) {
  if (gitWork.committing.has(key)) return "";
  // A turn paused for approval hasn't finished: the agent may be between two writes of one change. r.working: a
  // session that shares this folder is working (the server refuses then too, whatever the page knew).
  const working = state.streams.has(state.sid) || state.approval || gitWork.shown.find((x) => x.key === key)?.working;
  if (working) return "codepilot is working: commit when the turn is done.";
  if (!ticked) return "Tick at least one file to commit.";
  if (!(gitWork.message.get(key) || "").trim()) return "Write a message to commit.";
  return "";
}
// app.js's updateBusy: a turn started or ended, so Commit may be pressed or not.
function gitBusyChanged() { for (const r of gitWork.shown) gitBoxState(r.key); }

async function gitCommit(key) {
  const r = gitWork.shown.find((x) => x.key === key); if (!r) return;
  const off = gitUnticked(key), paths = (r.files || []).filter((f) => !off.has(f.path)).map((f) => f.path);
  const message = gitWork.message.get(key) || "";
  if (gitWhy(key, paths.length)) return;
  const sid = state.sid;
  gitWork.committing.add(key); gitWork.refused.delete(key); gitBoxState(key);
  try {
    const d = await api(`/api/sessions/${sid}/git/commit`, { method: "POST", body: { ...(key ? { folder: key } : {}), message, paths } });
    if (state.sid !== sid) return;
    gitWork.message.delete(key);
    for (const p of paths) off.delete(p);
    toast(`Committed ${d.hash}: ${d.subject}`);
  } catch (err) {
    gitWork.refused.set(key, err.message); // git's own words (a hook's output), under the box
  } finally {
    gitWork.committing.delete(key);
    await loadGit();
    $(`#gitList textarea[data-gmsg="${CSS.escape(key)}"]`)?.focus(); // where you write the next one
  }
}

// ---- Discard
// What it does, in words, before it does it: a file the last commit has goes back to it; one it hasn't leaves for the
// trash. Undo is in the toast; the open tab follows either way (gitTabFollows).
function gitDiscardHint(rel, f, tab) {
  const hint = f.kind === "deleted" ? `${rel} comes back as it was in the last commit.`
    : f.kind === "renamed" ? `${rel} goes back to ${f.from}, as in the last commit; ${rel} moves to codepilot's trash, and Undo puts it back.`
    : f.kind === "untracked" || f.kind === "added" ? `${rel} isn't in the last commit, so it moves to codepilot's trash; Undo puts it back.`
    : `${rel} goes back to the last commit. Your changes move to codepilot's trash; Undo puts them back.`;
  return hint + (tab?.dirty ? " Your unsaved edits in the open tab are lost too." : "");
}
async function gitDiscard(button) {
  const { groot: key, grel: rel, gdiscard: path } = button.dataset;
  const f = state.git.files.get(path); if (!f) return;
  const tab = state.tabs.find((t) => t.id === "file:" + path);
  if (!(await confirmDialog(`Discard changes to ${rel}?`, gitDiscardHint(rel, f, tab), "Discard"))) return;
  const sid = state.sid;
  try {
    const d = await api(`/api/sessions/${sid}/git/discard`, { method: "POST", body: { ...(key ? { folder: key } : {}), path: rel } });
    if (state.sid !== sid) return;
    await gitTabFollows(path, d.gone);
    toast(`Discarded changes to ${rel}`, false, { label: "Undo", run: () => gitUndo(sid, d.trash_id, path) });
  } catch (err) { toast(err.message, true); }
  if (state.sid === sid) loadGit();
}
async function gitUndo(sid, trashId, path) {
  try {
    const back = await api(`/api/sessions/${sid}/fs`, { method: "POST", body: { op: "restore", trash_id: trashId } });
    if (state.sid !== sid) return;
    await gitTabFollows(path, false);
    toast(`Put back ${shownPath(back.path)}`);
  } catch (err) { toast(err.message, true); } // (refused: the file changed since, and the kept copy stays in the trash)
  if (state.sid === sid) loadGit();
}
// The open tab of a file whose changes were just discarded or put back: its unsaved edits went with them, so the draft
// is forgotten (tabstate.js keeps one only while a tab is dirty, and is told at once), and it shows the file as it now
// is, through the editor's handle when it's in Edit mode; or it closes, without asking, when the file is gone.
async function gitTabFollows(path, gone) {
  const tab = state.tabs.find((t) => t.id === "file:" + path); if (!tab) return;
  tab.dirty = false; tab.draft = null;
  if (gone) { await closeTab(tab.id); saveTabs(); return; }
  const f = await api(`/api/sessions/${state.sid}/files?path=${encodeURIComponent(path)}`).catch(() => null);
  if (f && f.content != null) {
    Object.assign(tab, { content: f.content, mtime: f.mtime, encoding: f.encoding }, tab.editing ? { draft: f.content } : {});
    if (tab.ed) tab.ed.setText(f.content); // editor.js: in place, so the caret and the scroll stay
    else if (state.active === tab.id) renderEditor();
  }
  renderTabs(); saveTabs();
}

$("#gitList").addEventListener("click", (e) => {
  if (e.target.closest("#openGitDiff")) return openGitDiff();
  const c = e.target.closest("[data-gcommit]"); if (c) return gitCommit(c.dataset.gcommit);
  const x = e.target.closest("[data-gdiscard]"); if (x) return gitDiscard(x);
  const r = e.target.closest("[data-gitfile]"); if (!r) return;
  const path = r.dataset.gitfile;
  // What was deleted is shown as a diff: there's no file to open.
  if (state.git.files.get(path)?.kind === "deleted") openGitDiff(path); else openFile(path);
});
$("#gitList").addEventListener("change", (e) => {
  const t = e.target;
  if (t.matches(".gtick")) { const off = gitUnticked(t.dataset.groot); t.checked ? off.delete(t.dataset.gtick) : off.add(t.dataset.gtick); gitBoxState(t.dataset.groot); }
  if (t.matches(".gtick-all")) {
    const key = t.dataset.gtickall, off = gitUnticked(key), r = gitWork.shown.find((x) => x.key === key);
    for (const f of r?.files || []) t.checked ? off.delete(f.path) : off.add(f.path);
    for (const b of $$(`#gitList .gtick[data-groot="${CSS.escape(key)}"]`)) b.checked = t.checked;
    gitBoxState(key);
  }
});
$("#gitList").addEventListener("input", (e) => {
  if (!e.target.matches("[data-gmsg]")) return;
  gitWork.message.set(e.target.dataset.gmsg, e.target.value); gitBoxState(e.target.dataset.gmsg);
});
// ⌘Enter in a message box commits, or does nothing when Commit can't be pressed. It never reaches app.js's own
// ⌘Enter, which would approve a command waiting for approval wherever focus is.
$("#gitList").addEventListener("keydown", (e) => {
  if (!e.target.matches("[data-gmsg]") || e.key !== "Enter" || !(isMac ? e.metaKey : e.ctrlKey) || e.isComposing) return;
  e.preventDefault(); e.stopPropagation();
  gitCommit(e.target.dataset.gmsg);
});

// ---- focus through a redraw
// The control that had focus, by what identifies it (its data attribute), with its row's place in the list and a
// text box's selection; put back after the list is drawn again. A control whose row went (committed, discarded) gives
// focus to the same control in the row that took its place, else to its repository's message box.
const GIT_FOCUS_ATTRS = ["gtick", "gitfile", "gdiscard", "gmsg", "gcommit", "gtickall"];
function gitFocusNow(list) {
  const el = document.activeElement;
  if (!el || !list.contains(el) || el === list) return null;
  const attr = GIT_FOCUS_ATTRS.find((a) => el.dataset[a] != null); if (!attr) return null;
  const row = el.closest(".git-row");
  return { attr, value: el.dataset[attr], root: el.dataset.groot ?? row?.querySelector(".gtick")?.dataset.groot ?? el.dataset[attr],
    index: row ? [...list.querySelectorAll(".git-row")].indexOf(row) : -1,
    sel: el.tagName === "TEXTAREA" ? [el.selectionStart, el.selectionEnd] : null };
}
function gitFocusBack(list, was) {
  if (!was) return;
  const name = was.attr.replace(/[A-Z]/g, (c) => "-" + c.toLowerCase());
  let el = list.querySelector(`[data-${name}="${CSS.escape(was.value)}"]`);
  if (!el && was.index >= 0) {
    const rows = [...list.querySelectorAll(".git-row")];
    el = (rows[was.index] || rows.at(-1))?.querySelector(`[data-${name}]`);
  }
  el ||= list.querySelector(`textarea[data-gmsg="${CSS.escape(was.root || "")}"]`) || list.querySelector("textarea[data-gmsg]");
  if (!el) return;
  el.focus({ preventScroll: true });
  if (was.sel && el.tagName === "TEXTAREA") el.setSelectionRange(...was.sel);
}

// ---- the Explorer
// Each row of a changed file gets its letter (and data-git, for the name's colour); each folder that holds one, a dot.
// A folder of the session (folders.js) gets the dot when its repository has changes.
function markTree() {
  for (const row of $$("#tree .row[data-file], #tree .row[data-dir], #tree .row.root")) {
    row.querySelector(".gmark")?.remove();
    const path = row.dataset.file ?? row.dataset.dir;
    const f = row.dataset.file != null ? state.git.files.get(path) : null;
    const dot = !f && (path != null ? state.git.dirs.has(path) : state.git.roots.has(row.dataset.root));
    if (f) row.dataset.git = f.kind; else delete row.dataset.git;
    if (row.dataset.gitLabel) { row.removeAttribute("aria-label"); delete row.dataset.gitLabel; }
    if (!f && !dot) continue;
    const name = row.querySelector(".name")?.textContent || "";
    row.setAttribute("aria-label", f ? gitLabel(name, f.kind) : `${name}, contains changes`); row.dataset.gitLabel = "";
    const mark = f ? gitMark(f.kind) : `<span class="gmark dot" title="Contains changes" aria-hidden="true">●</span>`;
    const at = row.querySelector(".hover-act");
    at ? at.insertAdjacentHTML("beforebegin", mark) : row.insertAdjacentHTML("beforeend", mark);
  }
}
