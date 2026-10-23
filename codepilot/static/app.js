"use strict";
/* codepilot IDE front end. No build step: plain DOM + fetch. */

// ---------------------------------------------------------------- utilities
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const H = { "Content-Type": "application/json", "X-Codepilot": "1" };
const isMac = /Mac|iPhone|iPad/.test(navigator.platform);
function store(key, val) { try { if (val === undefined) return localStorage.getItem(key); localStorage.setItem(key, val); } catch { return null; } return null; }
async function api(path, opts = {}) {
  const res = await fetch(path, { headers: H, ...opts, body: opts.body ? JSON.stringify(opts.body) : undefined });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}
const fmtTok = (n) => (n >= 1e6 ? (n / 1e6).toFixed(1) + "M" : n >= 1e3 ? (n / 1e3).toFixed(1) + "k" : String(n || 0));
const fmtBytes = (n) => (n >= 1048576 ? (n / 1048576).toFixed(1) + " MB" : n >= 1024 ? Math.round(n / 1024) + " KB" : n + " B");
const fmtMs = (ms) => (ms == null ? "" : ms >= 1000 ? (ms / 1000).toFixed(1) + "s" : ms >= 1 ? ms.toFixed(0) + "ms" : ms > 0 ? ms.toFixed(2) + "ms" : "0ms");
const ago = (t) => { const s = Date.now() / 1000 - t; return s < 60 ? "just now" : s < 3600 ? Math.floor(s / 60) + "m ago" : s < 86400 ? Math.floor(s / 3600) + "h ago" : Math.floor(s / 86400) + "d ago"; };
const base = (p) => p.split("/").pop();
const dirOf = (p) => (p.includes("/") ? p.slice(0, p.lastIndexOf("/")) : "");
const tilde = (p) => { const h = state?.cfg?.home; return h && p && (p === h || p.startsWith(h + "/")) ? "~" + p.slice(h.length) : p; };
const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

// ---------------------------------------------------------------- icons (Lucide-style, ISC)
const ICONS = {
  logo: '<path d="M12 2 3 7v10l9 5 9-5V7z"/><path d="m9.5 10-2 2 2 2"/><path d="m14.5 10 2 2-2 2"/>',
  files: '<path d="M20 7h-3a2 2 0 0 1-2-2V2"/><path d="M9 18a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h7l4 4v10a2 2 0 0 1-2 2Z"/><path d="M3 7.6v12.8A1.6 1.6 0 0 0 4.6 22h9.8"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  history: '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l4 2"/>',
  pulse: '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
  branch: '<path d="M6 3v12"/><circle cx="18" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M18 9a9 9 0 0 1-9 9"/>',
  brain: '<path d="m12 2 9 5-9 5-9-5z"/><path d="m3 12 9 5 9-5"/><path d="m3 17 9 5 9-5"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  folderOpen: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h6a2 2 0 0 1 2 2v1"/><path d="M3 7v10a2 2 0 0 0 2 2h12.5a2 2 0 0 0 1.9-1.4L22 11H7.5a2 2 0 0 0-1.9 1.4L3 19"/>',
  file: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>',
  refresh: '<path d="M21 12a9 9 0 0 1-15.5 6.2L3 16"/><path d="M3 21v-5h5"/><path d="M3 12a9 9 0 0 1 15.5-6.2L21 8"/><path d="M21 3v5h-5"/>',
  collapse: '<path d="m7 20 5-5 5 5"/><path d="m7 4 5 5 5-5"/>',
  chevron: '<path d="m9 6 6 6-6 6"/>',
  x: '<path d="M18 6 6 18M6 6l12 12"/>',
  sidebar: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16"/>',
  panel: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 15h18"/>',
  chat: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
  theme: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  trash: '<path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/>',
  play: '<path d="m6 4 14 8-14 8z"/>',
  at: '<circle cx="12" cy="12" r="4"/><path d="M16 8v5a3 3 0 0 0 6 0v-1a10 10 0 1 0-4 8"/>',
  send: '<path d="M12 19V5"/><path d="m5 12 7-7 7 7"/>',
  stop: '<rect x="7" y="7" width="10" height="10" rx="1.5"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  alert: '<circle cx="12" cy="12" r="9"/><path d="M12 8v4M12 16h.01"/>',
  tool: '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.8-3.8a6 6 0 0 1-7.9 7.9l-6.9 6.9a2.1 2.1 0 0 1-3-3l6.9-6.9a6 6 0 0 1 7.9-7.9z"/>',
  diff: '<path d="M12 3v14M5 10h14M5 21h14"/>',
  copy: '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/>',
  sparkle: '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/><path d="M19 17l.7 1.8 1.8.7-1.8.7L19 22l-.7-1.8-1.8-.7 1.8-.7z"/>',
  terminal: '<path d="m4 17 6-5-6-5"/><path d="M12 19h8"/>',
  server: '<rect x="3" y="4" width="18" height="7" rx="2"/><rect x="3" y="13" width="18" height="7" rx="2"/><path d="M7 7.5h.01M7 16.5h.01"/>',
  beaker: '<path d="M9 3h6"/><path d="M10 3v6L4.2 19.5A1 1 0 0 0 5.1 21h13.8a1 1 0 0 0 .9-1.5L14 9V3"/>',
  eye: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  edit: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
  list: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
  up: '<path d="M12 19V5"/><path d="m5 12 7-7 7 7"/>',
  home: '<path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>',
  cloud: '<path d="M17.5 19a4.5 4.5 0 1 0-1.4-8.8A6 6 0 0 0 4.3 12.6 3.5 3.5 0 0 0 6.5 19z"/>',
  link: '<path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7"/><path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7"/>',
};
const icon = (name, cls = "") => `<svg class="i ${cls}" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name] || ICONS.file}</svg>`;
function hydrateIcons(root = document) {
  for (const el of $$("[data-icon]", root)) {
    if (el.dataset.iconDone) continue;
    el.insertAdjacentHTML("afterbegin", icon(el.dataset.icon));
    el.dataset.iconDone = "1";
  }
}
const TOOL_ICONS = { read_file: "eye", list_files: "files", search_code: "search", git: "branch", run_tests: "beaker", run_command: "terminal",
  propose_edit: "edit", explore: "sparkle", update_plan: "list", open_workspace: "folderOpen", list_traces: "pulse", trace_outline: "pulse",
  search_traces: "pulse", read_trace: "pulse", load_skill: "brain", remember: "brain", cloudwatch_logs: "server" };
const EXT_COLORS = { py: "var(--syn-fn)", js: "var(--syn-type)", ts: "var(--syn-fn)", tsx: "var(--syn-fn)", jsx: "var(--syn-type)", json: "var(--syn-num)",
  md: "var(--muted)", yml: "var(--syn-var)", yaml: "var(--syn-var)", toml: "var(--syn-var)", go: "var(--syn-attr)", rs: "var(--syn-num)", sh: "var(--syn-str)",
  html: "var(--syn-var)", css: "var(--syn-kw)", sql: "var(--syn-attr)", jsonl: "var(--syn-num)", log: "var(--muted)" };
const LANGS = { py: "python", js: "javascript", mjs: "javascript", jsx: "javascript", ts: "typescript", tsx: "typescript", json: "json", jsonl: "json",
  md: "markdown", yml: "yaml", yaml: "yaml", toml: "ini", ini: "ini", cfg: "ini", sh: "bash", bash: "bash", zsh: "bash", go: "go", rs: "rust",
  java: "java", kt: "kotlin", rb: "ruby", css: "css", scss: "scss", html: "xml", xml: "xml", sql: "sql", c: "c", h: "c", cpp: "cpp", cs: "csharp",
  php: "php", swift: "swift", makefile: "makefile", dockerfile: "dockerfile", txt: "plaintext", log: "plaintext" };
const extOf = (p) => { const b = base(p).toLowerCase(); if (b === "makefile") return "makefile"; if (b === "dockerfile") return "dockerfile"; return b.includes(".") ? b.split(".").pop() : ""; };
const fileIcon = (p) => `<span class="ficon file" style="color:${EXT_COLORS[extOf(p)] || "var(--faint)"}">${icon("file")}</span>`;

// ---------------------------------------------------------------- state
const state = {
  cfg: null, sid: null, session: null, workspace: "", streams: new Set(), proposals: new Map(), toolEls: new Map(),
  tabs: [], active: null, tree: new Map(), expanded: new Set(), activity: 0, context: null, testCmd: "", traceFiles: [],
};

// ---------------------------------------------------------------- layout
const ide = $("#ide");
function setView(view) {
  $$("#activitybar button").forEach((b) => b.classList.toggle("on", b.dataset.view === view));
  $$(".sidebar .view").forEach((v) => v.classList.toggle("on", v.dataset.view === view));
  ide.classList.remove("no-sidebar");
  store("cp-view", view);
  if (view === "traces") loadTraces();
  if (view === "changes") { renderProposalList(); loadGit(); }
  if (view === "memory") renderMemory();
  if (view === "search") $("#grepInput").focus();
}
$("#activitybar").addEventListener("click", (e) => {
  const b = e.target.closest("button"); if (!b) return;
  if (b.classList.contains("on") && !ide.classList.contains("no-sidebar")) { ide.classList.add("no-sidebar"); return; }
  setView(b.dataset.view);
});
const toggle = (cls) => { ide.classList.toggle(cls); store("cp-" + cls, ide.classList.contains(cls) ? "1" : "0"); };
$("#toggleSidebar").onclick = () => toggle("no-sidebar");
$("#togglePanel").onclick = () => toggle("no-panel");
$("#toggleChat").onclick = () => toggle("no-chat");
$("#closePanel").onclick = () => toggle("no-panel");
$("#themeBtn").onclick = () => {
  const dark = matchMedia("(prefers-color-scheme: dark)").matches;
  const cur = document.documentElement.dataset.theme || (dark ? "dark" : "light");
  const next = cur === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next; store("cp-theme", next);
  if (termState.term) termState.term.options.theme = termTheme();
};
function makeResizer(el, varName, axis, min, max, invert) {
  el.addEventListener("mousedown", (e) => {
    e.preventDefault(); el.classList.add("drag");
    const start = axis === "x" ? e.clientX : e.clientY;
    const startVal = parseFloat(getComputedStyle(ide).getPropertyValue(varName));
    const move = (ev) => {
      const delta = (axis === "x" ? ev.clientX : ev.clientY) - start;
      const v = Math.max(min, Math.min(max, startVal + (invert ? -delta : delta)));
      ide.style.setProperty(varName, v + "px");
    };
    const up = () => { el.classList.remove("drag"); document.removeEventListener("mousemove", move); document.removeEventListener("mouseup", up); store("cp" + varName, ide.style.getPropertyValue(varName)); };
    document.addEventListener("mousemove", move); document.addEventListener("mouseup", up);
  });
}
makeResizer($("#sidebarResizer"), "--sidebar-w", "x", 180, 560, false);
makeResizer($("#chatResizer"), "--chat-w", "x", 300, 820, true);
makeResizer($("#panelResizer"), "--panel-h", "y", 90, 640, true);

// bottom panel tabs
$(".panel-tabs").addEventListener("click", (e) => {
  const b = e.target.closest("[data-ptab]"); if (!b) return;
  showPanelTab(b.dataset.ptab);
});
function showPanelTab(name) {
  $$(".panel-tabs [data-ptab]").forEach((b) => b.classList.toggle("on", b.dataset.ptab === name));
  $$(".panel-body").forEach((p) => (p.hidden = p.dataset.ptab !== name));
  ide.classList.remove("no-panel");
  if (name === "terminal") requestAnimationFrame(openTerminal);
}
$("#clearActivity").onclick = () => { $("#activity").innerHTML = ""; state.activity = 0; $("#actCount").textContent = "0"; };

// ---------------------------------------------------------------- init
async function init() {
  const theme = store("cp-theme"); if (theme) document.documentElement.dataset.theme = theme;
  for (const v of ["--sidebar-w", "--chat-w", "--panel-h"]) { const s = store("cp" + v); if (s) ide.style.setProperty(v, s); }
  for (const c of ["no-sidebar", "no-panel", "no-chat"]) if (store("cp-" + c) === "1") ide.classList.add(c);
  hydrateIcons();
  state.cfg = await api("/api/config");
  const c = state.cfg;
  $("#sbProvider").innerHTML = `${icon("server")}${c.provider === "bedrock" ? `bedrock · ${esc(c.region)}${c.profile ? " · " + esc(c.profile) : ""}` : `${esc(c.provider)} · ${esc(shortModel(c.models.main) || "no model set")}`}`;
  $("#sbProvider").classList.add(c.provider === "ollama" ? "warn" : "ok");
  $("#tier").innerHTML = c.tiers.map((t) => `<option value="${t}">${t} · ${esc(shortModel(c.models[t]))}</option>`).join("");
  $("#tier").value = c.default_tier;
  if (c.eval_cmd) $("#cmdInput").value = c.eval_cmd;
  renderQuick();
  api("/api/github").then((g) => {
    $("#sbGithub").innerHTML = g.available ? `${icon("branch")}github: ${esc(g.user)}${g.host !== "github.com" ? " @ " + esc(g.host) : ""}` : `<span title="${esc(g.reason || "")}">${icon("alert")}github off</span>`;
    $("#sbGithub").className = "sb-item " + (g.available ? "" : "warn");
  }).catch(() => {});
  setView(store("cp-view") || "explorer");
  const list = await loadSessions();
  const last = store("cp-session");
  if (last && list.some((s) => s.id === last)) await openSession(last);
  else if (list.length) await openSession(list[0].id);
  else { renderChatEmpty(); renderEditor(); renderTree(); }
  setInterval(pollSessions, 4000);
}
const shortModel = (m) => String(m).replace(/^(us|eu|apac|global)\.anthropic\./, "").replace(/-\d{8}-v\d+:\d+$/, "");

// ---------------------------------------------------------------- sessions
async function loadSessions() {
  const list = await api("/api/sessions").catch(() => []);
  state.sessionList = list;
  $("#sessionList").innerHTML = list.map((s) => `<div class="session ${s.id === state.sid ? "on" : ""}" data-id="${s.id}">
      <div class="t">${esc(s.title || "New session")}</div>
      <div class="r">${s.busy || state.streams.has(s.id) ? '<span class="spinner"></span>' : ""}<span>${esc(s.repo ? base(s.repo) : "no folder")}</span><span>·</span><span>${ago(s.updated)}</span></div>
      <button class="icon-btn sm del" data-del="${s.id}" title="Delete session">${icon("trash")}</button></div>`).join("")
    || `<div class="empty-state">No sessions yet.<br><button class="btn primary" onclick="newSession()">${icon("plus")}New session</button></div>`;
  return list;
}
async function pollSessions() {
  if (!(state.sessionList || []).some((s) => s.busy) && !state.streams.size) return;
  await loadSessions();
}
$("#sessionList").addEventListener("click", async (e) => {
  const del = e.target.closest("[data-del]");
  if (del) {
    e.stopPropagation();
    if (!confirm("Delete this session and its history?")) return;
    await api(`/api/sessions/${del.dataset.del}`, { method: "DELETE" });
    if (del.dataset.del === state.sid) { state.sid = null; store("cp-session", ""); renderChatEmpty(); }
    loadSessions(); return;
  }
  const row = e.target.closest(".session"); if (row) openSession(row.dataset.id);
});
async function newSession(repo) {
  const s = await api("/api/sessions", { method: "POST", body: { repo: repo ?? state.workspace ?? "", tier: $("#tier").value, auto_approve: $("#autoApprove").checked } });
  await openSession(s.id); $("#input").focus();
  return s;
}
window.newSession = newSession;
$("#newSessionBtn").onclick = () => newSession();
$("#newChatBtn").onclick = () => newSession();

async function openSession(sid) {
  const prevWorkspace = state.workspace;
  state.sid = sid; state.workspace = null; store("cp-session", sid);
  const data = await api(`/api/sessions/${sid}`);
  state.session = data.session;
  $("#chatTitle").textContent = data.session.title || "New session";
  $("#tier").value = data.session.tier; $("#autoApprove").checked = data.session.auto_approve;
  state.mode = data.session.mode || "build";
  $("#transcript").innerHTML = ""; state.toolEls.clear(); endText();
  state.proposals = new Map(data.proposals.map((p) => [p.id, p]));
  state.workspace = data.session.repo || "";
  if (!data.events.length) renderChatEmpty();
  for (const ev of data.events) render(ev, true);
  for (const p of data.proposals) if (p.status === "pending") renderProposalCard(p);
  if (data.pending) render({ type: "approval_needed", tools: data.pending }, true);
  renderPlan(null); for (const ev of data.events) if (ev.type === "plan") renderPlan(ev.items);
  updateBusy();
  setContext(data.context); renderUsage(data.usage); state.summary = data.summary;
  setWorkspace(data.session.repo, prevWorkspace !== (data.session.repo || ""));
  renderProposalList(); loadSessions(); scrollEnd(true);
}

// ---------------------------------------------------------------- workspace / explorer
function setWorkspace(repo, changed = true) {
  state.workspace = repo || "";
  if (state.session) state.session.repo = repo;
  $("#workspaceName").textContent = repo ? base(repo) : "Open folder…";
  $("#workspaceBtn").title = tilde(repo) || "Open folder";
  $("#explorerTitle").textContent = repo ? base(repo) : "Explorer";
  if (changed) {
    state.tree.clear(); state.expanded.clear();
    state.tabs = state.tabs.filter((t) => !["file", "trace", "gitdiff"].includes(t.kind));
    if (!state.tabs.some((t) => t.id === state.active)) state.active = state.tabs[0]?.id || null;
  }
  renderTree(); renderEditor(); loadGit(); loadWorkspaceInfo();
  if ($(".chat-empty")) renderChatEmpty();
  onWorkspaceChangedForTerminal();
  if ($(".view.on")?.dataset.view === "traces") loadTraces();
}
async function openFolder() {
  const path = await browseFolder(state.workspace ? dirOf(state.workspace) || state.workspace : state.cfg.default_repo || "");
  if (!path) return;
  await useFolder(path);
}
async function useFolder(path) {
  try {
    if (!state.sid) { await newSession(path); return; }
    const d = await api(`/api/sessions/${state.sid}`, { method: "PATCH", body: { repo: path } });
    setWorkspace(d.session.repo, true); loadSessions();
  } catch (err) { toast(err.message, true); }
}
$("#workspaceBtn").onclick = openFolder;
$("#openFolderBtn").onclick = openFolder;
$("#refreshTreeBtn").onclick = () => { state.tree.clear(); renderTree(); };
$("#collapseTreeBtn").onclick = () => { state.expanded.clear(); renderTree(); };

async function fetchDir(path) {
  if (state.tree.has(path)) return state.tree.get(path);
  const d = await api(`/api/sessions/${state.sid}/files?path=${encodeURIComponent(path)}`);
  state.tree.set(path, d.entries || []);
  return d.entries || [];
}
async function renderTree() {
  const el = $("#tree");
  if (!state.sid || !state.workspace) {
    el.innerHTML = `<div class="empty-state">No folder open.<br>Open one here, or tell codepilot in chat (e.g. “review ~/code/shop”).<br><button class="btn primary" id="emptyOpen">${icon("folderOpen")}Open folder</button></div>`;
    $("#emptyOpen").onclick = openFolder; return;
  }
  const rows = [];
  const walk = async (path, depth) => {
    let entries;
    try { entries = await fetchDir(path); } catch (err) { rows.push(`<div class="empty-state">${esc(err.message)}</div>`); return; }
    for (const e of entries) {
      const open = state.expanded.has(e.path);
      if (e.dir) {
        rows.push(`<div class="row" style="--depth:${depth}" data-dir="${esc(e.path)}" draggable="true"><span class="caret ${open ? "open" : ""}">${icon("chevron")}</span><span class="ficon dir">${icon(open ? "folderOpen" : "folder")}</span><span class="name">${esc(e.name)}</span><button class="icon-btn sm hover-act" data-at="${esc(e.path)}" title="Reference in chat">${icon("at")}</button></div>`);
        if (open) await walk(e.path, depth + 1);
      } else {
        const on = state.active === "file:" + e.path ? "on" : "";
        rows.push(`<div class="row ${on}" style="--depth:${depth}" data-file="${esc(e.path)}" draggable="true"><span class="caret"></span>${fileIcon(e.path)}<span class="name">${esc(e.name)}</span><button class="icon-btn sm hover-act" data-at="${esc(e.path)}" title="Reference in chat">${icon("at")}</button></div>`);
      }
    }
  };
  await walk(".", 0);
  el.innerHTML = rows.join("") || `<div class="empty-state">Empty folder.</div>`;
}
$("#tree").addEventListener("click", (e) => {
  const picked = e.target.closest("[data-file],[data-dir]");
  if (picked) { state.picked = picked.dataset.file || picked.dataset.dir; $$("#tree .row").forEach((r) => r.classList.toggle("picked", r === picked)); }
  const at = e.target.closest("[data-at]");
  if (at) { e.stopPropagation(); insertRef(at.dataset.at); return; }
  const d = e.target.closest("[data-dir]");
  if (d) { const p = d.dataset.dir; state.expanded.has(p) ? state.expanded.delete(p) : state.expanded.add(p); renderTree(); return; }
  const f = e.target.closest("[data-file]"); if (f) openFile(f.dataset.file);
});
$("#tree").addEventListener("dragstart", (e) => {
  const r = e.target.closest("[data-file],[data-dir]"); if (!r) return;
  e.dataTransfer.setData("text/plain", "@" + (r.dataset.file || r.dataset.dir) + " ");
  e.dataTransfer.effectAllowed = "copy";
});

async function loadWorkspaceInfo() {
  if (!state.sid) return;
  const w = await api(`/api/sessions/${state.sid}/workspace`).catch(() => null);
  state.wsInfo = w;
  state.testCmd = w?.test_cmd || "";
  $("#sbTest").innerHTML = state.workspace ? `${icon("beaker")}${esc(state.testCmd || "no test command")}` : "";
  renderModes();
  if ($(".view.on")?.dataset.view === "memory") renderMemory();
}

// ---------------------------------------------------------------- editor tabs
function openTab(tab) {
  const existing = state.tabs.find((t) => t.id === tab.id);
  if (existing) Object.assign(existing, tab); else state.tabs.push(tab);
  state.active = tab.id; renderEditor();
}
function closeTab(id) {
  const i = state.tabs.findIndex((t) => t.id === id); if (i < 0) return;
  state.tabs.splice(i, 1);
  if (state.active === id) state.active = state.tabs[Math.min(i, state.tabs.length - 1)]?.id || null;
  renderEditor();
}
function renderTabs() {
  $("#editorTabs").innerHTML = state.tabs.map((t) => `<div class="tab ${t.id === state.active ? "on" : ""}" data-tab="${esc(t.id)}" title="${esc(t.tip || t.title)}">
    <span class="ticon">${t.kind === "file" ? fileIcon(t.path) : icon(t.icon || "file")}</span><span class="label">${esc(t.title)}</span>
    <button class="icon-btn sm close" data-close="${esc(t.id)}">${icon("x")}</button></div>`).join("");
}
$("#editorTabs").addEventListener("click", (e) => {
  const c = e.target.closest("[data-close]"); if (c) { e.stopPropagation(); closeTab(c.dataset.close); return; }
  const t = e.target.closest("[data-tab]"); if (t) { state.active = t.dataset.tab; renderEditor(); }
});
$("#editorTabs").addEventListener("auxclick", (e) => { const t = e.target.closest("[data-tab]"); if (t && e.button === 1) closeTab(t.dataset.tab); });
function renderEditor() {
  renderTabs();
  const tab = state.tabs.find((t) => t.id === state.active);
  const ed = $("#editor");
  if (!tab) { ed.innerHTML = welcomeHtml(); bindWelcome(); return; }
  if (tab.kind === "file") renderFileTab(tab);
  else if (tab.kind === "trace") renderTraceTab(tab);
  else if (tab.kind === "diff") renderDiffTab(tab);
  else if (tab.kind === "gitdiff") renderGitDiffTab(tab);
  $$("#tree .row[data-file]").forEach((r) => r.classList.toggle("on", "file:" + r.dataset.file === state.active));
}
function welcomeHtml() {
  const recent = (state.sessionList || []).slice(0, 5).map((s) => `<div class="link" data-open-session="${s.id}">${icon("history")}${esc(s.title || "New session")} <span class="muted">${esc(s.repo ? base(s.repo) : "")}</span></div>`).join("");
  const mod = isMac ? "⌘" : "Ctrl+";
  return `<div class="ed-scroll" style="display:flex"><div class="welcome">
    <h1>${icon("logo")}codepilot</h1>
    <p>Your coding copilot on ${{ ollama: "a local model (Ollama)", bedrock: "Claude via Amazon Bedrock", anthropic: "Claude via the Anthropic API", openai: "the OpenAI API" }[state.cfg?.provider] || "your model"}. Open a folder, then ask in chat. Reference files with <kbd>@</kbd>, drag them in from the explorer, or select lines in a file.</p>
    <h3>Start</h3>
    <div class="link" id="wOpen">${icon("folderOpen")}Open folder…</div>
    <div class="link" id="wNew">${icon("plus")}New session</div>
    <div class="link" id="wFind">${icon("search")}Go to file…</div>
    ${recent ? `<h3>Recent sessions</h3>${recent}` : ""}
    <h3>Shortcuts</h3>
    <div class="kbd-grid"><kbd>Ctrl+\`</kbd><span>Terminal</span><kbd>${mod}P</kbd><span>Go to file</span><kbd>${mod}B</kbd><span>Toggle sidebar</span><kbd>${mod}J</kbd><span>Toggle bottom panel</span><kbd>${mod}L</kbd><span>Focus chat</span><kbd>Alt+W</kbd><span>Close tab</span><kbd>@</kbd><span>Reference a file in chat</span></div>
  </div></div>`;
}
function bindWelcome() {
  $("#wOpen") && ($("#wOpen").onclick = openFolder);
  $("#wNew") && ($("#wNew").onclick = () => newSession());
  $("#wFind") && ($("#wFind").onclick = openPalette);
  $$("[data-open-session]").forEach((el) => (el.onclick = () => openSession(el.dataset.openSession)));
}

// file tab
async function openFile(path, line) {
  if (!state.sid || !state.workspace) return toast("Open a folder first.", true);
  const id = "file:" + path;
  const existing = state.tabs.find((t) => t.id === id);
  if (existing && existing.content != null) { existing.flash = line || null; if (line) existing.sel = null; state.active = id; renderEditor(); return; }
  try {
    const d = await api(`/api/sessions/${state.sid}/files?path=${encodeURIComponent(path)}`);
    if (d.entries) { state.expanded.add(path); setView("explorer"); renderTree(); return; }
    openTab({ id, kind: "file", path: d.path, title: base(d.path), tip: d.path, content: d.content, flash: line || null, sel: null });
  } catch (err) { toast(err.message, true); }
}
function highlight(text, path) {
  const lang = LANGS[extOf(path)];
  if (window.hljs && lang && text.length < 400000 && hljs.getLanguage(lang)) {
    try { return hljs.highlight(text, { language: lang, ignoreIllegals: true }).value; } catch { /* fall through */ }
  }
  return esc(text);
}
function renderFileTab(tab) {
  const lines = tab.content.split("\n");
  if (lines.length > 1 && lines[lines.length - 1] === "") lines.pop();
  const sel = tab.sel;
  const selLabel = sel ? (sel.a === sel.b ? `line ${sel.a}` : `lines ${sel.a}–${sel.b}`) : "";
  const parts = tab.path.split("/");
  $("#editor").innerHTML = `<div class="ed-bar"><span class="crumbs">${parts.slice(0, -1).map(esc).join(" › ")}${parts.length > 1 ? " › " : ""}<b>${esc(parts.at(-1))}</b></span>
      <span class="spacer"></span><span class="muted">${selLabel ? selLabel.replace("lines", "L").replace("line", "L") : lines.length + " lines"}</span>
      <button class="btn" id="fAdd" title="Reference in chat">${icon("at")}${sel ? "Add lines" : "Add to chat"}</button>
      <button class="btn" id="fAsk">${icon("sparkle")}Ask</button>
      <button class="btn ghost" id="fCopy" title="Copy path (right-click a file for more)">${icon("copy")}</button>
      <button class="btn ghost" id="fReload" title="Reload from disk">${icon("refresh")}</button></div>
    <div class="ed-scroll" id="edScroll"><div class="code-view">
      <div class="gutter" id="gutter">${lines.map((_, i) => `<div data-ln="${i + 1}" class="${sel && i + 1 >= sel.a && i + 1 <= sel.b ? "sel" : ""}">${i + 1}</div>`).join("")}</div>
      <div class="code-wrap" id="codeWrap"><pre><code>${highlight(lines.join("\n"), tab.path)}</code></pre></div></div></div>`;
  const wrap = $("#codeWrap");
  const addHl = (a, b, cls) => wrap.insertAdjacentHTML("afterbegin", `<div class="line-hl ${cls}" style="top:${6 + (a - 1) * 20}px;height:${(b - a + 1) * 20}px"></div>`);
  if (sel) addHl(sel.a, sel.b, "");
  if (tab.flash) { addHl(tab.flash, tab.flash, "flash"); requestAnimationFrame(() => { $("#edScroll").scrollTop = Math.max(0, (tab.flash - 8) * 20); }); }
  $("#gutter").onclick = (e) => {
    const ln = +e.target.dataset.ln; if (!ln) return;
    if (e.shiftKey && tab.sel) tab.sel = { a: Math.min(tab.sel.a, ln), b: Math.max(tab.sel.b, ln) };
    else tab.sel = tab.sel && tab.sel.a === ln && tab.sel.b === ln ? null : { a: ln, b: ln };
    tab.flash = null; const st = $("#edScroll").scrollTop; renderFileTab(tab); $("#edScroll").scrollTop = st;
  };
  const ref = () => tab.path + (tab.sel ? `:${tab.sel.a}${tab.sel.b !== tab.sel.a ? "-" + tab.sel.b : ""}` : "");
  $("#fAdd").onclick = () => insertRef(ref());
  $("#fCopy").onclick = () => copyText(ref());
  $(".crumbs").title = "Right-click for path options";
  $(".crumbs").oncontextmenu = (e) => { e.preventDefault(); showMenu(e.clientX, e.clientY, pathMenu(tab.path, false)); };
  $("#fAsk").onclick = () => { setInput(`Explain @${ref()} — what it does, how it fits in, and any bugs you see.`); };
  $("#fReload").onclick = async () => { tab.content = null; const id = tab.id; await openFile(tab.path); state.active = id; };
}

// trace tab
async function openTrace(path) {
  try {
    const d = await api(`/api/sessions/${state.sid}/trace?path=${encodeURIComponent(path)}`);
    openTab({ id: "trace:" + path, kind: "trace", icon: "pulse", path, title: base(path), tip: path, data: d });
  } catch (err) { toast(err.message, true); }
}
function renderTraceTab(tab) {
  const d = tab.data, o = d.outline, spans = o.spans || [];
  const t0 = spans.length ? spans[0].start_ms : 0;
  const total = spans.length ? Math.max(...spans.map((s) => s.start_ms + (s.duration_ms || 0))) - t0 : 0;
  const ids = Object.entries(o.ids || {}).map(([k, v]) => `<div><span>${esc(k)}</span>${esc(v.slice(0, 3).join(", "))}</div>`).join("");
  const rows = spans.slice(0, 500).map((s) => {
    const left = total ? ((s.start_ms - t0) / total) * 100 : 0;
    const width = total && s.duration_ms ? (s.duration_ms / total) * 100 : 0.5;
    const tip = `${s.name}\n+${fmtMs(s.start_ms - t0)} · ${fmtMs(s.duration_ms)}${s.status ? "\n" + s.status : ""}\n${JSON.stringify(s.attrs, null, 1)}`;
    return `<div class="tl-row" title="${esc(tip)}"><span class="tl-name ${s.error ? "err" : ""}">${esc(s.name)}</span><div class="tl-track"><div class="tl-bar ${s.error ? "err" : ""}" style="left:${left}%;width:${Math.max(width, 0.5)}%"></div></div><span class="tl-dur">${fmtMs(s.duration_ms)}</span></div>`;
  }).join("");
  $("#editor").innerHTML = `<div class="ed-bar"><span class="crumbs"><b>${esc(tab.path)}</b></span><span class="spacer"></span><span class="muted">${fmtBytes(d.size)}</span>
      <button class="btn primary" id="tAsk">${icon("sparkle")}Ask codepilot about this trace</button><button class="btn" id="tRef">${icon("at")}Add to chat</button></div>
    <div class="ed-scroll"><div class="trace-view">
      <div class="stats"><div class="stat"><b>${o.records}</b><span>records</span></div><div class="stat"><b>${spans.length}</b><span>spans</span></div>
        <div class="stat"><b style="color:${o.errors ? "var(--err)" : "inherit"}">${o.errors}</b><span>errors</span></div><div class="stat"><b>${spans.length ? fmtMs(total) : "—"}</b><span>duration</span></div></div>
      ${ids ? `<div class="ids">${ids}</div>` : ""}
      ${spans.length ? `<div class="section-title">Timeline</div><div class="timeline">${rows}</div>` : `<div class="hint">No spans detected; see the raw records below.</div>`}
      <div class="section-title">Raw ${d.records ? "" : "(too large to display; codepilot can still read it)"}</div><div class="jtree" id="jtree"></div>
    </div></div>`;
  $("#tAsk").onclick = () => setInput(`Analyze trace @${tab.path}: walk through what happened, flag anything that failed or looks wrong, and point to the code responsible.`);
  $("#tRef").onclick = () => insertRef(tab.path);
  if (d.records) $("#jtree").appendChild(jsonTree(d.records.length === 1 ? d.records[0] : d.records, 0));
}
function jsonTree(v, depth, key) {
  const k = key !== undefined ? `<span class="k">${esc(key)}</span>: ` : "";
  if (v && typeof v === "object") {
    const entries = Array.isArray(v) ? v.map((x, i) => [i, x]) : Object.entries(v);
    const d = document.createElement("details"); if (depth < 1) d.open = true;
    d.innerHTML = `<summary>${k}<span class="muted">${Array.isArray(v) ? `[${v.length}]` : `{${entries.length}}`}</span></summary>`;
    let built = false;
    const build = () => { if (built) return; built = true; for (const [ck, cv] of entries.slice(0, 300)) d.appendChild(jsonTree(cv, depth + 1, ck)); if (entries.length > 300) d.insertAdjacentHTML("beforeend", `<div class="leaf muted">… ${entries.length - 300} more</div>`); };
    if (d.open) build(); d.addEventListener("toggle", build);
    return d;
  }
  const div = document.createElement("div"); div.className = "leaf";
  const cls = typeof v === "string" ? "s" : typeof v === "number" ? "n" : "b";
  const shown = typeof v === "string" ? JSON.stringify(v.length > 2000 ? v.slice(0, 2000) + "…" : v) : String(v);
  div.innerHTML = `${k}<span class="${cls}">${esc(shown)}</span>`; return div;
}

// diff tabs
function diffHtml(diff) {
  return `<div class="diff">${diff.split("\n").map((l) => {
    const c = l.startsWith("+++") || l.startsWith("---") || l.startsWith("@@") || l.startsWith("diff ") ? "h" : l.startsWith("+") ? "a" : l.startsWith("-") ? "d" : "";
    return `<div class="${c}">${esc(l) || " "}</div>`; }).join("")}</div>`;
}
function openProposal(id) {
  const p = state.proposals.get(+id); if (!p) return;
  openTab({ id: "diff:" + p.id, kind: "diff", icon: "diff", title: `#${p.id} ${base(p.path)}`, tip: p.path, pid: p.id });
}
function renderDiffTab(tab) {
  const p = state.proposals.get(tab.pid);
  if (!p) { $("#editor").innerHTML = `<div class="empty-state">Proposal not found.</div>`; return; }
  $("#editor").innerHTML = `<div class="ed-bar"><span class="crumbs"><b>${esc(p.path)}</b></span><span class="status ${p.status}">${p.status}</span><span class="muted">${esc(p.reason || "")}</span><span class="spacer"></span>
      ${propActions(p)}
      <button class="btn ghost" id="dOpen">${icon("file")}Open file</button></div>
    <div class="ed-scroll">${diffHtml(p.diff)}</div>`;
  $("#dOpen").onclick = () => openFile(p.path);
}
async function openGitDiff() {
  const g = await api(`/api/sessions/${state.sid}/git`).catch(() => null);
  if (!g || !g.git) return toast("Not a git repository.", true);
  openTab({ id: "gitdiff", kind: "gitdiff", icon: "branch", title: "Working tree", data: g });
}
function renderGitDiffTab(tab) {
  const g = tab.data;
  $("#editor").innerHTML = `<div class="ed-bar"><span class="crumbs">${icon("branch")} <b>${esc(g.branch)}</b> · uncommitted changes</span><span class="spacer"></span><button class="btn ghost" id="gReload">${icon("refresh")}</button></div>
    <div class="ed-scroll">${g.diff.trim() ? diffHtml(g.diff) : `<div class="empty-state">No unstaged changes.</div>`}</div>`;
  $("#gReload").onclick = async () => { tab.data = await api(`/api/sessions/${state.sid}/git`); renderEditor(); };
}

// ---------------------------------------------------------------- search view
const runGrep = debounce(async () => {
  const q = $("#grepInput").value.trim();
  if (!q || !state.sid) { $("#grepResults").innerHTML = ""; $("#grepStatus").textContent = ""; return; }
  $("#grepStatus").textContent = "Searching…";
  try {
    const d = await api(`/api/sessions/${state.sid}/grep?q=${encodeURIComponent(q)}&glob=${encodeURIComponent($("#grepGlob").value.trim())}`);
    const byFile = new Map();
    for (const r of d.results) { if (!byFile.has(r.path)) byFile.set(r.path, []); byFile.get(r.path).push(r); }
    $("#grepStatus").textContent = `${d.results.length} result${d.results.length === 1 ? "" : "s"} in ${byFile.size} file${byFile.size === 1 ? "" : "s"}${d.truncated ? " (limited)" : ""}`;
    let rx; try { rx = new RegExp(q, "gi"); } catch { rx = new RegExp(q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi"); }
    $("#grepResults").innerHTML = [...byFile].map(([path, hits]) => `<div class="grep-file"><div class="row" data-gfile="${esc(path)}">${fileIcon(path)}<span class="name">${esc(base(path))}</span><span class="meta">${esc(dirOf(path))}</span></div>
      ${hits.map((h) => `<div class="grep-hit" data-gpath="${esc(h.path)}" data-gline="${h.line}"><b>${h.line}</b>${esc(h.text.trim()).replace(rx, (m) => `<mark>${m}</mark>`)}</div>`).join("")}</div>`).join("");
  } catch (err) { $("#grepStatus").textContent = err.message; }
}, 250);
$("#grepInput").addEventListener("input", runGrep);
$("#grepGlob").addEventListener("input", runGrep);
$("#grepResults").addEventListener("click", (e) => {
  const h = e.target.closest("[data-gpath]"); if (h) return openFile(h.dataset.gpath, +h.dataset.gline);
  const f = e.target.closest("[data-gfile]"); if (f) openFile(f.dataset.gfile);
});

// ---------------------------------------------------------------- traces view
async function loadTraces() {
  if (!state.sid || !state.workspace) { $("#traceRoots").textContent = "Open a folder to see its traces and logs."; $("#traceList").innerHTML = ""; return; }
  const d = await api(`/api/sessions/${state.sid}/traces`).catch(() => ({ roots: [], files: [] }));
  state.traceFiles = d.files;
  $("#traceRoots").textContent = d.roots.length ? d.roots.map((r) => r.replace(state.workspace + "/", "")).join(", ") : "No traces/ or logs/ folder found (CODEPILOT_TRACE_DIRS adds more).";
  renderTraceList();
}
function renderTraceList() {
  const q = $("#traceFilter").value.toLowerCase();
  const files = state.traceFiles.filter((f) => f.path.toLowerCase().includes(q));
  $("#traceList").innerHTML = files.map((f) => `<div class="row ${state.active === "trace:" + f.path ? "on" : ""}" style="padding-left:4px" data-trace="${esc(f.path)}">${icon("pulse")}<span class="name" title="${esc(f.path)}">${esc(base(f.path))}</span><span class="meta">${fmtBytes(f.size)} · ${ago(f.mtime)}</span></div>`).join("");
}
$("#traceFilter").addEventListener("input", renderTraceList);
$("#refreshTracesBtn").onclick = loadTraces;
$("#traceList").addEventListener("click", (e) => { const r = e.target.closest("[data-trace]"); if (r) { openTrace(r.dataset.trace).then(renderTraceList); } });

// ---------------------------------------------------------------- changes view
function renderProposalList() {
  const list = [...state.proposals.values()].reverse();
  const pending = list.filter((p) => p.status === "pending").length;
  $("#changesBadge").hidden = !pending; $("#changesBadge").textContent = pending;
  $("#proposalList").innerHTML = list.map((p) => `<div class="row" data-prop-open="${p.id}">${icon("diff")}<span class="name">${esc(base(p.path))} <span class="muted">#${p.id}</span></span>${p.status === "applied" ? `<button class="icon-btn sm hover-act" data-revert="${p.id}" title="Undo">${icon("history")}</button>` : ""}<span class="status ${p.status}">${p.status}</span></div>`).join("")
    || `<div class="hint" style="padding:0 14px">Nothing proposed yet. Diffs codepilot suggests show up here for review.</div>`;
}
$("#proposalList").addEventListener("click", (e) => { const r = e.target.closest("[data-prop-open]"); if (r) openProposal(r.dataset.propOpen); });
async function loadGit() {
  if (!state.sid || !state.workspace) { $("#gitList").innerHTML = ""; $("#sbBranch").innerHTML = ""; $("#gitBranch").textContent = ""; return; }
  const g = await api(`/api/sessions/${state.sid}/git`).catch(() => null);
  if (!g || !g.git) { $("#gitList").innerHTML = `<div class="hint" style="padding:0 14px">Not a git repository.</div>`; $("#sbBranch").innerHTML = ""; return; }
  $("#gitBranch").textContent = "· " + g.branch;
  $("#sbBranch").innerHTML = `${icon("branch")}${esc(g.branch)}`;
  const lines = g.status.split("\n").filter(Boolean);
  $("#gitList").innerHTML = (lines.length ? `<div class="row" id="openGitDiff">${icon("diff")}<span class="name">View working tree diff</span></div>` : "")
    + lines.map((l) => { const code = l.slice(0, 2).trim(), path = l.slice(3); return `<div class="row" data-gitfile="${esc(path)}">${fileIcon(path)}<span class="name">${esc(path)}</span><span class="meta mono">${esc(code)}</span></div>`; }).join("")
    || `<div class="hint" style="padding:0 14px">Clean working tree.</div>`;
  $("#openGitDiff") && ($("#openGitDiff").onclick = openGitDiff);
}
$("#gitList").addEventListener("click", (e) => { const r = e.target.closest("[data-gitfile]"); if (r && !r.dataset.gitfile.endsWith("/")) openFile(r.dataset.gitfile); });
$("#refreshGitBtn").onclick = loadGit;
document.addEventListener("click", async (e) => {
  const ap = e.target.closest("[data-apply],[data-reject],[data-revert]"); if (!ap) return;
  e.stopPropagation();
  const id = ap.dataset.apply || ap.dataset.reject || ap.dataset.revert;
  const action = ap.dataset.apply ? "apply" : ap.dataset.reject ? "reject" : "revert";
  try {
    const p = await api(`/api/proposals/${id}/${action}`, { method: "POST" }); state.proposals.set(p.id, p);
    toast({ apply: `Applied #${p.id} to ${p.path}`, reject: `Rejected #${p.id}`, revert: `Undid #${p.id}; ${p.path} restored` }[action]);
    if (action === "apply" && p.checks) { toast(`Checks found issues in ${p.path}; codepilot will see them next turn`, true); activity("error", "checks", p.path, p.checks); }
  } catch (err) { toast(err.message, true); if (action === "apply") { const p = state.proposals.get(+id); if (p) p.status = "failed"; } }
  refreshProposalViews(+id); loadGit();
  const p = state.proposals.get(+id);
  const tab = state.tabs.find((t) => t.id === "file:" + p?.path); if (tab) { tab.content = null; if (state.active === tab.id) openFile(tab.path); }
});
function refreshProposalViews(id) {
  const p = state.proposals.get(id); if (!p) return;
  $$(`[data-prop="${id}"]`).forEach((card) => { const s = $(".status", card); s.className = "status " + p.status; s.textContent = p.status; const a = $(".pacts", card); if (a) a.innerHTML = propActions(p); });
  renderProposalList(); if (state.active === "diff:" + id) renderEditor();
}

// ---------------------------------------------------------------- memory view
function renderMemory() {
  const c = state.context, w = state.wsInfo;
  const pct = ctxPct(c);
  $("#memoryView").innerHTML = `
    <div class="group-head" style="padding-left:2px">How memory works</div>
    <div class="hint" style="line-height:1.55">Each step resends this session's conversation (cached, so it's cheap). Before every model call codepilot checks the size: at ${c ? Math.round(c.prune_at * 100) : 60}% of the budget it clears old tool outputs, at ${c ? Math.round(c.compact_at * 100) : 80}% it summarises earlier turns, keeping recent turns, the plan and proposals exact. Workspace notes persist across every session on this folder.</div>
    <div class="group-head" style="padding-left:2px">Working memory</div>
    <div style="display:flex;align-items:center;gap:8px"><span class="meter" style="width:100%"><i class="${ctxClass(c)}" style="width:${pct}%"></i></span><span class="mono" style="font-size:11.5px">${pct}%</span></div>
    <div class="hint">${c ? `~${fmtTok(c.tokens)} of a ${fmtTok(c.budget)}-token budget (model window ${fmtTok(c.window)})` : "—"}</div>
    <div style="display:flex;gap:6px;margin-top:6px"><button class="btn" id="compactBtn" ${state.sid ? "" : "disabled"}>${icon("collapse")}Compact now</button><button class="btn" id="handoffBtn" ${state.sid ? "" : "disabled"} title="Start a fresh session on this folder, seeded with this one's summary">${icon("plus")}Continue in new session</button></div>
    <div class="group-head" style="padding-left:2px">Conversation summary</div>
    <div class="hint">${state.summary ? esc(state.summary).replace(/\n/g, "<br>") : "None yet — appears when the conversation gets long."}</div>
    <div class="group-head" style="padding-left:2px">Workspace notes</div>
    <textarea class="field mono" id="notesBox" rows="7" style="font-size:12px;resize:vertical" placeholder="${state.workspace ? "Facts codepilot should always know about this folder…" : "Open a folder to keep notes for it."}" ${state.workspace ? "" : "disabled"}></textarea>
    <div style="display:flex;gap:6px;align-items:center;margin-top:6px"><button class="btn" id="saveNotes" ${state.workspace ? "" : "disabled"}>Save notes</button><span class="hint" id="notesPath" style="margin:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"></span></div>
    <div class="group-head" style="padding-left:2px">Token usage</div><div id="usageTable" class="hint">—</div>
    <div class="group-head" style="padding-left:2px">Analysers (run_checks)</div>
    <div class="hint">${(w?.checks || []).length ? w.checks.map((c) => `<span class="mono">${esc(c.name)}</span> <span class="muted">${esc(c.kind)}</span>`).join(" · ") : "None detected. Install ruff / mypy / pyright, eslint / tsc, gitleaks, semgrep… and codepilot uses them automatically."}</div>
    <div class="group-head" style="padding-left:2px">Modes</div>
    ${(w?.modes || []).map((m) => `<div class="hint" style="margin:3px 0"><b style="color:var(--fg-2)">${esc(m.label)}</b>${m.builtin ? "" : ' <span class="proj">custom</span>'} — ${esc(m.description)}</div>`).join("")}
    <div class="hint">Add your own in <span class="mono">~/.codepilot/modes/*.md</span> or <span class="mono">.codepilot/modes/</span>.</div>
    <div class="group-head" style="padding-left:2px">Skills</div>
    ${(w?.skills || []).map((s) => `<div class="hint" style="margin:3px 0"><b class="mono" style="color:var(--fg-2)">${esc(s.name)}</b> — ${esc(s.description)}</div>`).join("") || `<div class="hint">—</div>`}
    <div class="group-head" style="padding-left:2px">Project instructions</div>
    <div class="hint">${w?.instructions ? `<pre class="mono" style="white-space:pre-wrap;margin:0;font-size:11.5px">${esc(w.instructions)}</pre>` : "None found (AGENTS.md, CLAUDE.md, .cursorrules, .kiro/steering …)."}</div>`;
  renderUsage(state.usage);
  $("#compactBtn") && ($("#compactBtn").onclick = compactNow);
  $("#handoffBtn") && ($("#handoffBtn").onclick = handoff);
  if (state.workspace && state.sid) {
    api(`/api/sessions/${state.sid}/notes`).then((n) => { $("#notesBox").value = n.notes; $("#notesPath").textContent = n.path; }).catch(() => {});
    $("#saveNotes").onclick = async () => { await api(`/api/sessions/${state.sid}/notes`, { method: "PUT", body: { notes: $("#notesBox").value } }); toast("Notes saved"); };
  }
}
function renderUsage(u) {
  state.usage = u;
  const rows = (u && u.by_model) || [];
  const tot = rows.reduce((a, r) => a + (r.input || 0) + (r.output || 0), 0);
  $("#sbTokens").textContent = `${fmtTok(tot)} tokens`;
  const el = $("#usageTable"); if (!el) return;
  el.innerHTML = rows.length ? rows.map((r) => `<div class="mono" style="font-size:11.5px">${esc(shortModel(r.model))}: ${r.calls} calls · in ${fmtTok(r.input)} · out ${fmtTok(r.output)}${r.cache_read ? ` · cache ${fmtTok(r.cache_read)}` : ""}</div>`).join("") : "—";
}
const ctxPct = (c) => (c && c.budget ? Math.min(100, Math.round((c.tokens / c.budget) * 100)) : 0);
const ctxClass = (c) => { const p = ctxPct(c) / 100; return !c ? "" : p >= c.compact_at ? "high" : p >= c.prune_at ? "mid" : ""; };
function setContext(c) {
  if (!c || c.tokens == null) return;
  state.context = c;
  const pct = ctxPct(c);
  const bar = $("#ctxBar"); bar.style.width = pct + "%"; bar.className = ctxClass(c);
  $("#ctxText").textContent = `context ${pct}% · ${fmtTok(c.tokens)}/${fmtTok(c.budget)}${c.has_summary ? " · summarised" : ""}`;
  $("#sbContext").title = `~${c.tokens.toLocaleString()} prompt tokens of a ${c.budget.toLocaleString()}-token budget (window ${c.window.toLocaleString()}). Old tool outputs are cleared at ${Math.round(c.prune_at * 100)}%, earlier turns summarised at ${Math.round(c.compact_at * 100)}%. Click to compact now.`;
}
async function compactNow() {
  if (!state.sid || state.streams.has(state.sid)) return;
  const focus = await promptDialog("Compact conversation", "", "Optional: what the summary should focus on (e.g. \"the API changes\"). Leave empty for a general summary.");
  if (focus === null) return;
  streamTo(state.sid, `/api/sessions/${state.sid}/compact`, { focus });
}
async function handoff() {
  if (!state.sid) return;
  if (!confirm("Start a fresh session on this folder, seeded with this session's summary?")) return;
  try { const s = await api(`/api/sessions/${state.sid}/handoff`, { method: "POST" }); await openSession(s.id); toast("Continued in a new session"); }
  catch (err) { toast(err.message, true); }
}
$("#sbContext").style.cursor = "pointer";
$("#sbContext").addEventListener("click", compactNow);
async function refreshUsage() { if (state.sid) renderUsage(await api(`/api/sessions/${state.sid}/usage`).catch(() => null)); }

// ---------------------------------------------------------------- chat rendering
let curText = null, curThink = null, curBuf = "";
function endText() { curText = null; curThink = null; curBuf = ""; }
let stickToBottom = true;
function scrollEnd(force) { const t = $("#transcript"); if (force) stickToBottom = true; if (stickToBottom) t.scrollTop = t.scrollHeight; }
$("#transcript").addEventListener("scroll", () => { const t = $("#transcript"); stickToBottom = t.scrollHeight - t.scrollTop - t.clientHeight < 80; });
function add(html) { $(".chat-empty")?.remove(); const d = document.createElement("div"); d.innerHTML = html; const el = d.firstElementChild; $("#transcript").appendChild(el); return el; }
function renderChatEmpty() {
  $("#transcript").innerHTML = `<div class="chat-empty">${icon("sparkle")}<b>What should we work on?</b>${state.workspace ? `Working in <span class="mono">${esc(base(state.workspace))}</span>. Ask for a review, a fix, tests, or an explanation.` : "Open a folder, or just say which one — e.g. “review ~/code/payments for bugs”."}</div>`;
}
const QUICK = [
  ["Review changes", "Review my uncommitted changes and recent commits. Report real defects with locations and fixes."],
  ["Map codebase", "Give me a map of this codebase: entry points, main components, data flow, and where state lives. Cite files."],
  ["Run tests & fix", "Run the unit tests. For any failure, find the root cause and propose a minimal fix."],
  ["Triage traces", "Look at the newest traces or logs. What failed or behaved badly, and what in the code caused it?"],
  ["Find bugs", "Hunt for likely bugs in the core code: error handling, edge cases, contracts between components. Rank by severity."],
];
function renderQuick() { $("#quick").innerHTML = QUICK.map(([l], i) => `<button data-q="${i}">${esc(l)}</button>`).join(""); }
$("#quick").addEventListener("click", (e) => { const b = e.target.closest("[data-q]"); if (b) setInput(QUICK[+b.dataset.q][1]); });

function linkify(html) {
  // path:line or path:line-line → open in editor
  html = html.replace(/(^|[\s(>"'])((?:[\w.-]+\/)*[\w.-]+\.[A-Za-z0-9]{1,6}):(\d+)(?:-(\d+))?/g,
    (m, pre, p, a) => `${pre}<a class="loc" data-path="${p}" data-line="${a}">${m.slice(pre.length)}</a>`);
  return html;
}
function inline(s) {
  return linkify(s
    .replace(/`([^`]+)`/g, (m, c) => (/^[\w.-]+(\/[\w.-]+)+$|^[\w-]+\.[a-z]{1,6}$/i.test(c) ? `<code><a class="loc" data-path="${c}">${c}</a></code>` : `<code>${c}</code>`))
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|\W)_([^_\n]+)_(?=\W|$)/g, "$1<em>$2</em>")
    .replace(/(^|[\s(])\*([^*\s][^*\n]*?)\*(?=[\s.,;:!?)]|$)/g, "$1<em>$2</em>")
    .replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>'));
}
function md(src) {
  const out = [];
  const parts = String(src).split(/```/);
  parts.forEach((part, i) => {
    if (i % 2) {
      const nl = part.indexOf("\n"); const lang = nl >= 0 ? part.slice(0, nl).trim() : ""; const code = nl >= 0 ? part.slice(nl + 1) : part;
      let html = esc(code);
      if (window.hljs && lang && hljs.getLanguage(lang)) { try { html = hljs.highlight(code, { language: lang, ignoreIllegals: true }).value; } catch { /* keep plain */ } }
      out.push(`<pre><button class="icon-btn sm copy" title="Copy">${icon("copy")}</button><code>${html}</code></pre>`); return;
    }
    let list = null;
    for (const line of esc(part).split("\n")) {
      const li = line.match(/^\s*([-*]|\d+\.)\s+(.*)$/);
      if (li) { const t = /\d/.test(li[1]) ? "ol" : "ul"; if (list !== t) { if (list) out.push(`</${list}>`); out.push(`<${t}>`); list = t; } out.push(`<li>${inline(li[2])}</li>`); continue; }
      if (list) { out.push(`</${list}>`); list = null; }
      const h = line.match(/^(#{1,4})\s+(.*)$/);
      if (h) out.push(`<h3>${inline(h[2])}</h3>`); else if (line.trim()) out.push(`<p>${inline(line)}</p>`);
    }
    if (list) out.push(`</${list}>`);
  });
  return out.join("");
}
function userHtml(text) {
  return esc(text).replace(/(^|[\s(])@([\w.\-/~]+)(?::(\d+)(?:-(\d+))?)?/g, (m, pre, p, a) => `${pre}<span class="ref" data-path="${p}" ${a ? `data-line="${a}"` : ""}>@${m.slice(pre.length + 1)}</span>`);
}
function argSummary(name, input) {
  if (!input) return "";
  if (!Object.values(input).some((v) => v !== "" && v != null)) return "";
  if (name === "update_plan" && Array.isArray(input.items)) return `${input.items.filter((i) => i.status === "done").length}/${input.items.length} done`;
  if (input.path && (input.start_line || input.end_line)) return `${input.path}:${input.start_line || 1}-${input.end_line || ""}`;
  return input.path || input.pattern || input.query || input.command || input.task || input.args || input.name || input.log_group || input.note || JSON.stringify(input).slice(0, 120);
}
function toolEl(ev) {
  const el = add(`<details class="tool"><summary><span class="ticon">${icon(TOOL_ICONS[ev.name] || "tool")}</span><span class="tname">${esc(ev.name)}</span>
    <span class="targ">${esc(argSummary(ev.name, ev.input))}</span><span class="st"><span class="spinner"></span></span></summary>
    <pre>${esc(JSON.stringify(ev.input, null, 2))}</pre></details>`);
  state.toolEls.set(ev.id, el); return el;
}
function render(ev, replay) {
  switch (ev.type) {
    case "user": endText(); add(`<div class="msg user">${userHtml(ev.text)}</div>`); break;
    case "attached": add(`<div class="attached">${ev.paths.map((p) => `<span data-path="${esc(p.split(":")[0])}" data-line="${esc(p.split(":")[1]?.split("-")[0] || "")}">${icon("file")} ${esc(p)}</span>`).join("")}</div>`); break;
    case "assistant": endText(); add(`<div class="msg assistant">${md(ev.text)}</div>`); break;
    case "skill": add(`<div class="skill-chip">${icon("sparkle")}skill: ${esc(ev.name)}</div>`); break;
    case "text":
      if (!curText) { curText = add(`<div class="msg assistant"></div>`); curBuf = ""; }
      curBuf += ev.text; curText.innerHTML = md(curBuf); break;
    case "thinking":
      if (!curThink) curThink = add(`<div class="thinking"></div>`);
      curThink.textContent += ev.text; curThink.scrollTop = curThink.scrollHeight; break;
    case "tool_call": endText(); toolEl(ev); if (!replay) activity("call", ev.name, argSummary(ev.name, ev.input), JSON.stringify(ev.input, null, 2)); break;
    case "tool_running": { const el = state.toolEls.get(ev.id); if (el) $(".st", el).innerHTML = '<span class="spinner"></span>'; break; }
    case "tool_result": {
      const el = state.toolEls.get(ev.id) || toolEl({ id: ev.id, name: ev.name, input: null });
      const exit = ev.output.match(/^exit code (-?\d+)/m);
      const failedRun = !ev.is_error && exit && exit[1] !== "0";
      const st = $(".st", el); st.className = "st " + (ev.is_error ? "err" : failedRun ? "warn" : "ok");
      st.innerHTML = `${icon(ev.is_error || failedRun ? "alert" : "check")}${failedRun ? "exit " + exit[1] + " · " : ""}${ev.seconds ? ev.seconds + "s" : ""}`;
      el.insertAdjacentHTML("beforeend", `<pre>${esc(ev.output)}</pre>`);
      if (!replay) activity(ev.is_error ? "error" : "result", ev.name, `${ev.output.length.toLocaleString()} chars${ev.seconds ? " · " + ev.seconds + "s" : ""}`, ev.output);
      break;
    }
    case "sub_tool": {
      const el = state.toolEls.get(ev.parent); if (!el) break;
      let subs = $(".subs", el); if (!subs) { subs = document.createElement("div"); subs.className = "subs"; $("summary", el).after(subs); el.open = true; }
      subs.insertAdjacentHTML("beforeend", `<div>↳ ${esc(ev.name)} ${esc(ev.detail)}</div>`); subs.scrollTop = subs.scrollHeight;
      if (!replay) activity("explore", ev.name, ev.detail); break;
    }
    case "proposal": endText(); state.proposals.set(ev.proposal.id, ev.proposal); renderProposalCard(ev.proposal); renderProposalList(); break;
    case "approval_needed": {
      endText();
      const el = add(`<div class="card approval"><div class="hd">${icon("alert")}<strong>Approval needed</strong></div>
        ${ev.tools.map((t) => `<div class="cmd">$ ${esc(t.command)}</div>`).join("")}
        <div class="acts"><button class="btn primary" data-approve="1">${icon("check")}Approve &amp; run</button><button class="btn" data-approve="0">Deny</button></div></div>`);
      el.addEventListener("click", (e) => { const b = e.target.closest("[data-approve]"); if (!b) return; el.remove(); streamTo(state.sid, `/api/sessions/${state.sid}/approve`, { approve: b.dataset.approve === "1" }); });
      break;
    }
    case "workspace": setWorkspace(ev.repo, true); loadSessions(); toast(`Opened ${ev.repo}`); break;
    case "plan": renderPlan(ev.items); break;
    case "usage": { const u = ev.usage || {}; activity("model", shortModel(ev.model || ""), `in ${fmtTok(u.inputTokens || 0)} · out ${fmtTok(u.outputTokens || 0)}${u.cacheReadInputTokens ? " · cached " + fmtTok(u.cacheReadInputTokens) : ""} · ${ev.seconds}s`); endText(); refreshUsage(); break; }
    case "context": setContext(ev); break;
    case "notice": endText(); add(`<div class="banner notice">${esc(ev.message)}</div>`); break;
    case "error": endText(); add(`<div class="banner error">${esc(ev.message)}</div>`); if (!replay) activity("error", "error", ev.message); break;
    case "done": endText(); break;
  }
  if (!replay) scrollEnd();
}
function propActions(p) {
  if (p.status === "pending") return `<button class="btn primary" data-apply="${p.id}">Apply</button><button class="btn" data-reject="${p.id}">Reject</button>`;
  if (p.status === "applied") return `<button class="btn" data-revert="${p.id}" title="Restore the file as it was before this change">${icon("history")}Undo</button>`;
  return "";
}
function renderProposalCard(p) {
  return add(`<div class="card" data-prop="${p.id}"><div class="hd">${icon("edit")}<span class="path" data-prop-open="${p.id}">${esc(p.path)}</span><span class="muted">#${p.id}</span><span class="status ${p.status}">${p.status}</span><span class="spacer"></span>
    <span class="pacts">${propActions(p)}</span></div>
    ${p.reason ? `<div class="reason">${esc(p.reason)}</div>` : ""}${diffHtml(p.diff)}</div>`);
}
function renderPlan(items) {
  const el = $("#plan");
  if (!items || !items.length) { el.hidden = true; el.innerHTML = ""; return; }
  el.hidden = false;
  el.innerHTML = items.map((i) => `<div class="it ${esc(i.status)}"><span class="box"></span><span>${esc(i.text)}</span></div>`).join("");
}
$("#transcript").addEventListener("click", (e) => {
  const loc = e.target.closest("a.loc, .ref, .attached span");
  if (loc) { e.preventDefault(); openFile(loc.dataset.path, +loc.dataset.line || undefined); return; }
  const po = e.target.closest("[data-prop-open]"); if (po) { openProposal(po.dataset.propOpen); return; }
  const cp = e.target.closest(".copy");
  if (cp) { navigator.clipboard?.writeText(cp.parentElement.querySelector("code").innerText); toast("Copied"); }
});

function activity(kind, name, detail, body) {
  state.activity++; $("#actCount").textContent = state.activity;
  const t = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
  const label = `<b>${esc(name)}</b> <span class="muted">${esc(detail || "")}</span>`;
  $("#activity").insertAdjacentHTML("beforeend", `<div class="act"><span class="t">${t}</span><span class="k ${kind}">${esc(kind)}</span>${body ? `<details><summary>${label}</summary><pre>${esc(body)}</pre></details>` : `<span class="d">${label}</span>`}</div>`);
  const pane = $("#activity"); pane.scrollTop = pane.scrollHeight;
}

// ---------------------------------------------------------------- streaming
function updateBusy() {
  const busy = state.streams.has(state.sid);
  $("#sendBtn").hidden = busy; $("#stopBtn").hidden = !busy;
  $("#sbBusy").innerHTML = busy ? '<span class="spinner"></span>working…' : "";
}
async function streamTo(sid, url, body) {
  if (state.streams.has(sid)) return;
  state.streams.add(sid); updateBusy(); loadSessions();
  const typing = sid === state.sid ? add(`<div class="typing"><i></i><i></i><i></i></div>`) : null;
  try {
    const res = await fetch(url, { method: "POST", headers: H, body: JSON.stringify(body) });
    if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.error || res.statusText); }
    const reader = res.body.getReader(); const dec = new TextDecoder(); let buf = "";
    for (;;) {
      const { value, done } = await reader.read(); if (done) break;
      buf += dec.decode(value, { stream: true });
      let nl;
      while ((nl = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, nl); buf = buf.slice(nl + 1);
        if (!line.trim()) continue;
        if (sid === state.sid) { render(JSON.parse(line)); if (typing && typing.isConnected) $("#transcript").appendChild(typing); }
      }
    }
  } catch (err) { if (sid === state.sid) render({ type: "error", message: err.message }); }
  finally {
    typing?.remove(); state.streams.delete(sid); updateBusy(); loadSessions();
    if (sid === state.sid) { loadGit(); const d = await api(`/api/sessions/${sid}`).catch(() => null); if (d) { state.summary = d.summary; $("#chatTitle").textContent = d.session.title || "New session"; if ($(".view.on")?.dataset.view === "memory") renderMemory(); } }
  }
}
async function send() {
  const text = $("#input").value.trim(); if (!text) return;
  if (state.sid && state.streams.has(state.sid)) return;
  if (!state.sid) { try { await newSession(state.workspace); } catch (err) { toast(err.message, true); return; } }
  $("#input").value = ""; autosize(); hideMentions();
  render({ type: "user", text }); scrollEnd(true);
  if (!state.session?.title) $("#chatTitle").textContent = text.split("\n")[0].slice(0, 80);
  streamTo(state.sid, `/api/sessions/${state.sid}/chat`, { message: text, tier: $("#tier").value });
}
$("#sendBtn").onclick = send;
$("#stopBtn").onclick = () => state.sid && api(`/api/sessions/${state.sid}/cancel`, { method: "POST" });
const DEFAULT_MODES = [{ name: "build", label: "Build", description: "Implement changes", blocked: [] }];
function renderModes() {
  const list = state.wsInfo?.modes || DEFAULT_MODES;
  const sel = $("#modeSelect");
  sel.innerHTML = list.map((m) => `<option value="${esc(m.name)}" title="${esc(m.description)}">${esc(m.label)}</option>`).join("");
  if (!list.some((m) => m.name === state.mode)) state.mode = "build";
  sel.value = state.mode; setMode(state.mode);
}
function setMode(mode) {
  state.mode = mode;
  const m = (state.wsInfo?.modes || DEFAULT_MODES).find((x) => x.name === mode);
  const readonly = !!m && m.blocked.includes("propose_edit");
  $("#modeSelect").value = mode; $("#modeSelect").classList.toggle("readonly", readonly);
  $("#modeSelect").title = m ? `${m.label}: ${m.description}` : mode;
  $("#composerBox").classList.toggle("readonly", readonly);
  $("#input").placeholder = m && mode !== "build" ? `${m.label}: ${m.description}` : "Ask codepilot…  @ files · / skills";
}
$("#modeSelect").addEventListener("change", async () => {
  const mode = $("#modeSelect").value; setMode(mode);
  if (state.sid) await api(`/api/sessions/${state.sid}`, { method: "PATCH", body: { mode } }).catch((err) => toast(err.message, true));
});
$("#tier").addEventListener("change", () => state.sid && api(`/api/sessions/${state.sid}`, { method: "PATCH", body: { tier: $("#tier").value } }));
$("#autoApprove").addEventListener("change", () => state.sid && api(`/api/sessions/${state.sid}`, { method: "PATCH", body: { auto_approve: $("#autoApprove").checked } }));

// ---------------------------------------------------------------- composer: @ mentions, drag & drop
const input = $("#input");
function autosize() { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 220) + "px"; }
function setInput(text) { input.value = text; autosize(); input.focus(); ide.classList.remove("no-chat"); }
function insertRef(path) {
  ide.classList.remove("no-chat");
  const pos = input.selectionStart ?? input.value.length;
  const before = input.value.slice(0, pos), after = input.value.slice(pos);
  const pad = before && !/\s$/.test(before) ? " " : "";
  input.value = before + pad + "@" + path + " " + after;
  const caret = (before + pad + "@" + path + " ").length;
  input.focus(); input.setSelectionRange(caret, caret); autosize();
}
let mention = { open: false, items: [], idx: 0, start: 0 };
const fetchMentions = debounce(async (q) => {
  if (!state.sid || !state.workspace) return hideMentions();
  const d = await api(`/api/sessions/${state.sid}/find?q=${encodeURIComponent(q)}`).catch(() => ({ files: [] }));
  mention.items = d.files.slice(0, 12); mention.idx = 0; renderMentions();
}, 100);
function renderMentions() {
  if (mention.kind === "skill") return showSkillMenu(input.value.slice(1, input.selectionStart));
  const pop = $("#mentionPop");
  if (!mention.items.length) { pop.hidden = true; mention.open = false; return; }
  mention.open = true; pop.hidden = false;
  pop.innerHTML = mention.items.map((f, i) => `<div class="opt ${i === mention.idx ? "on" : ""}" data-i="${i}">${fileIcon(f)}<span>${esc(base(f))}</span><span class="dir">${esc(dirOf(f))}</span></div>`).join("");
}
function hideMentions() { mention.open = false; $("#mentionPop").hidden = true; }
function acceptMention(i) {
  const f = mention.items[i]; if (!f) return;
  const pos = input.selectionStart;
  if (mention.kind === "skill") {
    input.value = "/" + f + " " + input.value.slice(pos);
    input.setSelectionRange(f.length + 2, f.length + 2); hideMentions(); autosize(); return;
  }
  input.value = input.value.slice(0, mention.start) + "@" + f + " " + input.value.slice(pos);
  const caret = mention.start + f.length + 2; input.setSelectionRange(caret, caret); hideMentions(); autosize();
}
input.addEventListener("input", () => {
  autosize();
  const pos = input.selectionStart; const before = input.value.slice(0, pos);
  const slash = before.match(/^\/([\w.-]*)$/);
  if (slash) { showSkillMenu(slash[1]); return; }
  const m = before.match(/(^|\s)@([\w.\-/~]*)$/);
  if (m) { mention.kind = "file"; mention.start = pos - m[2].length - 1; fetchMentions(m[2]); } else hideMentions();
});
function showSkillMenu(q) {
  const builtins = [{ name: "compact", description: "Summarise the conversation so far to free context. Add a focus, e.g. /compact the API changes" }];
  const skills = [...builtins, ...(state.wsInfo?.skills || [])].filter((s) => s.name.includes(q.toLowerCase()));
  if (mention.kind !== "skill" || !mention.open) mention.idx = 0;
  mention.kind = "skill"; mention.start = 0;
  mention.idx = Math.min(mention.idx, Math.max(0, skills.length - 1));
  mention.items = skills.map((s) => s.name); mention.skills = skills;
  const pop = $("#mentionPop");
  if (!skills.length) { hideMentions(); return; }
  mention.open = true; pop.hidden = false;
  pop.innerHTML = skills.map((s, i) => `<div class="opt ${i === mention.idx ? "on" : ""}" data-i="${i}">${icon("sparkle")}<span>/${esc(s.name)}</span><span class="desc">${esc(s.description)}</span></div>`).join("");
}
input.addEventListener("keydown", (e) => {
  if (mention.open) {
    if (e.key === "ArrowDown") { e.preventDefault(); mention.idx = (mention.idx + 1) % mention.items.length; renderMentions(); return; }
    if (e.key === "ArrowUp") { e.preventDefault(); mention.idx = (mention.idx - 1 + mention.items.length) % mention.items.length; renderMentions(); return; }
    if (e.key === "Enter" || e.key === "Tab") { e.preventDefault(); acceptMention(mention.idx); return; }
    if (e.key === "Escape") { hideMentions(); return; }
  }
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); }
});
$("#mentionPop").addEventListener("mousedown", (e) => { const o = e.target.closest("[data-i]"); if (o) { e.preventDefault(); acceptMention(+o.dataset.i); } });
$("#atBtn").onclick = () => { const pos = input.selectionStart ?? input.value.length; const pad = input.value && !/\s$/.test(input.value.slice(0, pos)) ? " " : ""; input.setRangeText(pad + "@", pos, pos, "end"); input.focus(); input.dispatchEvent(new Event("input")); };
const box = $("#composerBox");
box.addEventListener("dragover", (e) => { e.preventDefault(); box.classList.add("drop"); });
box.addEventListener("dragleave", () => box.classList.remove("drop"));
box.addEventListener("drop", (e) => {
  e.preventDefault(); box.classList.remove("drop");
  const t = e.dataTransfer.getData("text/plain"); if (t && t.startsWith("@")) insertRef(t.slice(1).trim());
});

// ---------------------------------------------------------------- bottom panel: run
async function runCmd(kind) {
  if (!state.sid || !state.workspace) return toast("Open a folder first.", true);
  const command = $("#cmdInput").value.trim();
  if (kind === "command" && !command) return;
  showPanelTab("output");
  const btn = { tests: $("#runTestsBtn"), checks: $("#runChecksBtn"), command: $("#runCmdBtn") }[kind]; btn.disabled = true;
  const label = { tests: state.testCmd || "tests", checks: "analysers", command }[kind];
  $("#output").innerHTML = `<div class="out-head"><span class="spinner"></span>Running ${esc(label)}…</div>`;
  try {
    const r = await api(`/api/sessions/${state.sid}/run`, { method: "POST", body: { kind, args: $("#testArgs").value, command } });
    $("#output").innerHTML = `<div class="out-head"><span class="status ${r.ok ? "applied" : "failed"}">${r.ok ? "exit 0" : "failed"}</span><span class="muted">${r.seconds}s</span><span class="spacer"></span><button class="btn" id="askOut">${icon("sparkle")}Ask codepilot about this</button></div><pre>${esc(r.output)}</pre>`;
    $("#askOut").onclick = () => setInput(`I ran ${kind === "command" ? "`" + command + "`" : "the " + kind}. Explain any failures and propose fixes. Output:\n\n${r.output.slice(-12000)}`);
    activity("run", kind === "command" ? command.slice(0, 60) : kind, `${r.ok ? "ok" : "failed"} · ${r.seconds}s`, r.output);
    loadGit(); if (kind === "command") loadTraces();
  } catch (err) { $("#output").innerHTML = `<div class="banner error">${esc(err.message)}</div>`; }
  btn.disabled = false;
}
$("#runTestsBtn").onclick = () => runCmd("tests");
$("#runChecksBtn").onclick = () => runCmd("checks");
$("#runCmdBtn").onclick = () => runCmd("command");
$("#cmdInput").addEventListener("keydown", (e) => { if (e.key === "Enter") runCmd("command"); });

// ---------------------------------------------------------------- open-folder browser
const fd = { path: "", sel: null, resolve: null };
function browseFolder(start) {
  return new Promise((resolve) => {
    fd.resolve = resolve; fd.sel = null;
    $("#folderDialog").hidden = false;
    fdLoad(start || "");
  });
}
async function fdLoad(path) {
  try {
    const d = await api(`/api/browse?path=${encodeURIComponent(path)}&hidden=${$("#fdHidden").checked ? 1 : 0}`);
    fd.path = d.path; fd.parent = d.parent; fd.sel = null;
    $("#fdInput").value = d.path;
    const places = d.places.filter((p) => !p.recent), recent = d.places.filter((p) => p.recent);
    const placeRow = (p) => `<div class="row ${p.path === d.path ? "on" : ""}" data-fdgo="${esc(p.path)}" title="${esc(p.path)}">${icon(p.name === "Home" ? "home" : p.path.includes("CloudStorage") ? "cloud" : p.recent ? "history" : "folder")}<span class="name">${esc(p.name)}</span></div>`;
    $("#fdPlaces").innerHTML = `<div class="sec">Places</div>${places.map(placeRow).join("")}${recent.length ? `<div class="sec">Recent</div>${recent.map(placeRow).join("")}` : ""}`;
    $("#fdList").innerHTML = d.dirs.map((x) => `<div class="row" data-fdpath="${esc(x.path)}"><span class="ficon dir">${icon("folder")}</span><span class="name">${esc(x.name)}</span>${x.project ? `<span class="proj">${esc(x.project)}</span>` : ""}</div>`).join("")
      || `<div class="empty-state">No subfolders here.</div>`;
    fdHint();
  } catch (err) { $("#fdHint").textContent = err.message; }
}
function fdHint() { $("#fdHint").textContent = "Open: " + (fd.sel || fd.path); $("#fdOpen").textContent = fd.sel ? "Open selected" : "Open this folder"; }
function fdClose(value) { $("#folderDialog").hidden = true; const r = fd.resolve; fd.resolve = null; r && r(value); }
$("#fdList").addEventListener("click", (e) => {
  const row = e.target.closest("[data-fdpath]"); if (!row) return;
  $$("#fdList .row").forEach((x) => x.classList.toggle("sel", x === row)); fd.sel = row.dataset.fdpath; fdHint();
});
$("#fdList").addEventListener("dblclick", (e) => { const row = e.target.closest("[data-fdpath]"); if (row) fdLoad(row.dataset.fdpath); });
$("#fdPlaces").addEventListener("click", (e) => { const row = e.target.closest("[data-fdgo]"); if (row) fdLoad(row.dataset.fdgo); });
$("#fdUp").onclick = () => fd.parent && fdLoad(fd.parent);
$("#fdHidden").onchange = () => fdLoad(fd.path);
$("#fdInput").addEventListener("keydown", (e) => { if (e.key === "Enter") fdLoad($("#fdInput").value.trim()); if (e.key === "Escape") fdClose(null); });
$("#fdOpen").onclick = () => fdClose(fd.sel || fd.path);
$("#fdCancel").onclick = () => fdClose(null);
$("#fdClose").onclick = () => fdClose(null);
$("#folderDialog").addEventListener("mousedown", (e) => { if (e.target.id === "folderDialog") fdClose(null); });
$("#folderDialog").addEventListener("keydown", (e) => {
  if (e.target.id === "fdInput") return;
  if (e.key === "Escape") fdClose(null);
  if (e.key === "Enter") fd.sel ? fdLoad(fd.sel) : fdClose(fd.path);
  if (e.key === "Backspace" && fd.parent) fdLoad(fd.parent);
});

// ---------------------------------------------------------------- copy paths & context menu
const absPath = (rel) => (rel === "." ? state.workspace : state.workspace + "/" + rel);
async function copyText(text, label) {
  try { await navigator.clipboard.writeText(text); }
  catch {
    const ta = document.createElement("textarea"); ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
    document.body.appendChild(ta); ta.select(); document.execCommand("copy"); ta.remove();
  }
  toast(`Copied ${label || text}`);
}
function showMenu(x, y, items) {
  const m = $("#ctxMenu");
  m.innerHTML = items.map((it, i) => (it === "-" ? '<div class="sep"></div>' : `<div class="mi" data-mi="${i}">${icon(it.icon || "file")}<span>${esc(it.label)}</span>${it.kbd ? `<kbd>${esc(it.kbd)}</kbd>` : ""}</div>`)).join("");
  m.hidden = false;
  const r = m.getBoundingClientRect();
  m.style.left = Math.min(x, innerWidth - r.width - 8) + "px"; m.style.top = Math.min(y, innerHeight - r.height - 8) + "px";
  m.onclick = (e) => { const el = e.target.closest("[data-mi]"); if (!el) return; m.hidden = true; items[+el.dataset.mi].run(); };
}
document.addEventListener("mousedown", (e) => { if (!e.target.closest("#ctxMenu")) $("#ctxMenu").hidden = true; });
function pathMenu(rel, isDir) {
  const mod = isMac ? "⌘" : "Ctrl+";
  return [
    isDir ? { label: "Expand / collapse", icon: "folderOpen", run: () => { state.expanded.has(rel) ? state.expanded.delete(rel) : state.expanded.add(rel); renderTree(); } }
          : { label: "Open", icon: "file", run: () => openFile(rel) },
    { label: "Add to chat", icon: "at", run: () => insertRef(rel) },
    "-",
    { label: "Copy relative path", icon: "copy", kbd: mod + "C", run: () => copyText(rel) },
    { label: "Copy absolute path", icon: "copy", run: () => copyText(absPath(rel)) },
    { label: "Copy @reference", icon: "link", run: () => copyText("@" + rel) },
    ...(isDir ? ["-", { label: "Open as workspace folder", icon: "folderOpen", run: () => useFolder(absPath(rel)) }] : []),
  ];
}
document.addEventListener("contextmenu", (e) => {
  const el = e.target.closest("[data-file],[data-dir],[data-tab^='file:'],[data-gfile],[data-gitfile],[data-trace]");
  if (!el) return;
  e.preventDefault();
  const rel = el.dataset.file || el.dataset.dir || el.dataset.gfile || el.dataset.gitfile || el.dataset.trace || el.dataset.tab.slice(5);
  showMenu(e.clientX, e.clientY, pathMenu(rel, !!el.dataset.dir));
});

// ---------------------------------------------------------------- terminal (xterm.js <-> /api/terminal)
const termState = { term: null, fit: null, ws: null, cwd: null };
const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
function termTheme() {
  return { background: cssVar("--bg-2"), foreground: cssVar("--fg"), cursor: cssVar("--accent"), cursorAccent: cssVar("--bg-2"),
    selectionBackground: cssVar("--sel"), black: "#1d2027", red: cssVar("--err"), green: cssVar("--ok"), yellow: cssVar("--warn"),
    blue: cssVar("--accent"), magenta: cssVar("--syn-kw"), cyan: cssVar("--syn-attr"), white: cssVar("--fg-2"),
    brightBlack: cssVar("--faint"), brightWhite: cssVar("--fg") };
}
function openTerminal() {
  const token = document.querySelector('meta[name="codepilot-token"]')?.content;
  if (!token || !window.Terminal) { $("#termStatus").textContent = "Terminal is disabled (CODEPILOT_TERMINAL=0)."; return; }
  if (!termState.term) {
    termState.term = new Terminal({ fontFamily: cssVar("--mono"), fontSize: 12.5, lineHeight: 1.15, cursorBlink: true,
      theme: termTheme(), scrollback: 5000, allowProposedApi: false });
    termState.fit = new FitAddon.FitAddon();
    termState.term.loadAddon(termState.fit);
    termState.term.open($("#termHost"));
    termState.term.onData((data) => termState.ws?.readyState === 1 && termState.ws.send(JSON.stringify({ type: "input", data })));
    new ResizeObserver(() => fitTerminal()).observe($("#termHost"));
  }
  if (!termState.ws || termState.ws.readyState > 1) connectTerminal();
  fitTerminal(); termState.term.focus();
}
function fitTerminal() {
  if (!termState.term || $("#termHost").offsetParent === null) return;
  try { termState.fit.fit(); } catch { return; }
  if (termState.ws?.readyState === 1) termState.ws.send(JSON.stringify({ type: "resize", cols: termState.term.cols, rows: termState.term.rows }));
}
function connectTerminal() {
  const token = document.querySelector('meta[name="codepilot-token"]').content;
  termState.ws?.close();
  termState.cwd = tilde(state.workspace) || "~";
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/api/terminal?token=${encodeURIComponent(token)}&sid=${encodeURIComponent(state.sid || "")}`);
  termState.ws = ws;
  $("#termStatus").textContent = "Connecting…";
  ws.onopen = () => { $("#termStatus").innerHTML = `Shell in <span class="mono">${esc(termState.cwd)}</span>`; fitTerminal(); };
  ws.onmessage = (ev) => termState.term.write(ev.data);
  ws.onclose = (ev) => {
    if (termState.ws !== ws) return;
    $("#termStatus").textContent = ev.code === 1008 ? "Refused: reload the page (the server restarted)." : "Shell closed. Click New terminal.";
  };
}
$("#termNew").onclick = () => { if (termState.term) { termState.term.reset(); } connectTerminal(); termState.term?.focus(); };
$("#termSendSel").onclick = () => {
  const sel = termState.term?.getSelection();
  if (!sel) return toast("Select some terminal text first.", true);
  setInput(`${input.value ? input.value + "\n\n" : ""}Terminal output:\n\`\`\`\n${sel.trimEnd()}\n\`\`\``);
};
function onWorkspaceChangedForTerminal() {
  if (termState.ws?.readyState === 1 && termState.cwd !== (tilde(state.workspace) || "~"))
    termState.term.write(`\r\n\x1b[2m[codepilot] workspace is now ${tilde(state.workspace) || "~"}; click New terminal for a shell there]\x1b[0m\r\n`);
}

// ---------------------------------------------------------------- palette & dialog & toast
let pal = { items: [], idx: 0 };
function openPalette() {
  if (!state.sid || !state.workspace) return toast("Open a folder first.", true);
  $("#palette").hidden = false; $("#paletteInput").value = ""; $("#paletteInput").focus(); palSearch("");
}
const palSearch = debounce(async (q) => {
  const d = await api(`/api/sessions/${state.sid}/find?q=${encodeURIComponent(q)}`).catch(() => ({ files: [] }));
  pal.items = d.files; pal.idx = 0; renderPalette();
}, 80);
function renderPalette() {
  $("#paletteList").innerHTML = pal.items.map((f, i) => `<div class="opt ${i === pal.idx ? "on" : ""}" data-i="${i}">${fileIcon(f)}<span class="n">${esc(base(f))}</span><span class="dir">${esc(dirOf(f))}</span></div>`).join("") || `<div class="hint" style="padding:8px 10px">No matching files.</div>`;
  $("#paletteList .opt.on")?.scrollIntoView({ block: "nearest" });
}
function closePalette() { $("#palette").hidden = true; }
$("#paletteInput").addEventListener("input", (e) => palSearch(e.target.value));
$("#paletteInput").addEventListener("keydown", (e) => {
  if (e.key === "ArrowDown") { e.preventDefault(); pal.idx = Math.min(pal.idx + 1, pal.items.length - 1); renderPalette(); }
  else if (e.key === "ArrowUp") { e.preventDefault(); pal.idx = Math.max(pal.idx - 1, 0); renderPalette(); }
  else if (e.key === "Enter") { const f = pal.items[pal.idx]; if (f) { closePalette(); openFile(f); } }
  else if (e.key === "Escape") closePalette();
});
$("#paletteList").addEventListener("click", (e) => { const o = e.target.closest("[data-i]"); if (o) { closePalette(); openFile(pal.items[+o.dataset.i]); } });
$("#palette").addEventListener("mousedown", (e) => { if (e.target.id === "palette") closePalette(); });
$("#paletteBtn").onclick = openPalette;

function promptDialog(title, value, hint) {
  return new Promise((resolve) => {
    $("#dialogTitle").textContent = title; $("#dialogInput").value = value || ""; $("#dialogHint").textContent = hint || "";
    $("#dialog").hidden = false; $("#dialogInput").focus(); $("#dialogInput").select();
    const done = (v) => { $("#dialog").hidden = true; $("#dialogOk").onclick = $("#dialogCancel").onclick = $("#dialogInput").onkeydown = null; resolve(v); };
    $("#dialogOk").onclick = () => done($("#dialogInput").value.trim());
    $("#dialogCancel").onclick = () => done(null);
    $("#dialogInput").onkeydown = (e) => { if (e.key === "Enter") done($("#dialogInput").value.trim()); if (e.key === "Escape") done(null); };
  });
}
function toast(msg, isErr) {
  const el = document.createElement("div");
  el.textContent = msg;
  el.style.cssText = `position:fixed;bottom:36px;left:50%;transform:translateX(-50%);z-index:60;padding:7px 14px;border-radius:8px;font-size:12.5px;box-shadow:var(--shadow);background:var(--bg-4);border:1px solid var(--line-2);color:${isErr ? "var(--err)" : "var(--fg)"}`;
  document.body.appendChild(el); setTimeout(() => el.remove(), 2600);
}

// ---------------------------------------------------------------- keyboard
document.addEventListener("keydown", (e) => {
  const mod = isMac ? e.metaKey : e.ctrlKey;
  if (mod && e.key.toLowerCase() === "p") { e.preventDefault(); openPalette(); }
  else if (mod && e.key.toLowerCase() === "b") { e.preventDefault(); toggle("no-sidebar"); }
  else if (mod && e.key.toLowerCase() === "j") { e.preventDefault(); toggle("no-panel"); }
  else if (mod && e.key.toLowerCase() === "l") { e.preventDefault(); ide.classList.remove("no-chat"); input.focus(); }
  else if (e.altKey && e.code === "KeyW") { e.preventDefault(); if (state.active) closeTab(state.active); }
  else if (e.ctrlKey && e.key === "`") { e.preventDefault(); const on = !$(".panel-body[data-ptab=terminal]").hidden && !ide.classList.contains("no-panel"); if (on) toggle("no-panel"); else showPanelTab("terminal"); }
  else if (mod && e.key.toLowerCase() === "c" && state.picked && !String(getSelection()) && !e.target.closest("input,textarea")) { e.preventDefault(); copyText(state.picked); }
  else if (e.key === "Escape") { closePalette(); hideMentions(); $("#ctxMenu").hidden = true; }
});

init().catch((err) => { document.body.insertAdjacentHTML("afterbegin", `<div class="banner error" style="position:fixed;top:44px;left:60px;z-index:99">${esc(err.message)}</div>`); });
