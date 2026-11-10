"use strict";
// A session's folders (folders.py): its main folder plus folders you add, such as another repo. The title bar's folder
// button is their menu (add one, or open one in a new session: it never silently replaces the session's folder). Once
// there's more than one, the Explorer shows each as a top-level entry, the main one first. Files in an added folder go
// by their full path, as codepilot names them.

const addedFolders = () => state.session?.folders || [];
const closedRoots = new Set(); // folders folded in the Explorer (all open by default)

// "target", or "target +2" with added folders.
const folderButtonLabel = (repo) => repo ? base(repo) + (addedFolders().length ? ` +${addedFolders().length}` : "") : "Open folder…";

async function setFolders(body) {
  const sid = state.sid;
  try {
    const d = await api(`/api/sessions/${sid}`, { method: "PATCH", body });
    if (state.sid !== sid) { loadSessions(); return; } // you've opened another session meanwhile: leave it be
    // Reopened as the server now has it: changes rebased onto the new main folder, or outdated by a removed one.
    if (d.session) await openSession(sid);
  } catch (err) { toast(err.message, true); }
}
const browseNear = () => browseFolder(dirOf(state.workspace) || state.workspace || state.cfg.default_repo || "");
async function addFolder() { const path = await browseNear(); if (path) await setFolders({ folders: [...addedFolders(), path] }); }
async function openFolderInNewSession() { const path = await browseNear(); if (path) await newSession(path); }
const removeFolder = (path) => setFolders({ folders: addedFolders().filter((p) => p !== path) });
// Another main folder closes the open files (their paths are the main folder's): not while one has unsaved edits.
function makeMainFolder(path) {
  if (state.tabs.some((t) => t.dirty)) return toast("Save or close the files with unsaved edits first: making another folder main closes open files.", true);
  return setFolders({ make_main: path });
}
// The added folders open in the Explorer, for the disk check to follow (app.js checkDisk).
const openAddedFolders = () => addedFolders().filter((p) => !closedRoots.has(p) && !(state.session?.missing || []).includes(p));

function folderMenu(anchor = $("#workspaceBtn")) {
  const r = anchor.getBoundingClientRect();
  showMenu(r.left, r.bottom + 4, [
    ...[state.workspace, ...addedFolders()].map((p, i) => ({ label: `${base(p)}${i ? "" : " (main)"}`, icon: "folder", run: () => revealFolder(p) })),
    "-",
    { label: "Add folder…", icon: "folderPlus", run: addFolder },
    { label: "Open folder in a new session…", icon: "folderOpen", run: openFolderInNewSession },
  ]);
}

function revealFolder(path) {
  closedRoots.delete(path); setView("explorer");
  renderTree().then(() => $(`#tree .row.root[data-root="${CSS.escape(path)}"]`)?.scrollIntoView({ block: "nearest" }));
}

// The Explorer's folders: with one, its tree as always; with more, a top-level entry for each, main first. `walk` is
// renderTree's (a folder's entries at a depth); an added folder that's gone says so.
async function walkFolders(walk, rows) {
  const added = addedFolders();
  if (!added.length) return walk(".", 0);
  for (const [i, path] of [state.workspace, ...added].entries()) {
    const key = i ? path : ".", open = !closedRoots.has(path);
    const found = !(state.session?.missing || []).includes(path); // (the server checks: no failed request)
    rows.push(`<div class="row root${found ? "" : " missing"}" style="--depth:0" data-root="${esc(path)}" title="${esc(tilde(path))}"><span class="caret ${open && found ? "open" : ""}">${icon("chevron")}</span><span class="ficon dir">${icon("folder")}</span><span class="name">${esc(base(path))}</span>${i ? "" : '<span class="root-tag">main</span>'}</div>`);
    if (!found) rows.push(`<div class="root-missing"><span>This folder can't be found: ${esc(tilde(path))}</span><button class="btn sm" data-root-remove="${esc(path)}">Remove from session</button></div>`);
    else if (open) await walk(key, 1);
  }
}

$("#tree").addEventListener("click", (e) => {
  const rm = e.target.closest("[data-root-remove]");
  if (rm) { removeFolder(rm.dataset.rootRemove); return; }
  const root = e.target.closest(".row.root");
  if (!root) return;
  const p = root.dataset.root, main = p === state.workspace;
  state.picked = main ? null : p; state.pickedDir = !main; // New File/Folder go in this folder
  closedRoots.has(p) ? closedRoots.delete(p) : closedRoots.add(p); renderTree();
});
$("#tree").addEventListener("contextmenu", (e) => {
  const root = e.target.closest(".row.root"); if (!root) return;
  e.preventDefault(); e.stopPropagation(); // (not the Explorer's own menu for empty space)
  const path = root.dataset.root, main = path === state.workspace;
  showMenu(e.clientX, e.clientY, [
    ...(main ? [] : [{ label: "Make main folder", icon: "home", run: () => makeMainFolder(path) },
      { label: "Remove from session", icon: "x", run: () => removeFolder(path) }]),
    { label: "Open in Terminal", icon: "terminal", run: () => newTerminal(path) },
    { label: "Copy Path", icon: "copy", run: () => copyText(path) },
  ]);
});

// A path as the lists show it: an added folder's file as "<folder>/<path>" (api/src/app.py), not its long full path.
function shownPath(p) {
  const f = addedFolders().find((a) => p === a || p.startsWith(a + "/"));
  return f ? base(f) + p.slice(f.length) : p;
}

// The Changes view: each added folder that's a git checkout, under its own heading with its branch.
function addedGit(list) {
  for (const g of list || []) {
    if (!g.git) continue;
    const files = g.files || [];
    $("#gitList").insertAdjacentHTML("beforeend", `<div class="group-head" title="${esc(tilde(g.path))}">${esc(base(g.path))} <span class="muted">· ${esc(g.branch)}</span></div>`
      + (files.map((f) => { const path = `${g.path}/${f.path}`; return `<div class="row" data-gitfile="${esc(path)}">${fileIcon(path)}<span class="name">${esc(f.path)}</span><span class="meta mono">${esc(f.code)}</span></div>`; }).join("")
        || '<div class="hint" style="padding:0 14px">Clean working tree.</div>'));
  }
}
