"use strict";
// Tabs come back: each main folder's open tabs, their order and place, the Explorer's open folders and any unsaved edit
// are kept in this browser (localStorage, cp-tabs:<folder>) and reopened after a reload, a restart, or a switch back to
// a session on that folder. Per folder, not per session: sessions on one folder share their tabs, as they always have.
// A file's text is never stored, only a draft that differs from it. The page asks before it's left only when a draft
// couldn't be stored (too large, or storage full or blocked); asking on every reload would teach you to click through.

const TABS_KEY = "cp-tabs:";
const TABS_MAX_DRAFT = 1_000_000; // characters: localStorage holds a few million in all, for every folder
const TABS_MAX_AGE = 30 * 86400; // s: a folder not opened for this long is forgotten at startup
const TABS_MAX_FOLDERS = 20;

// folder: whose tabs state.tabs holds, and so where they're written (null while a folder's tabs are being reopened:
// writing a half-restored list then would lose the rest). unsafe: ids of tabs whose draft the last write couldn't keep.
const tabStore = { folder: null, restoring: 0, seq: 0, unsafe: new Set() };

function tabsRestoring() { return !!tabStore.restoring; } // openTab: reopened tabs don't take focus one by one

// Each kind that comes back: what's stored for it, and how it's opened again. A kind not here (a global steering doc,
// another tool's read-only one) isn't restored. A new kind comes back by adding a row.
const TAB_KINDS = {
  file: { record: (t) => (t.id === "file:" + t.path ? fileRecord(t) : null), reopen: reopenFile },
  image: { record: (t) => ({ path: t.path }), reopen: reopenFile }, // (openFile works out the kind again)
  binary: { record: (t) => ({ path: t.path }), reopen: reopenFile },
  trace: { record: (t) => ({ path: t.path }), reopen: (r, found) => found.traces.has(r.path) && openTrace(r.path) },
  spec: { record: (t) => ({ name: t.name, view: t.view || null }), reopen: reopenSpec },
  // The Review tab is the session's: it comes back only when the session has changes to show.
  review: { record: (t) => ({ sel: t.sel || null }), reopen: (r) => state.proposals.size && openReview(r.sel) },
  gitdiff: { record: () => ({}), reopen: () => openGitDiff() },
};

function tabRecord(tab, unsafe) {
  const kind = TAB_KINDS[tab.kind];
  const fields = kind && !tab.global && !tab.readonly ? kind.record(tab) : null;
  if (!fields) return null;
  const rec = { id: tab.id, kind: tab.kind, ...fields };
  if (rec.draft != null && rec.draft.length > TABS_MAX_DRAFT) { delete rec.draft; delete rec.baseMtime; unsafe.add(tab.id); }
  return rec;
}

function fileRecord(t) {
  const place = t.ed?.place(); // editor.js: the editor this tab is in, if it's shown
  const rec = { path: t.path, view: t.view || null, topLine: place?.topLine ?? (t.topLine || 1), scroll: t.scroll || 0,
    sel: t.sel || null, caret: place?.caret ?? t.caret ?? null, editing: !!t.editing, editPreview: !!t.editPreview };
  // Only an edit that differs from the file, and never for one that isn't UTF-8 (it can't be edited here).
  if (t.dirty && t.draft != null && !t.encoding) Object.assign(rec, { draft: t.draft, baseMtime: t.mtime ?? null });
  return rec;
}

function writeTabRecord(folder, rec) {
  try { localStorage.setItem(TABS_KEY + folder, JSON.stringify(rec)); return true; } catch { return false; }
}

function readTabRecord(folder) {
  try {
    const rec = JSON.parse(localStorage.getItem(TABS_KEY + folder) || "null");
    return rec && rec.v === 1 && Array.isArray(rec.tabs) ? rec : null;
  } catch { return null; }
}

// The current folder's record, written whole.
function saveTabs() {
  const folder = tabStore.folder;
  if (!folder || tabStore.restoring) return;
  const unsafe = new Set();
  const rec = { v: 1, at: Math.floor(Date.now() / 1000), active: state.active, expanded: [...state.expanded],
    tabs: state.tabs.map((t) => tabRecord(t, unsafe)).filter(Boolean) };
  if (!writeTabRecord(folder, rec)) {
    // Full or blocked: every draft is at risk. Keep the tabs and their place if that much still fits.
    for (const t of state.tabs) if (t.dirty) unsafe.add(t.id);
    for (const t of rec.tabs) { delete t.draft; delete t.baseMtime; }
    writeTabRecord(folder, rec);
  }
  tabStore.unsafe = unsafe;
}
const saveTabsSoon = debounce(saveTabs, 300);

// Replace the tabs with repo's. The open folders are set before anything waits, so the tree setWorkspace draws next
// already shows them; then each tab is reopened in order, quietly, and the editor is drawn once at the end.
async function restoreTabs(repo) {
  const seq = ++tabStore.seq;
  tabStore.restoring = seq; tabStore.folder = null; tabStore.unsafe = new Set();
  state.tabs = []; state.active = null;
  const rec = repo ? readTabRecord(repo) : null;
  state.expanded.clear(); for (const p of rec?.expanded || []) state.expanded.add(p);
  // A newer restore takes over. While a session is opening the folder is briefly unset: wait for it to settle (to
  // this folder, carry on: a session on the same folder keeps its tabs; to another, that one's restore takes over).
  const ours = async () => {
    for (let i = 0; i < 200 && tabStore.restoring === seq && state.workspace === null; i++) await new Promise((r) => setTimeout(r, 25));
    return tabStore.restoring === seq && state.workspace === repo;
  };
  try {
    if (!rec?.tabs.length) return;
    const has = (kind) => rec.tabs.some((r) => r.kind === kind);
    const paths = rec.tabs.filter((r) => ["file", "image", "binary"].includes(r.kind)).map((r) => r.path);
    const [stat, traces] = await Promise.all([ // what's still there, so nothing gone is asked for (or errors)
      paths.length ? api(`/api/sessions/${state.sid}/stat`, { method: "POST", body: { dirs: [], files: paths } }).catch(() => null) : null,
      has("trace") ? api(`/api/sessions/${state.sid}/traces`).catch(() => null) : null,
      has("spec") ? loadSpecs(true) : null,
    ]);
    const found = { mtimes: stat?.files || {}, traces: new Set((traces?.files || []).map((f) => f.path)) };
    for (const r of rec.tabs) {
      if (!(await ours())) return;
      try { await TAB_KINDS[r.kind]?.reopen(r, found); } catch { /* left out */ }
    }
    if (!(await ours())) return;
    const order = new Map(rec.tabs.map((r, i) => [r.id, i])); // (a tab you opened meanwhile goes last)
    state.tabs.sort((a, b) => (order.get(a.id) ?? Infinity) - (order.get(b.id) ?? Infinity));
    state.active = state.tabs.some((t) => t.id === rec.active) ? rec.active : state.tabs[0]?.id || null;
  } finally {
    if (tabStore.restoring === seq) {
      tabStore.restoring = 0;
      if (state.workspace === repo && repo) tabStore.folder = repo;
      renderEditor();
    }
  }
}

// A file tab, where it was. A place is set before the one render, not passed to openFile as a line: a line would
// flash and clear the selection.
async function reopenFile(r, found) {
  const mtime = found.mtimes[r.path]; // null: gone; undefined: not known, so try
  const draft = typeof r.draft === "string" ? r.draft : null;
  if (mtime === null) {
    if (draft == null) return; // gone, with nothing of yours in it: left out
    openTab({ id: r.id, kind: "file", path: r.path, title: base(r.path), tip: r.path, content: "", mtime: null, missing: true, sel: null });
    toast(`${r.path} was deleted on disk. Your unsaved edit is kept: Save writes the file again.`);
  } else await openFile(r.path);
  const tab = state.tabs.find((t) => t.id === r.id);
  if (tab?.kind !== "file") return;
  Object.assign(tab, { view: r.view || undefined, topLine: r.topLine || 1, scroll: r.scroll || 0, sel: r.sel || null,
    caret: r.caret ?? null, flash: null, editPreview: !!r.editPreview });
  if (tab.encoding) return;
  if (draft != null) {
    // The draft's own base: when the file changed since, checkDisk says so once, and Save asks before overwriting.
    Object.assign(tab, { editing: true, draft, mtime: tab.missing ? null : r.baseMtime ?? tab.mtime });
    tab.dirty = tab.draft !== tab.content;
  } else if (r.editing) Object.assign(tab, { editing: true, draft: tab.content });
}

function reopenSpec(r) {
  if (!findSpec(r.name)) return; // (the specs were loaded first)
  openSpec(r.name);
  const tab = state.tabs.find((t) => t.id === r.id);
  if (tab) tab.view = r.view || null;
}

// At startup: forget folders not opened for 30 days, and all but the 20 most recent.
function pruneTabRecords(now = Date.now() / 1000) {
  try {
    const at = (k) => { try { return +JSON.parse(localStorage.getItem(k)).at || 0; } catch { return 0; } };
    const recs = Object.keys(localStorage).filter((k) => k.startsWith(TABS_KEY)).map((k) => [k, at(k)]);
    recs.sort((a, b) => b[1] - a[1]);
    recs.forEach(([k, t], i) => { if (i >= TABS_MAX_FOLDERS || now - t > TABS_MAX_AGE) localStorage.removeItem(k); });
  } catch { /* storage blocked: nothing stored either */ }
}

// Leaving: write now (the debounce may not have run), and ask only for an edit that couldn't be kept.
addEventListener("beforeunload", (e) => {
  saveTabs();
  if (state.tabs.some((t) => t.dirty && tabStore.unsafe.has(t.id))) { e.preventDefault(); e.returnValue = ""; }
});
addEventListener("pagehide", saveTabs);
document.addEventListener("visibilitychange", () => { if (document.hidden) saveTabs(); });
