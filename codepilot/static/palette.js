"use strict";
// ⌘P goes anywhere (spec go-anywhere): to a file (the ones you were in when nothing is typed), to `name:line`, or to
// `:line` in the file shown. The text's first character picks the mode; each mode lists rows, and one renderPalette
// draws any of them. Loaded straight after app.js and using its helpers; app.js calls openPalette and closePalette
// from its keys, the welcome page and the File menu, and noteRecent from renderEditor.

// rows: what's drawn (options, a heading on the first of a group, hints); items: the options, which Enter takes;
// shown: the text the rows answer. seq: an answer to text typed since is dropped (a find can come back late).
const pal = { rows: [], items: [], idx: 0, shown: null, seq: 0 };

// ---- modes: a row each; the first whose prefix the text starts with lists what it means
const PAL_MODES = [
  { prefix: ":", items: lineItems },
  { prefix: "", items: fileItems },
];

// The last list is cleared, not shown again: Enter on it would take what was there last time.
function openPalette(prefix = "") {
  pal.rows = pal.items = []; pal.shown = null; renderPalette();
  $("#palette").hidden = false; $("#paletteInput").value = prefix; $("#paletteInput").focus(); palList(prefix);
}
function closePalette() { $("#palette").hidden = true; }

async function palList(text) {
  const seq = ++pal.seq;
  const mode = PAL_MODES.find((m) => text.startsWith(m.prefix));
  const rows = await Promise.resolve(mode.items(text.slice(mode.prefix.length))).catch(() => []);
  if (seq !== pal.seq) return;
  pal.rows = rows; pal.items = rows.filter((r) => r.run); pal.idx = 0; pal.shown = text;
  renderPalette();
}
const palSearch = debounce(palList, 80);

// A combobox, as the session switcher and the @ list are (sessions.js, a11y.js): focus stays in the box and the
// current option is its active descendant. A group's heading names it and isn't an option; a hint is neither.
function renderPalette() {
  let html = "", group = false, heads = 0;
  const end = () => { if (group) html += "</div>"; group = false; };
  for (const r of pal.rows) {
    if (r.hint) { end(); html += `<div class="hint pal-hint">${esc(r.hint)}</div>`; continue; }
    if (r.heading) {
      end(); group = true; const id = `pal-h-${heads++}`;
      html += `<div role="group" aria-labelledby="${id}"><div class="pal-head" id="${id}">${esc(r.heading)}</div>`;
    }
    const i = pal.items.indexOf(r), on = i === pal.idx;
    // (tabindex -1: reachable by the box's keys, never a Tab stop; a click keeps focus in the box, below)
    html += `<div class="opt${on ? " on" : ""}" id="pal-opt-${i}" role="option" aria-selected="${on}" tabindex="-1" data-i="${i}">`
      + `${r.icon || ""}<span class="n">${esc(r.title)}</span>${r.dir != null ? `<span class="dir">${esc(r.dir)}</span>` : ""}`
      + `${r.detail ? `<span class="desc">${esc(r.detail)}</span>` : ""}${r.kbd ? `<kbd>${esc(r.kbd)}</kbd>` : ""}</div>`;
  }
  end();
  $("#paletteList").innerHTML = html;
  const on = $("#paletteList .opt.on");
  if (on) $("#paletteInput").setAttribute("aria-activedescendant", on.id); else $("#paletteInput").removeAttribute("aria-activedescendant");
  on?.scrollIntoView({ block: "nearest" });
}

// Closed first, so what the option does with focus (a prompt, the editor) is where focus stays (a11y.js gives it back
// to what had it only when nothing has taken it since).
function palRun(item) {
  if (!item) return;
  closePalette();
  try { Promise.resolve(item.run()).catch((err) => toast(err.message, true)); } catch (err) { toast(err.message, true); }
}
// Enter takes the option for what's in the box: typed faster than the list came back, it waits for that answer.
async function palEnter() {
  const text = $("#paletteInput").value;
  if (pal.shown !== text) await palList(text);
  if (!$("#palette").hidden) palRun(pal.items[pal.idx]);
}

$("#paletteInput").addEventListener("input", (e) => palSearch(e.target.value));
$("#paletteInput").addEventListener("keydown", (e) => {
  if (e.isComposing) return; // (Enter that ends an IME composition isn't a choice)
  const step = { ArrowDown: 1, ArrowUp: -1 }[e.key];
  if (step) { e.preventDefault(); pal.idx = Math.max(0, Math.min(pal.idx + step, pal.items.length - 1)); renderPalette(); }
  // Not typed: the key ends here, so a command that puts focus in a text box doesn't get the Enter as well.
  else if (e.key === "Enter") { e.preventDefault(); palEnter(); }
  else if (e.key === "Escape") closePalette();
});
$("#paletteList").addEventListener("mousedown", (e) => e.preventDefault()); // (focus stays in the box)
$("#paletteList").addEventListener("click", (e) => { const o = e.target.closest("[data-i]"); if (o) palRun(pal.items[+o.dataset.i]); });
$("#palette").addEventListener("mousedown", (e) => { if (e.target.id === "palette") closePalette(); });
$("#paletteBtn").onclick = () => openPalette();

// ---- files
// The text as a name and an optional line: "core.py:12".
function palLine(text) {
  const m = text.match(/^(.*?):(\d+)\s*$/);
  return m ? { name: m[1], line: +m[2] } : { name: text, line: null };
}
async function palFind(q) {
  return (await api(`/api/sessions/${state.sid}/find?q=${encodeURIComponent(q)}`).catch(() => ({ files: [] }))).files;
}
// Nothing typed: the files you were in, else (a folder with none yet) the folder's files as before.
async function fileItems(text) {
  if (!state.sid || !state.workspace) return [{ hint: "Open a folder to go to its files." }];
  const { name, line } = palLine(text);
  const recent = name.trim() ? [] : await recentFiles();
  const files = recent.length ? recent : await palFind(name);
  if (!files.length) return [{ hint: "No matching files." }];
  return files.map((f, i) => ({ heading: i ? null : recent.length ? "Recently opened" : "Files", icon: fileIcon(f),
    title: base(f), dir: dirOf(shownPath(f)), run: () => palGoTo(f, line) }));
}

// `:n`: a line in the file shown, a file of the folder's (not a steering doc shown as one).
function lineItems(text) {
  const tab = activeFileTab();
  if (!tab || tab.id !== "file:" + tab.path) return [{ hint: "Open a file first: :line goes to a line in the file shown." }];
  const n = /^\s*\d+\s*$/.test(text) ? +text : 0;
  if (!n) return [{ hint: `Type a line number in ${base(tab.path)}.` }];
  return [{ icon: icon("list"), title: `Go to line ${n} in ${base(tab.path)}`, run: () => palGoTo(tab.path, n) }];
}

// Open path at line: the read view flashes it (openFile); in Edit mode the caret goes there, in the same editor when
// it's the one shown (its undo history and your draft stay as they are), else once openFile has shown it.
async function palGoTo(path, line) {
  const here = activeFileTab();
  if (!(line && here?.editing && here.path === path)) await openFile(path, line || undefined);
  const tab = activeFileTab();
  if (!line || tab?.path !== path || !tab.editing || tab.editPreview) return;
  await loadEditor().catch(() => {}); // editor.js: mounted once its script is in (renderEditTab says if it failed)
  const ed = codeEditor();
  if (ed?.tab === tab) { ed.goToLine(line); ed.focus(); }
}

// ---- recent files
// Each folder's 30 most recently shown files, newest first, in this browser (cp-recent:<folder>). The folder is the
// one whose tabs are on screen (tabstate.js), not state.workspace: while a session opens, that already names the next
// folder. Folders are forgotten by the rule tabstate.js keeps its own records by.
const RECENT_KEY = "cp-recent:";
const RECENT_MAX = 30;
const recent = { noted: null, pruned: false };

function readRecent(folder) {
  try {
    const rec = JSON.parse(localStorage.getItem(RECENT_KEY + folder) || "null");
    return rec?.v === 1 && Array.isArray(rec.paths) ? rec.paths : [];
  } catch { return []; }
}

// renderEditor ends here, and it runs often: a file shown again writes nothing.
function noteRecent(tab) {
  const folder = tabStore.folder; // (null while a folder's tabs are being reopened)
  if (!folder || !tab || !["file", "image", "binary"].includes(tab.kind) || tab.id !== "file:" + tab.path) return;
  const key = folder + "\n" + tab.path;
  if (recent.noted === key) return;
  recent.noted = key;
  const paths = [tab.path, ...readRecent(folder).filter((p) => p !== tab.path)].slice(0, RECENT_MAX);
  try { localStorage.setItem(RECENT_KEY + folder, JSON.stringify({ v: 1, at: Math.floor(Date.now() / 1000), paths })); }
  catch { /* full or blocked: not kept */ }
  if (!recent.pruned) { recent.pruned = true; pruneTabRecords(undefined, RECENT_KEY); }
}

// What ⌘P starts from: the folder's recent files but the one shown, leaving out any that are gone (or no longer in
// the session's folders: /stat says null for those too), in one request.
async function recentFiles() {
  const folder = tabStore.folder;
  const paths = folder ? readRecent(folder).filter((p) => "file:" + p !== state.active) : [];
  if (!paths.length) return [];
  const d = await api(`/api/sessions/${state.sid}/stat`, { method: "POST", body: { dirs: [], files: paths } }).catch(() => null);
  return paths.filter((p) => d?.files?.[p] !== null);
}
