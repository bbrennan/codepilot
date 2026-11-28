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

// One repository's answer as the page uses it: where its files are (prefix: "" or "<folder>/"), and the files.
function gitRepos(g) {
  const repos = [];
  if (g?.git) repos.push({ root: state.workspace, prefix: "", main: true, ...g });
  for (const f of g?.folders || []) if (f.git) repos.push({ root: f.path, prefix: f.path + "/", main: false, ...f });
  return repos;
}

function renderGitView(g) {
  state.git = { files: new Map(), dirs: new Set(), roots: new Set() };
  for (const r of gitRepos(g)) {
    for (const f of r.files || []) state.git.files.set(r.prefix + f.path, f);
    for (const d of r.dirs || []) state.git.dirs.add(r.prefix + d);
    if (r.files?.length) state.git.roots.add(r.root);
  }
  const list = $("#gitList");
  list.innerHTML = g?.git ? gitListHtml(g, "") : `<div class="hint" style="padding:0 14px">Not a git repository.</div>`;
  for (const r of gitRepos(g).filter((r) => !r.main)) {
    list.insertAdjacentHTML("beforeend", `<div class="group-head" title="${esc(tilde(r.path))}">${esc(base(r.path))} <span class="muted">· ${esc(r.branch)}</span></div>` + gitListHtml(r, r.prefix));
  }
  markTree();
}

function gitListHtml(r, prefix) {
  const files = r.files || [];
  if (!files.length) return '<div class="hint" style="padding:0 14px">Clean working tree.</div>';
  const more = r.total > files.length
    ? `<div class="hint git-more">${files.length.toLocaleString()} of ${r.total.toLocaleString()} changed files shown. A folder this big is usually one for .gitignore.</div>` : "";
  return (prefix ? "" : `<div class="row" id="openGitDiff">${icon("diff")}<span class="name">View working tree diff</span></div>`)
    + files.map((f) => gitRowHtml(prefix + f.path, f)).join("") + more;
}

// A row holds controls (a tick box, Discard), so the row itself isn't the button: the name is.
function gitRowHtml(path, f) {
  const k = GIT_KINDS[f.kind] || GIT_KINDS.modified;
  const tip = f.from ? `${k.word} from ${f.from}` : k.word;
  return `<div class="row git-row" data-git="${f.kind}" data-gitrow="${esc(path)}">`
    + `<button class="gname" data-gitfile="${esc(path)}" title="${esc(shownPath(path))}: ${esc(tip)}" aria-label="${esc(gitLabel(f.path, f.kind))}">${fileIcon(path)}<span class="name">${esc(f.path)}</span>${gitMark(f.kind)}</button></div>`;
}

$("#gitList").addEventListener("click", (e) => {
  if (e.target.closest("#openGitDiff")) return openGitDiff();
  const r = e.target.closest("[data-gitfile]"); if (!r) return;
  const path = r.dataset.gitfile;
  // What was deleted is shown as a diff: there's no file to open.
  if (state.git.files.get(path)?.kind === "deleted") openGitDiff(path); else openFile(path);
});

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
