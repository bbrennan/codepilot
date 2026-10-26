"use strict";
/* codepilot IDE front end. No build step: plain DOM + fetch. */

// ---------------------------------------------------------------- utilities
const $ = (s, el = document) => el.querySelector(s);
// Page errors, kept for problem reports (Help → Report a problem).
const pageErrors = [];
const notePageError = (msg) => { pageErrors.push(`${new Date().toISOString().slice(11, 19)} ${String(msg).slice(0, 500)}`); if (pageErrors.length > 50) pageErrors.shift(); };
window.addEventListener("error", (e) => notePageError(`${e.message} (${(e.filename || "").split("/").pop()}:${e.lineno})`));
window.addEventListener("unhandledrejection", (e) => notePageError(`unhandled: ${e.reason?.message || e.reason}`));
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const H = { "Content-Type": "application/json", "X-Codepilot": "1" };
const isMac = /Mac|iPhone|iPad/.test(navigator.platform);
function store(key, val) { try { if (val === undefined) return localStorage.getItem(key); localStorage.setItem(key, val); } catch { return null; } return null; }
async function api(path, opts = {}) {
  const res = await fetch(path, { headers: H, ...opts, body: opts.body ? JSON.stringify(opts.body) : undefined });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) { const e = new Error(data.error || res.statusText); e.status = res.status; throw e; }
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
  compass: '<circle cx="12" cy="12" r="10"/><path d="m16.24 7.76-1.8 5.4a2 2 0 0 1-1.28 1.28l-5.4 1.8 1.8-5.4a2 2 0 0 1 1.28-1.28z"/>',
  image: '<rect width="18" height="18" x="3" y="3" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.09-3.09a2 2 0 0 0-2.82 0L6 21"/>',
  help: '<circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><path d="M12 17h.01"/>',
  filePlus: '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M9 15h6"/><path d="M12 18v-6"/>',
  folderPlus: '<path d="M12 10v6"/><path d="M9 13h6"/><path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>',
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
  cfg: null, sid: null, session: null, workspace: "", streams: new Set(), streamEnds: new Map(), proposals: new Map(), toolEls: new Map(),
  tabs: [], active: null, tree: new Map(), expanded: new Set(), activity: 0, context: null, testCmd: "", traceFiles: [],
  msgText: new Map(), // message id -> the text the user sent (for edit and retry)
  attachments: [], // images waiting to be sent with the next message
};

// ---------------------------------------------------------------- layout
const ide = $("#ide");
function setView(view, reveal = true) {
  $$("#activitybar button").forEach((b) => b.classList.toggle("on", b.dataset.view === view));
  $$(".sidebar .view").forEach((v) => v.classList.toggle("on", v.dataset.view === view));
  if (reveal) { ide.classList.remove("no-sidebar"); store("cp-no-sidebar", "0"); }
  store("cp-view", view);
  if (view === "traces") loadTraces();
  if (view === "changes") { renderProposalList(); loadGit(); }
  if (view === "memory") renderMemory();
  if (view === "steering") loadSteering();
  if (view === "specs") loadSpecs();
  if (view === "search") $("#grepInput").focus();
}
$("#activitybar").addEventListener("click", (e) => {
  const b = e.target.closest("button"); if (!b) return;
  if (b.classList.contains("on") && !ide.classList.contains("no-sidebar")) { ide.classList.add("no-sidebar"); store("cp-no-sidebar", "1"); return; }
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
  for (const v of terms.views.values()) v.xterm.options.theme = termTheme();
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
  ide.classList.remove("no-panel"); store("cp-no-panel", "0");
  store("cp-ptab", name);
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
  showStaleBanner(c);
  $("#sbProvider").innerHTML = `${icon("server")}${c.provider === "bedrock" ? `bedrock · ${esc(c.region)}${c.profile ? " · " + esc(c.profile) : ""}` : `${esc(c.provider)} · ${esc(shortModel(c.models.main) || "no model set")}`}`;
  $("#sbProvider").classList.add(c.provider === "ollama" ? "warn" : "ok");
  renderModelSelect();
  loadModels(false);
  if (c.eval_cmd) $("#cmdInput").value = c.eval_cmd;
  renderQuick();
  api("/api/github").then((g) => {
    $("#sbGithub").innerHTML = g.available ? `${icon("branch")}github: ${esc(g.user)}${g.host !== "github.com" ? " @ " + esc(g.host) : ""}` : `<span title="${esc(g.reason || "")}">${icon("alert")}github off</span>`;
    $("#sbGithub").className = "sb-item " + (g.available ? "" : "warn");
  }).catch(() => {});
  setView(store("cp-view") || "explorer", false); // keep a hidden sidebar hidden
  const list = await loadSessions();
  const last = store("cp-session");
  if (last && list.some((s) => s.id === last)) await openSession(last);
  else if (list.length) await openSession(list[0].id);
  else { renderChatEmpty(); renderEditor(); renderTree(); }
  setInterval(pollSessions, 4000);
  await loadTerminals();
  const ptab = store("cp-ptab");
  if (!ide.classList.contains("no-panel") && ptab && (ptab !== "terminal" || terms.list.length)) showPanelTab(ptab);
}
// The server keeps running the code it started with; after an update (git pull), offer to restart it.
function showStaleBanner(c) {
  if (c && !("version" in c) && !$("#staleBanner")) { // a server from before version tracking: can't restart itself
    document.body.insertAdjacentHTML("afterbegin", `<div class="stale-banner" id="staleBanner">${icon("refresh")}<span>The codepilot server running now is older than this page, so newer features (like queued messages) won't work. Stop it and run <span class="mono">make start</span> again (or press Ctrl+C where <span class="mono">make serve</span> runs, then start it).</span></div>`);
    return;
  }
  if (!c?.stale || $("#staleBanner")) return;
  document.body.insertAdjacentHTML("afterbegin", `<div class="stale-banner" id="staleBanner">${icon("refresh")}<span>codepilot was updated, but the running server still has the old code.</span><button class="btn sm primary" id="staleRestart">Restart now</button><span class="muted">(or run <span class="mono">codepilot restart</span>)</span></div>`);
  $("#staleRestart").onclick = restartServer;
}
async function restartServer() {
  if (state.streams.size && !confirm("codepilot is working. Restart anyway? The current turn stops.")) return;
  const btn = $("#staleRestart"); if (btn) { btn.disabled = true; btn.textContent = "Restarting…"; }
  await api("/api/restart", { method: "POST" }).catch(() => null);
  for (let i = 0; i < 60; i++) { // wait for the new server, then load the new page code
    await new Promise((r) => setTimeout(r, 500));
    const c = await fetch("/api/config", { cache: "no-store" }).then((r) => r.json()).catch(() => null);
    if (c && !c.stale) { location.reload(); return; }
  }
  toast("The server didn't come back. Run codepilot restart in a terminal.", true);
}
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) fetch("/api/config", { cache: "no-store" }).then((r) => r.json()).then(showStaleBanner).catch(() => {});
});
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
  const list = await loadSessions();
  followIfRunning(state.sid, list.find((s) => s.id === state.sid)?.busy);
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
  // One at a time: a message sent while a new session is still opening goes to that session, not a second one.
  if (state.creatingSession) return state.creatingSession;
  state.creatingSession = (async () => {
    const s = await api("/api/sessions", { method: "POST", body: { repo: repo ?? state.workspace ?? "", tier: selectedTier(), auto_approve: $("#autoApprove").checked } });
    await openSession(s.id); $("#input").focus();
    return s;
  })().finally(() => { state.creatingSession = null; });
  return state.creatingSession;
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
  syncModelSelect(); $("#autoApprove").checked = data.session.auto_approve; $("#autoApply").checked = !!data.auto_apply;
  state.mode = data.session.mode || "build";
  $("#transcript").innerHTML = ""; state.toolEls.clear(); endText();
  state.proposals = new Map(data.proposals.map((p) => [p.id, p]));
  state.prompts = data.events.filter((ev) => ev.type === "user").map((ev) => ev.text); resetHistory();
  state.workspace = data.session.repo || "";
  if (!data.events.length) renderChatEmpty();
  for (const ev of data.events) render(ev, true);
  // Changes are redrawn where they were proposed (proposal_ref); anything still waiting that wasn't goes last.
  for (const p of data.proposals) if (p.status === "pending" && !$(`#transcript [data-prop="${p.id}"]`)) renderProposalCard(p);
  state.approval = null; state.allow = data.allow || [];
  if (data.pending) render({ type: "approval_needed", tools: data.pending }, true);
  renderReviewBar();
  renderPlan(null); for (const ev of data.events) if (ev.type === "plan") renderPlan(ev.items);
  updateBusy();
  setContext(data.context); renderUsage(data.usage); state.summary = data.summary;
  setWorkspace(data.session.repo, prevWorkspace !== (data.session.repo || ""));
  renderProposalList(); loadSessions(); scrollEnd(true);
  loadSteering(true);
  followIfRunning(sid, data.busy);
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
        rows.push(`<div class="row ${state.picked === e.path ? "picked" : ""}${e.dim ? " dim" : ""}" style="--depth:${depth}" data-dir="${esc(e.path)}" draggable="true"><span class="caret ${open ? "open" : ""}">${icon("chevron")}</span><span class="ficon dir">${icon(open ? "folderOpen" : "folder")}</span><span class="name">${esc(e.name)}</span><button class="icon-btn sm hover-act" data-at="${esc(e.path)}" title="Reference in chat">${icon("at")}</button></div>`);
        if (open) await walk(e.path, depth + 1);
      } else {
        const on = state.active === "file:" + e.path ? "on" : "";
        rows.push(`<div class="row ${on} ${state.picked === e.path ? "picked" : ""}" style="--depth:${depth}" data-file="${esc(e.path)}" draggable="true"><span class="caret"></span>${fileIcon(e.path)}<span class="name">${esc(e.name)}</span><button class="icon-btn sm hover-act" data-at="${esc(e.path)}" title="Reference in chat">${icon("at")}</button></div>`);
      }
    }
  };
  await walk(".", 0);
  el.innerHTML = rows.join("") || `<div class="empty-state">Empty folder.</div>`;
}
$("#tree").addEventListener("click", (e) => {
  const picked = e.target.closest("[data-file],[data-dir]");
  if (picked) { state.picked = picked.dataset.file || picked.dataset.dir; state.pickedDir = !!picked.dataset.dir; $$("#tree .row").forEach((r) => r.classList.toggle("picked", r === picked)); }
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
  // The Traces view only appears when this folder has trace or log folders (traces/, logs/, results/...).
  const hasTraces = !!(w?.trace_roots || []).length;
  $("#activitybar [data-view=traces]").hidden = !hasTraces;
  if (!hasTraces && $(".view.on")?.dataset.view === "traces") setView("explorer", false);
  if ($(".view.on")?.dataset.view === "memory") renderMemory();
}

// ---------------------------------------------------------------- editor tabs
function openTab(tab) {
  const existing = state.tabs.find((t) => t.id === tab.id);
  if (existing) Object.assign(existing, tab); else state.tabs.push(tab);
  state.active = tab.id; renderEditor();
}
async function closeTab(id) {
  const i = state.tabs.findIndex((t) => t.id === id); if (i < 0) return;
  const t = state.tabs[i];
  if (t.dirty && !(await confirmDialog(`Discard changes to ${t.title}?`, "Your unsaved edits will be lost.", "Discard"))) return;
  state.tabs.splice(i, 1);
  if (state.active === id) state.active = state.tabs[Math.min(i, state.tabs.length - 1)]?.id || null;
  renderEditor();
}
function renderTabs() {
  $("#editorTabs").innerHTML = state.tabs.map((t) => `<div class="tab ${t.id === state.active ? "on" : ""} ${t.dirty ? "dirty" : ""}" data-tab="${esc(t.id)}" title="${esc((t.tip || t.title) + (t.dirty ? " (unsaved)" : ""))}">
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
  else if (tab.kind === "review") renderReviewTab(tab);
  else if (tab.kind === "image") renderImageTab(tab);
  else if (tab.kind === "spec") renderSpecTab(tab);
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
  if (/\.(png|jpe?g|gif|webp|svg|ico|bmp|avif)$/i.test(path)) { // images: show the image, not its bytes
    openTab({ id, kind: "image", path, title: base(path), tip: path });
    return;
  }
  try {
    const d = await api(`/api/sessions/${state.sid}/files?path=${encodeURIComponent(path)}`);
    if (d.entries) { state.expanded.add(path); setView("explorer"); renderTree(); return; }
    openTab({ id, kind: "file", path: d.path, title: base(d.path), tip: d.path, content: d.content, mtime: d.mtime, flash: line || null, sel: null });
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
  if (tab.editing) return renderEditTab(tab);
  if (isMarkdown(tab.path) && tab.view !== "source") return renderDocTab(tab);
  const lines = tab.content.split("\n");
  if (lines.length > 1 && lines[lines.length - 1] === "") lines.pop();
  const sel = tab.sel;
  const selLabel = sel ? (sel.a === sel.b ? `line ${sel.a}` : `lines ${sel.a}–${sel.b}`) : "";
  const parts = tab.path.split("/");
  $("#editor").innerHTML = `<div class="ed-bar"><span class="crumbs">${parts.slice(0, -1).map(esc).join(" › ")}${parts.length > 1 ? " › " : ""}<b>${esc(parts.at(-1))}</b></span>
      <span class="spacer"></span><span class="muted">${selLabel ? selLabel.replace("lines", "L").replace("line", "L") : lines.length + " lines"}</span>
      <button class="btn" id="fAdd" title="Reference in chat">${icon("at")}${sel ? "Add lines" : "Add to chat"}</button>
      <button class="btn" id="fAsk">${icon("sparkle")}Ask</button>
      ${isMarkdown(tab.path) ? viewSwitch("source") : ""}
      ${tab.readonly ? `<span class="muted" title="Edit it in its own tool's folder">read-only</span>` : `<button class="btn" id="fEdit" title="Edit this file">${icon("edit")}Edit</button>`}
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
  $("#fEdit") && ($("#fEdit").onclick = () => editFile(tab.id));
  bindViewSwitch(tab);
  if (tab.global || tab.readonly) { $("#fAdd").remove(); $("#fAsk").remove(); } // outside the workspace: @ can't reach it
  if (tab.global) $("#fReload").onclick = () => openGlobalSteering(tab.global, true);
}

// ---------------------------------------------------------------- Markdown documents (preview)
// marked renders GitHub-flavoured Markdown; DOMPurify removes scripts, event handlers, styles and forms, so a
// document can never run code in this page (which holds the terminal token). Mermaid loads only when needed.
const isMarkdown = (p) => /\.(md|markdown|mdx|mdown)$/i.test(p || "");
const docParser = window.marked ? new marked.Marked({ gfm: true, breaks: false }) : null;
const slugify = (t) => t.toLowerCase().trim().replace(/[^\w\- ]+/g, "").replace(/\s+/g, "-");
function resolveDocPath(baseDir, href) {
  let ref = decodeURIComponent(href.split("#")[0].split("?")[0]);
  const parts = ref.startsWith("/") ? [] : (baseDir ? baseDir.split("/") : []);
  for (const seg of ref.replace(/^\//, "").split("/")) {
    if (seg === "..") parts.pop(); else if (seg && seg !== ".") parts.push(seg);
  }
  return parts.join("/");
}
function renderDoc(src, baseDir) {
  const text = String(src ?? "");
  const fm = text.match(/^---\r?\n([\s\S]*?)\r?\n---[ \t]*(?:\r?\n|$)/);
  const body = fm ? text.slice(fm[0].length) : text;
  if (!docParser || !window.DOMPurify) return md(body); // vendor scripts missing: basic rendering
  const html = DOMPurify.sanitize(docParser.parse(body), { FORBID_TAGS: ["style", "form", "button", "textarea", "select"], FORBID_ATTR: ["style"] });
  const wrap = document.createElement("div");
  wrap.innerHTML = html;
  const seen = new Map();
  wrap.querySelectorAll("h1,h2,h3,h4,h5,h6").forEach((h) => {
    const id = slugify(h.textContent) || "section", n = seen.get(id) || 0; seen.set(id, n + 1);
    h.id = "doc-" + (n ? `${id}-${n}` : id);
  });
  wrap.querySelectorAll("a[href]").forEach((a) => {
    const href = a.getAttribute("href");
    if (/^(https?:|mailto:)/i.test(href)) { a.target = "_blank"; a.rel = "noopener noreferrer"; a.title = href; return; }
    if (href.startsWith("#")) { a.dataset.anchor = "doc-" + slugify(decodeURIComponent(href.slice(1))); a.setAttribute("href", "#"); return; }
    a.dataset.docPath = resolveDocPath(baseDir, href); a.setAttribute("href", "#"); a.title = a.dataset.docPath;
  });
  wrap.querySelectorAll("img[src]").forEach((img) => {
    const src = img.getAttribute("src"); img.loading = "lazy";
    if (!/^(https?:|data:image\/)/i.test(src) && state.sid) img.setAttribute("src", `/api/sessions/${state.sid}/raw?path=${encodeURIComponent(resolveDocPath(baseDir, src))}`);
  });
  wrap.querySelectorAll("pre > code").forEach((code) => {
    const lang = (code.className.match(/language-([\w+-]+)/) || [])[1];
    if (lang === "mermaid") { const div = document.createElement("div"); div.className = "mermaid-block"; div.dataset.src = code.textContent; code.parentElement.replaceWith(div); return; }
    if (window.hljs && lang && hljs.getLanguage(lang)) { try { code.innerHTML = hljs.highlight(code.textContent, { language: lang, ignoreIllegals: true }).value; } catch { /* plain */ } }
  });
  if (fm) wrap.insertAdjacentHTML("afterbegin", `<div class="front-matter"><span>front matter</span><pre>${esc(fm[1])}</pre></div>`);
  return wrap.innerHTML;
}
let mermaidReady = null;
function loadScript(src) { return new Promise((res, rej) => { const el = document.createElement("script"); el.src = src; el.onload = res; el.onerror = () => rej(new Error(`couldn't load ${src}`)); document.head.appendChild(el); }); }
async function renderMermaid(root) {
  const blocks = root ? [...root.querySelectorAll(".mermaid-block:not([data-done])")] : [];
  if (!blocks.length) return;
  try {
    mermaidReady ||= loadScript("/static/vendor/mermaid.min.js");
    await mermaidReady;
    const dark = (document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")) === "dark";
    mermaid.initialize({ startOnLoad: false, securityLevel: "strict", theme: dark ? "dark" : "default" });
  } catch (err) { blocks.forEach((b) => { b.innerHTML = `<pre>${esc(b.dataset.src)}</pre>`; }); return; }
  for (const b of blocks) {
    b.dataset.done = "1";
    try { const { svg } = await mermaid.render("mmd-" + Math.random().toString(36).slice(2), b.dataset.src); b.innerHTML = svg; }
    catch (err) { b.innerHTML = `<div class="mermaid-error">Diagram error: ${esc(String(err.message || err).split("\n")[0])}</div><pre>${esc(b.dataset.src)}</pre>`; }
  }
}
function viewSwitch(current) {
  return `<span class="seg" role="group" aria-label="View"><button class="${current === "preview" ? "on" : ""}" data-view-mode="preview">Preview</button><button class="${current === "source" ? "on" : ""}" data-view-mode="source">Source</button></span>`;
}
function bindViewSwitch(tab) {
  $$("#editor [data-view-mode]").forEach((b) => (b.onclick = () => { tab.view = b.dataset.viewMode; renderEditor(); }));
}
function renderDocTab(tab) {
  const parts = tab.path.split("/");
  $("#editor").innerHTML = `<div class="ed-bar"><span class="crumbs">${parts.slice(0, -1).map(esc).join(" › ")}${parts.length > 1 ? " › " : ""}<b>${esc(parts.at(-1))}</b></span>
      <span class="spacer"></span>${viewSwitch("preview")}
      ${tab.readonly ? `<span class="muted">read-only</span>` : `<button class="btn" id="fEdit" title="Edit this file">${icon("edit")}Edit</button>`}
      ${tab.global || tab.readonly ? "" : `<button class="btn" id="fAdd" title="Reference in chat">${icon("at")}Add to chat</button>`}
      <button class="btn ghost" id="fReload" title="Reload from disk">${icon("refresh")}</button></div>
    <div class="ed-scroll doc-scroll" id="edScroll"><article class="md-doc" id="docBody">${renderDoc(tab.content, dirOf(tab.path))}</article></div>`;
  bindViewSwitch(tab);
  $("#fEdit") && ($("#fEdit").onclick = () => editFile(tab.id));
  $("#fAdd") && ($("#fAdd").onclick = () => insertRef(tab.path));
  $("#fReload").onclick = async () => { if (tab.global) return openGlobalSteering(tab.global, true); tab.content = null; const id = tab.id; await openFile(tab.path); state.active = id; };
  if (tab.scroll) $("#edScroll").scrollTop = tab.scroll;
  $("#edScroll").onscroll = (e) => { tab.scroll = e.target.scrollTop; };
  renderMermaid($("#docBody"));
}
function renderImageTab(tab) {
  const url = `/api/sessions/${state.sid}/raw?path=${encodeURIComponent(tab.path)}`;
  $("#editor").innerHTML = `<div class="ed-bar"><span class="crumbs"><b>${esc(tab.path)}</b></span><span class="spacer"></span><span class="muted" id="imgSize"></span>
      <button class="btn" id="fAdd" title="Attach to your next message">${icon("at")}Add to chat</button></div>
    <div class="ed-scroll img-view"><img src="${esc(url)}" alt="${esc(tab.path)}" id="imgView"></div>`;
  $("#imgView").onload = (e) => { $("#imgSize").textContent = `${e.target.naturalWidth} × ${e.target.naturalHeight}`; };
  $("#imgView").onerror = () => { $("#imgSize").textContent = "can't be shown"; };
  $("#fAdd").onclick = () => insertRef(tab.path);
}
// links inside rendered documents (preview, spec tab)
$("#editor").addEventListener("click", (e) => {
  const a = e.target.closest("a[data-doc-path], a[data-anchor]"); if (!a) return;
  e.preventDefault();
  if (a.dataset.anchor) { document.getElementById(a.dataset.anchor)?.scrollIntoView({ behavior: "smooth", block: "start" }); return; }
  const [path, hash] = [a.dataset.docPath, (a.getAttribute("data-hash") || "")];
  if (state.workspace) openFile(path).then(() => hash && document.getElementById(hash)?.scrollIntoView());
});

// edit mode: a plain-text editor with Save (⌘S), dirty tracking and a check for changes made on disk
function editFile(id) {
  const t = state.tabs.find((x) => x.id === id); if (!t || t.content == null) return;
  t.editing = true; if (t.draft == null) t.draft = t.content;
  state.active = id; renderEditor();
}
function indentUnit(text) { return /^\t/m.test(text) ? "\t" : "    "; }
function setDirty(tab) {
  const dirty = tab.draft != null && tab.draft !== tab.content;
  if (dirty !== !!tab.dirty) { tab.dirty = dirty; renderTabs(); }
  const st = $("#edState"); if (st) st.textContent = dirty ? "Unsaved changes" : "Saved";
}
function renderEditTab(tab) {
  const parts = tab.path.split("/");
  const mod = isMac ? "⌘" : "Ctrl+";
  $("#editor").innerHTML = `<div class="ed-bar"><span class="crumbs">${parts.slice(0, -1).map(esc).join(" › ")}${parts.length > 1 ? " › " : ""}<b>${esc(parts.at(-1))}</b></span>
      <span class="spacer"></span><span class="muted" id="edState">${tab.dirty ? "Unsaved changes" : "Editing"}</span>
      ${isMarkdown(tab.path) ? `<button class="btn" id="fEditPreview" title="See the draft rendered">${icon(tab.editPreview ? "edit" : "eye")}${tab.editPreview ? "Back to editing" : "Preview"}</button>` : ""}
      <button class="btn primary" id="fSave" title="Save (${mod}S)">${icon("check")}Save</button>
      <button class="btn" id="fDone" title="Back to the highlighted view">Done</button></div>
    ${tab.editPreview ? `<div class="ed-scroll doc-scroll"><article class="md-doc" id="docBody">${renderDoc(tab.draft ?? tab.content, dirOf(tab.path))}</article></div>` : `<textarea class="code-edit" id="codeEdit" spellcheck="false" autocapitalize="off" autocomplete="off" wrap="off" aria-label="Edit ${esc(tab.path)}"></textarea>`}`;
  $("#fEditPreview") && ($("#fEditPreview").onclick = () => { tab.editPreview = !tab.editPreview; renderEditor(); });
  $("#fSave").onclick = () => saveFile(tab);
  if (tab.editPreview) { renderMermaid($("#docBody")); $("#fDone").onclick = () => { tab.editPreview = false; renderEditor(); }; return; }
  const ta = $("#codeEdit");
  ta.value = tab.draft ?? tab.content;
  const caret = Math.min(tab.caret ?? 0, ta.value.length);
  ta.focus(); ta.setSelectionRange(caret, caret);
  if (tab.scroll) ta.scrollTop = tab.scroll;
  ta.oninput = () => { tab.draft = ta.value; setDirty(tab); };
  ta.onblur = () => { tab.caret = ta.selectionStart; tab.scroll = ta.scrollTop; };
  ta.onkeydown = (e) => {
    if (e.key === "Tab" && !e.shiftKey && !e.metaKey && !e.ctrlKey) {
      e.preventDefault(); ta.setRangeText(indentUnit(tab.content), ta.selectionStart, ta.selectionEnd, "end"); ta.oninput();
    }
  };
  $("#fSave").onclick = () => saveFile(tab);
  $("#fDone").onclick = async () => {
    if (tab.dirty && !(await confirmDialog(`Discard changes to ${tab.title}?`, "Save first to keep them.", "Discard"))) return;
    tab.editing = false; tab.draft = null; tab.dirty = false; renderEditor();
  };
}
async function saveFile(tab, force = false) {
  if (!tab || tab.draft == null) return;
  try {
    const d = tab.global
      ? await api("/api/steering/global", { method: "PUT", body: { name: tab.global, content: tab.draft, base_mtime: tab.mtime, force } })
      : await fsApi({ op: "save", path: tab.path, content: tab.draft, base_mtime: tab.mtime, force });
    tab.content = tab.draft; tab.mtime = d.mtime; setDirty(tab);
    toast(`Saved ${tab.path}`); loadGit();
    if (tab.global || tab.path.startsWith(".codepilot/steering/")) loadSteering();
  } catch (err) {
    if (/changed on disk/.test(err.message) && await confirmDialog(`${tab.title} changed on disk`,
      "It was changed after you opened it (by you elsewhere, a tool, or an applied proposal). Overwrite it with your version?", "Overwrite")) return saveFile(tab, true);
    toast(err.message, true);
  }
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
function openProposal(id) { openReview(+id); }
function renderDiffTab(tab) {
  const p = state.proposals.get(tab.pid);
  if (!p) { $("#editor").innerHTML = `<div class="empty-state">Proposal not found.</div>`; return; }
  $("#editor").innerHTML = `<div class="ed-bar"><span class="crumbs"><b>${esc(p.path)}</b></span><span class="status ${p.status}">${p.status}</span><span class="muted">${esc(p.reason || "")}</span><span class="spacer"></span>
      ${propActions(p)}
      <button class="btn ghost" id="dOpen">${icon("file")}Open file</button></div>
    <div class="ed-scroll">${diffHtml(p.diff)}</div>`;
  $("#dOpen").onclick = () => openFile(p.path);
}
// ---------------------------------------------------------------- review: the bar above the composer and the Review tab
function renderReviewBar() {
  const bar = $("#reviewBar"); if (!bar) return;
  const pend = [...state.proposals.values()].filter((p) => p.status === "pending");
  const ap = state.approval;
  const mod = isMac ? "⌘" : "Ctrl+";
  let html = "";
  if (ap) {
    const rule = ap.tools.length === 1 ? ap.tools[0].allow : null;
    html += `<div class="rb-row rb-approval">${icon("alert")}<div class="rb-main"><b>Run ${ap.tools.length > 1 ? "these" : "this"}?</b>${ap.tools.map((t) => `<code class="rb-cmd">${esc(t.command)}</code>`).join("")}
      ${rule ? `<label class="toggle rb-allow" title="Run commands starting with this without asking, for the rest of this session. Commands that chain or redirect (;, &&, |, >) always ask."><input type="checkbox" id="rbAllow"><span>always allow <code>${esc(rule.prefix)}</code> in this session</span></label>` : ""}</div>
      <div class="rb-acts"><button class="btn primary" id="rbApprove" title="${mod}Enter">${icon("check")}Run <kbd>${mod}⏎</kbd></button><button class="btn" id="rbDeny">Deny</button></div></div>`;
  }
  if (pend.length) {
    const tot = pend.reduce((acc, p) => { const st = diffStat(p.diff); acc.a += st.a; acc.d += st.d; return acc; }, { a: 0, d: 0 });
    const files = [...new Set(pend.map((p) => base(p.path)))];
    html += `<div class="rb-row rb-changes">${icon("diff")}<div class="rb-main"><b>${pend.length} change${pend.length > 1 ? "s" : ""} to review</b> <span class="dstat"><span class="a">+${tot.a}</span> <span class="d">−${tot.d}</span></span><span class="rb-files muted">${esc(files.slice(0, 4).join(", "))}${files.length > 4 ? ` +${files.length - 4} more` : ""}</span></div>
      <div class="rb-acts"><button class="btn" id="rbReview">Review</button><button class="btn primary" id="rbApplyAll">Apply all</button><button class="btn ghost" id="rbRejectAll">Reject all</button></div></div>`;
  }
  bar.innerHTML = html; bar.hidden = !html;
  if (ap) { $("#rbApprove").onclick = () => decideApproval(true); $("#rbDeny").onclick = () => decideApproval(false); }
  if (pend.length) {
    $("#rbReview").onclick = () => openReview(pend[0].id);
    $("#rbApplyAll").onclick = () => bulkProposals("apply");
    $("#rbRejectAll").onclick = () => bulkProposals("reject");
  }
}
// When you've decided every change codepilot was waiting on (and applied at least one), it carries on by itself.
const REVIEW_DONE = "I've reviewed your proposed changes (the outcome of each is above). Continue: verify what was applied, for example by running the relevant tests, then carry on with the task. If nothing is left to do, say so briefly.";
function maybeResumeAfterReview() {
  const sid = state.sid;
  if (!sid || state.awaitingReview !== sid || state.streams.has(sid) || state.approval) return;
  const props = [...state.proposals.values()];
  if (props.some((p) => p.status === "pending")) return;
  state.awaitingReview = null;
  if (!props.some((p) => p.status === "applied" && state.reviewBatch?.has(p.id))) return; // all rejected: wait for you
  add(`<div class="wait-row approved">${icon("refresh")}<span>Continuing after your review…</span></div>`);
  streamTo(sid, `/api/sessions/${sid}/chat`, { message: REVIEW_DONE, tier: selectedTier() });
}
function decideApproval(approve) {
  if (!state.approval || !state.sid) return;
  const remember = approve && !!$("#rbAllow")?.checked;
  const tools = state.approval.tools;
  state.approval = null; renderReviewBar();
  const row = $("#transcript .wait-row.waiting");
  if (row) { row.classList.remove("waiting"); row.classList.add(approve ? "approved" : "denied"); row.innerHTML = `${icon(approve ? "check" : "x")}<span>${approve ? "Approved" : "Denied"}: ${tools.map((t) => `<code>${esc(t.command)}</code>`).join(", ")}${remember ? ` · always allowed <code>${esc(tools[0].allow.prefix)}</code> this session` : ""}</span>`; }
  streamTo(state.sid, `/api/sessions/${state.sid}/approve`, { approve, remember });
}
async function proposalAction(p, action) {
  try {
    const r = await api(`/api/proposals/${p.id}/${action}`, { method: "POST" }); state.proposals.set(r.id, r);
    for (const o of r.outdated || []) { state.proposals.set(o.id, o); refreshProposalViews(o.id); }
    if (action === "apply" && r.checks) activity("error", "checks", r.path, r.checks);
    return true;
  } catch (err) { toast(`#${p.id} ${p.path}: ${err.message}`, true); if (action === "apply") p.status = "failed"; return false; }
}
async function bulkProposals(action) {
  const pend = [...state.proposals.values()].filter((p) => p.status === "pending");
  let ok = 0;
  for (const p of pend) { if (await proposalAction(p, action)) ok++; refreshProposalViews(p.id); }
  toast(`${action === "apply" ? "Applied" : "Rejected"} ${ok} of ${pend.length} change${pend.length > 1 ? "s" : ""}`);
  loadGit(); reloadOpenFiles(pend);
}
function reloadOpenFiles(props) {
  for (const p of props) { const tab = state.tabs.find((t) => t.id === "file:" + p.path); if (tab && !tab.dirty) { tab.content = null; if (state.active === tab.id) openFile(tab.path); } }
}
function openReview(pid) {
  const existing = state.tabs.find((t) => t.id === "review");
  if (existing) { if (pid) existing.sel = pid; state.active = "review"; renderEditor(); return; }
  openTab({ id: "review", kind: "review", icon: "diff", title: "Review changes", sel: pid || null });
}
function reviewList() {
  const all = [...state.proposals.values()];
  return [...all.filter((p) => p.status === "pending"), ...all.filter((p) => p.status !== "pending").reverse()];
}
function renderReviewTab(tab) {
  const list = reviewList();
  if (!list.length) { $("#editor").innerHTML = `<div class="empty-state">No changes in this session yet. Changes codepilot proposes appear here for review.</div>`; return; }
  if (!list.some((p) => p.id === tab.sel)) tab.sel = list[0].id;
  const p = state.proposals.get(tab.sel);
  const pendN = list.filter((x) => x.status === "pending").length;
  $("#editor").innerHTML = `<div class="review">
    <div class="rv-list"><div class="rv-head">${pendN ? `${pendN} waiting` : "All reviewed"}<span class="spacer"></span>${pendN ? `<button class="btn sm primary" id="rvApplyAll">Apply all</button>` : ""}</div>
      ${list.map((x) => `<div class="rv-item ${x.id === p.id ? "on" : ""}" data-rv="${x.id}">${fileIcon(x.path)}<div class="rv-name"><span>${esc(base(x.path))}</span><span class="muted">${esc(dirOf(x.path))}</span></div>${diffStat(x.diff).html}<span class="status ${x.status}">${x.status}</span></div>`).join("")}
      <div class="hint rv-keys"><kbd>j</kbd>/<kbd>k</kbd> move · <kbd>a</kbd> apply · <kbd>r</kbd> reject</div></div>
    <div class="rv-main"><div class="ed-bar"><span class="crumbs"><b>${esc(p.path)}</b> <span class="muted">#${p.id}</span></span><span class="status ${p.status}">${p.status}</span><span class="muted rv-reason">${esc(p.reason || "")}</span><span class="spacer"></span>${propActions(p)}<button class="btn ghost" id="rvOpen">${icon("file")}Open file</button></div>
      <div class="ed-scroll">${diffHtml(p.diff)}</div>
      <div class="rv-ask"><textarea class="field" id="rvAsk" rows="2" placeholder="Ask for a change to this, e.g. &quot;keep the old name as an alias&quot;"></textarea><button class="btn" id="rvAskBtn">${icon("send")}Send</button></div></div></div>`;
  $(".rv-list").onclick = (e) => { const it = e.target.closest("[data-rv]"); if (it) { tab.sel = +it.dataset.rv; renderReviewTab(tab); } };
  $("#rvOpen").onclick = () => openFile(p.path);
  $("#rvApplyAll") && ($("#rvApplyAll").onclick = () => bulkProposals("apply"));
  const ask = () => { const t = $("#rvAsk").value.trim(); if (!t) return; setInput(`About change #${p.id} to ${p.path}: ${t}`); send(); };
  $("#rvAskBtn").onclick = ask;
  $("#rvAsk").onkeydown = (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(); } };
}
function reviewKeys(e) {
  const tab = state.tabs.find((t) => t.id === "review");
  if (!tab || state.active !== "review" || e.target.closest("input,textarea,select") || e.metaKey || e.ctrlKey || e.altKey) return false;
  const list = reviewList(), i = list.findIndex((p) => p.id === tab.sel), p = list[i];
  if (e.key === "j" || e.key === "ArrowDown") { tab.sel = list[Math.min(i + 1, list.length - 1)]?.id; renderReviewTab(tab); return true; }
  if (e.key === "k" || e.key === "ArrowUp") { tab.sel = list[Math.max(i - 1, 0)]?.id; renderReviewTab(tab); return true; }
  if ((e.key === "a" || e.key === "r") && p?.status === "pending") {
    proposalAction(p, e.key === "a" ? "apply" : "reject").then(() => {
      refreshProposalViews(p.id); loadGit(); reloadOpenFiles([p]);
      const next = reviewList().find((x) => x.status === "pending"); if (next) { tab.sel = next.id; renderReviewTab(tab); }
    });
    return true;
  }
  return false;
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
  $("#traceRoots").innerHTML = d.roots.length
    ? `Trace and log files from this folder's <span class="mono">${d.roots.map((r) => esc(r.replace(state.workspace + "/", "") + "/")).join(", ")}</span>: for example logs, test or eval results, or OpenTelemetry traces your app writes. Open one for a timeline, or ask codepilot about it. <span class="muted">CODEPILOT_TRACE_DIRS points elsewhere.</span>`
    : "No traces/ or logs/ folder found (CODEPILOT_TRACE_DIRS adds more).";
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
  e.stopPropagation(); e.preventDefault(); // inside a collapsed row's <summary>: act, don't expand
  const id = ap.dataset.apply || ap.dataset.reject || ap.dataset.revert;
  const action = ap.dataset.apply ? "apply" : ap.dataset.reject ? "reject" : "revert";
  try {
    const p = await api(`/api/proposals/${id}/${action}`, { method: "POST" }); state.proposals.set(p.id, p);
    for (const o of p.outdated || []) { state.proposals.set(o.id, o); refreshProposalViews(o.id); } // older versions of it
    toast({ apply: `Applied #${p.id} to ${p.path}`, reject: `Rejected #${p.id}`, revert: `Undid #${p.id}; ${p.path} restored` }[action]);
    if (action === "apply" && p.checks) { toast(`Checks found issues in ${p.path}; codepilot will see them next turn`, true); activity("error", "checks", p.path, p.checks); }
  } catch (err) { toast(err.message, true); if (action === "apply") { const p = state.proposals.get(+id); if (p) p.status = "failed"; } }
  refreshProposalViews(+id); loadGit();
  const p = state.proposals.get(+id);
  const tab = state.tabs.find((t) => t.id === "file:" + p?.path); if (tab) { tab.content = null; if (state.active === tab.id) openFile(tab.path); }
});
function refreshProposalViews(id) {
  renderReviewBar();
  setTimeout(maybeResumeAfterReview, 0);
  if (state.tabs.some((t) => t.id === "review") && state.active === "review") renderEditor();
  const p = state.proposals.get(id); if (!p) return;
  $$(`[data-prop="${id}"]`).forEach((card) => { const s = $(".status", card); s.className = "status " + p.status; s.textContent = p.status; s.title = STATUS_TIPS[p.status] || ""; const a = $(".pacts", card); if (a) a.innerHTML = propActions(p); });
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
    <div class="group-head" style="padding-left:2px">Always allowed in this session</div>
    <div class="hint" id="allowList">${(state.allow || []).length ? state.allow.map((r, i) => `<span class="allow-chip"><code>${esc(r.tool === "github" ? "gh " + r.prefix : r.prefix)}</code><button class="icon-btn sm" data-unallow="${i}" title="Ask again for these">${icon("x")}</button></span>`).join(" ") : "Nothing. Tick “always allow” when approving a command to skip asking for it in this session."}</div>
    <div class="group-head" style="padding-left:2px">Token usage</div><div id="usageTable" class="hint">—</div>
    <div class="group-head" style="padding-left:2px">Analysers (run_checks)</div>
    <div class="hint">${(w?.checks || []).length ? w.checks.map((c) => `<span class="mono">${esc(c.name)}</span> <span class="muted">${esc(c.kind)}</span>`).join(" · ") : "None detected. Install ruff / mypy / pyright, eslint / tsc, gitleaks, semgrep… and codepilot uses them automatically."}</div>
    <div class="group-head" style="padding-left:2px">Modes</div>
    ${(w?.modes || []).map((m) => `<div class="hint" style="margin:3px 0"><b style="color:var(--fg-2)">${esc(m.label)}</b>${m.builtin ? "" : ' <span class="proj">custom</span>'} — ${esc(m.description)}</div>`).join("")}
    <div class="hint">Add your own in <span class="mono">~/.codepilot/modes/*.md</span> or <span class="mono">.codepilot/modes/</span>.</div>
    <div class="group-head" style="padding-left:2px">Skills</div>
    ${(w?.skills || []).map((s) => `<div class="hint" style="margin:3px 0"><b class="mono" style="color:var(--fg-2)">${esc(s.name)}</b> — ${esc(s.description)}</div>`).join("") || `<div class="hint">—</div>`}
    <div class="group-head" style="padding-left:2px">Steering (always on)</div>
    <div class="hint">${w?.instructions ? `<pre class="mono" style="white-space:pre-wrap;margin:0;font-size:11.5px">${esc(w.instructions)}</pre>` : "None yet."} <a href="#" id="memSteering">Manage in the Steering view</a></div>`;
  $("#memSteering") && ($("#memSteering").onclick = (e) => { e.preventDefault(); setView("steering"); });
  renderUsage(state.usage);
  $("#allowList").onclick = async (e) => {
    const b = e.target.closest("[data-unallow]"); if (!b || !state.sid) return;
    const keep = state.allow.filter((_, i) => i !== +b.dataset.unallow);
    const d = await api(`/api/sessions/${state.sid}`, { method: "PATCH", body: { allow: keep } }).catch((err) => toast(err.message, true));
    if (d) { state.allow = d.allow || []; renderMemory(); }
  };
  $("#compactBtn") && ($("#compactBtn").onclick = compactNow);
  $("#handoffBtn") && ($("#handoffBtn").onclick = handoff);
  if (state.workspace && state.sid) {
    // Unsaved edits survive re-renders of this view and aren't overwritten by the saved notes arriving late.
    const key = state.workspace;
    if (state.notesDraft?.key === key) $("#notesBox").value = state.notesDraft.text;
    $("#notesBox").oninput = () => { state.notesDraft = { key, text: $("#notesBox").value }; };
    api(`/api/sessions/${state.sid}/notes`).then((n) => { if (state.notesDraft?.key !== key) $("#notesBox").value = n.notes; $("#notesPath").textContent = n.path; }).catch(() => {});
    $("#saveNotes").onclick = async () => { await api(`/api/sessions/${state.sid}/notes`, { method: "PUT", body: { notes: $("#notesBox").value } }); state.notesDraft = null; toast("Notes saved"); };
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
// Long messages (a pasted trace, a log) show their first lines with Show all / Show less, so they don't
// bury the rest of the conversation.
const CLAMP_LINES = 12, CLAMP_CHARS = 1500;
function userMessageHtml(text) {
  const lines = text.split("\n").length;
  if (lines <= CLAMP_LINES && text.length <= CLAMP_CHARS) return `<div class="msg user"><div class="body">${userHtml(text)}</div></div>`;
  const size = `${lines.toLocaleString()} line${lines === 1 ? "" : "s"} · ${fmtBytes(new Blob([text]).size)}`;
  return `<div class="msg user long clamped"><div class="body">${userHtml(text)}</div>
    <div class="msg-foot"><button class="more" type="button" data-size="${esc(size)}">${icon("chevron")}<span>Show all (${esc(size)})</span></button><button class="more copy-msg" type="button" title="Copy this message">${icon("copy")}<span>Copy</span></button></div></div>`;
}
// Edit / retry: a message that started a turn knows its id (mid) and can rewind the conversation to it.
function markTurn(el, mid, text) {
  el.dataset.mid = mid;
  if (text != null) state.msgText.set(String(mid), text);
  else if (!state.msgText.has(String(mid))) state.msgText.set(String(mid), $(".body", el)?.innerText ?? "");
  if (!$(".msg-actions", el)) el.insertAdjacentHTML("beforeend", `<div class="msg-actions"><button data-act="edit" title="Edit and resend (rewinds the conversation to here)">${icon("edit")}</button><button data-act="retry" title="Send again from here">${icon("refresh")}</button></div>`);
}
const lastTurnBubble = () => [...$$("#transcript .msg.user[data-mid]")].at(-1) || null;
function rewindTo(el, text) {
  if (!state.sid || state.streams.has(state.sid)) return toast("Wait for codepilot to finish (or press Stop) first.", true);
  const mid = +el.dataset.mid;
  while (el.nextElementSibling) el.nextElementSibling.remove();
  el.remove();
  const fresh = add(userMessageHtml(text)); scrollEnd(true);
  state.prompts = (state.prompts || []).concat(text); resetHistory();
  streamTo(state.sid, `/api/sessions/${state.sid}/rewind`, { mid, message: text, tier: selectedTier() }).then(() => fresh);
}
async function editMessage(el) {
  const original = state.msgText.get(el.dataset.mid) ?? $(".body", el).innerText;
  if ($(".edit-box", el)) return;
  el.classList.add("editing");
  el.insertAdjacentHTML("beforeend", `<div class="edit-box"><textarea class="field" rows="3"></textarea><div class="edit-acts"><span class="hint">Enter to send · Esc to cancel</span><span class="spacer"></span><button class="btn sm" data-edit="cancel">Cancel</button><button class="btn sm primary" data-edit="send">Send</button></div></div>`);
  const ta = $(".edit-box textarea", el); ta.value = original; ta.style.height = Math.min(ta.scrollHeight + 4, 320) + "px"; ta.focus(); ta.setSelectionRange(ta.value.length, ta.value.length);
  const close = () => { $(".edit-box", el)?.remove(); el.classList.remove("editing"); };
  const go = async () => {
    const text = ta.value.trim(); if (!text) return;
    const isLast = el === lastTurnBubble();
    if (!isLast && !(await confirmDialog("Rewind to this message?", "Everything after it in this conversation is removed, then your edited message is sent. File changes you already applied stay (undo them in Changes if needed).", "Rewind & send"))) return;
    close(); rewindTo(el, text);
  };
  ta.onkeydown = (e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); go(); } if (e.key === "Escape") close(); };
  $("[data-edit=cancel]", el).onclick = close; $("[data-edit=send]", el).onclick = go;
}
async function retryFrom(el) {
  const isLast = el === lastTurnBubble();
  if (!isLast && !(await confirmDialog("Retry from here?", "Everything after this message is removed and it's sent again.", "Retry"))) return;
  rewindTo(el, state.msgText.get(el.dataset.mid) ?? $(".body", el).innerText);
}
function userHtml(text) {
  return esc(text).replace(/(^|[\s(])@([\w.\-/~]+)(?::(\d+)(?:-(\d+))?)?/g, (m, pre, p, a) => `${pre}<span class="ref" data-path="${p}" ${a ? `data-line="${a}"` : ""}>@${m.slice(pre.length + 1)}</span>`);
}
function argSummary(name, input) {
  if (!input) return "";
  if (!Object.values(input).some((v) => v !== "" && v != null)) return "";
  if (name === "update_plan" && Array.isArray(input.items)) return `${input.items.filter((i) => i.status === "done").length}/${input.items.length} done`;
  if (name === "write_spec") return `${input.doc || ""}.md · ${(input.content || "").split("\n").length} lines`;
  if (name === "update_task") return `task ${input.task} → ${String(input.status || "").replace("_", " ")}`;
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
    case "user": {
      endText();
      if (ev.text === REVIEW_DONE) { add(`<div class="wait-row approved">${icon("refresh")}<span>Continued after your review</span></div>`); break; }
      for (const id of ev.queued_ids || (ev.queued_id ? [ev.queued_id] : [])) $(`#transcript .msg.queued[data-qid="${id}"]`)?.remove();
      const el = add(userMessageHtml(ev.text));
      if (ev.queued || ev.queued_id) el.insertAdjacentHTML("afterbegin", `<div class="sent-while">sent while codepilot was working</div>`);
      if (ev.mid) markTurn(el, ev.mid, ev.text);
      break;
    }
    case "turn": { const u = [...$$("#transcript .msg.user:not(.queued)")].reverse().find((x) => !x.dataset.mid && !$(".sent-while", x)); if (u) markTurn(u, ev.mid); break; }
    case "route": endText(); add(`<div class="skill-chip route-chip" title="Auto picked this model because: ${esc(ev.reason)}">${icon("sparkle")}auto → ${esc(shortModel(ev.model))} · ${esc(ev.reason)}</div>`); if (!replay) activity("model", "auto", `${shortModel(ev.model)} (${ev.tier}): ${ev.reason}`); break;
    case "spec": {
      endText();
      const what = ev.created ? `started ${ev.kind === "bugfix" ? "bugfix " : ""}spec` : ev.doc ? `wrote ${ev.doc}` : ev.task ? `task ${ev.task} → ${ev.status.replace("_", " ")}` : "updated";
      add(`<div class="skill-chip spec-chip" data-spec-open="${esc(ev.name)}">${icon("list")}spec ${esc(ev.name)}: ${esc(what)}</div>`);
      if (!replay) { loadSpecs(true).then(() => { if (ev.created || ev.doc === "requirements") openSpec(ev.name); }); }
      break;
    }
    case "advisor": endText(); add(`<details class="card advisor" open><summary>${icon("sparkle")}Second opinion from ${esc(shortModel(ev.model))}</summary><div class="md">${md(ev.text)}</div></details>`); break;
    case "attached_images": add(`<div class="img-row">${ev.images.map((im) => `<a href="${esc(im.url)}" target="_blank" rel="noopener" title="${esc(im.source && im.source !== "pasted" ? im.source : "Open full size")}"><img src="${esc(im.url)}" alt="attached image" loading="lazy"></a>`).join("")}</div>`); break;
    case "attached": add(`<div class="attached">${ev.paths.map((p) => `<span data-path="${esc(p.split(":")[0])}" data-line="${esc(p.split(":")[1]?.split("-")[0] || "")}">${icon("file")} ${esc(p)}</span>`).join("")}</div>`); break;
    case "assistant": endText(); add(`<div class="msg assistant">${md(ev.text)}</div>`); break;
    case "skill": add(`<div class="skill-chip">${icon("sparkle")}skill: ${esc(ev.name)}</div>`); break;
    case "steering": endText(); add(`<div class="skill-chip steer-chip" title="Steering docs codepilot loaded for this">${icon("compass")}steering: ${esc(ev.names.join(", "))}${ev.file ? ` · for ${esc(ev.file)}` : ""}</div>`); break;
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
      if (ev.images?.length) { el.insertAdjacentHTML("beforeend", `<div class="img-row">${ev.images.map((u) => `<a href="${esc(u)}" target="_blank" rel="noopener"><img src="${esc(u)}" alt="image" loading="lazy"></a>`).join("")}</div>`); el.open = true; }
      if (!replay) activity(ev.is_error ? "error" : "result", ev.name, `${ev.output.length.toLocaleString()} chars${ev.seconds ? " · " + ev.seconds + "s" : ""}`, ev.output);
      break;
    }
    case "sub_tool": {
      const el = state.toolEls.get(ev.parent); if (!el) break;
      let subs = $(".subs", el); if (!subs) { subs = document.createElement("div"); subs.className = "subs"; $("summary", el).after(subs); el.open = true; }
      subs.insertAdjacentHTML("beforeend", `<div>↳ ${esc(ev.name)} ${esc(ev.detail)}</div>`); subs.scrollTop = subs.scrollHeight;
      if (!replay) activity("explore", ev.name, ev.detail); break;
    }
    case "proposal": {
      endText();
      const known = state.proposals.get(ev.proposal.id);
      state.proposals.set(ev.proposal.id, { ...known, ...ev.proposal, diff: ev.proposal.diff || known?.diff || "" });
      if ($(`#transcript [data-prop="${ev.proposal.id}"]`)) refreshProposalViews(ev.proposal.id); // e.g. superseded
      else { renderProposalCard(state.proposals.get(ev.proposal.id)); renderProposalList(); renderReviewBar(); }
      break;
    }
    case "proposal_ref": { const p = state.proposals.get(ev.id); if (p && !$(`#transcript [data-prop="${p.id}"]`)) renderProposalCard(p); break; }
    case "proposals_changed": for (const id of ev.ids) { const p = state.proposals.get(id); if (p) { p.status = "discarded"; refreshProposalViews(id); } } break;
    case "approval_needed": {
      endText();
      $$("#transcript .wait-row.waiting").forEach((w) => w.remove());
      add(`<div class="wait-row waiting">${icon("alert")}<span>Waiting for your approval: ${ev.tools.map((t) => `<code>${esc(t.command)}</code>`).join(", ")}</span><span class="muted">(see the bar below)</span></div>`);
      state.approval = { tools: ev.tools }; renderReviewBar();
      break;
    }
    case "workspace": setWorkspace(ev.repo, true); loadSessions(); toast(`Opened ${ev.repo}`); break;
    case "plan": renderPlan(ev.items); break;
    case "usage": { const u = ev.usage || {}; activity("model", shortModel(ev.model || ""), `in ${fmtTok(u.inputTokens || 0)} · out ${fmtTok(u.outputTokens || 0)}${u.cacheReadInputTokens ? " · cached " + fmtTok(u.cacheReadInputTokens) : ""} · ${ev.seconds}s`); endText(); refreshUsage(); break; }
    case "context": setContext(ev); break;
    case "notice": endText(); add(`<div class="banner notice">${esc(ev.message)}</div>`); break;
    case "error": {
      endText();
      const b = add(`<div class="banner error">${esc(ev.message)}</div>`);
      if (!replay) { activity("error", "error", ev.message); const last = lastTurnBubble(); if (last) b.insertAdjacentHTML("beforeend", ` <button class="btn sm" data-retry-last>Retry</button>`); }
      break;
    }
    case "done": endText(); break;
  }
  if (!replay) scrollEnd();
}
function propActions(p) {
  if (p.status === "pending") return `<button class="btn primary" data-apply="${p.id}">Apply</button><button class="btn" data-reject="${p.id}">Reject</button>`;
  if (p.status === "applied") return `<button class="btn" data-revert="${p.id}" title="Restore the file as it was before this change">${icon("history")}Undo</button>`;
  return "";
}
const STATUS_TIPS = {
  pending: "Waiting for your review", applied: "Written to the file (Undo restores it)", rejected: "You rejected it",
  outdated: "The file changed since this was proposed, so it can no longer be applied", superseded: "Replaced by a newer proposal for the same lines",
  discarded: "Dropped when the conversation was rewound", reverted: "Undone", failed: "Couldn't be applied",
};
function diffStat(diff) {
  let a = 0, d = 0;
  for (const l of (diff || "").split("\n")) { if (l.startsWith("+") && !l.startsWith("+++")) a++; else if (l.startsWith("-") && !l.startsWith("---")) d++; }
  return { a, d, html: `<span class="dstat"><span class="a">+${a}</span> <span class="d">−${d}</span></span>` };
}
function renderProposalCard(p) {
  // Compact in the chat: one line with its status; the diff is a click away, and review happens in the bar/tab.
  return add(`<details class="card prop" data-prop="${p.id}"><summary class="hd">${icon("edit")}<span class="path" data-prop-open="${p.id}" title="Open in Review">${esc(p.path)}</span>${diffStat(p.diff).html}<span class="muted">#${p.id}</span><span class="status ${p.status}" title="${esc(STATUS_TIPS[p.status] || "")}">${p.status}</span><span class="spacer"></span>
    <span class="pacts">${propActions(p)}</span></summary>
    ${p.reason ? `<div class="reason">${esc(p.reason)}</div>` : ""}${diffHtml(p.diff)}</details>`);
}
function renderPlan(items) {
  const el = $("#plan");
  if (!items || !items.length) { el.hidden = true; el.innerHTML = ""; return; }
  el.hidden = false;
  el.innerHTML = items.map((i) => `<div class="it ${esc(i.status)}"><span class="box"></span><span>${esc(i.text)}</span></div>`).join("");
}
$("#transcript").addEventListener("click", (e) => {
  const act = e.target.closest(".msg.user[data-mid] .msg-actions [data-act]");
  if (act) { const el = act.closest(".msg.user"); act.dataset.act === "edit" ? editMessage(el) : retryFrom(el); return; }
  if (e.target.closest("[data-retry-last]")) { const el = lastTurnBubble(); if (el) retryFrom(el); return; }
  const qb = e.target.closest(".msg.queued [data-qedit], .msg.queued [data-qcancel]");
  if (qb) { unqueue(qb.closest(".msg.queued"), !!qb.dataset.qedit || qb.hasAttribute("data-qedit")); return; }
  const qs = e.target.closest(".msg.queued [data-qswitch]");
  if (qs) { switchQueued(qs.closest(".msg.queued")); return; }
  const more = e.target.closest(".msg.user .more");
  if (more) {
    const msg = more.closest(".msg.user");
    if (more.classList.contains("copy-msg")) { copyText($(".body", msg).innerText, "message"); return; }
    const clamped = msg.classList.toggle("clamped");
    $("span", more).textContent = clamped ? `Show all (${more.dataset.size})` : "Show less";
    if (clamped) msg.scrollIntoView({ block: "nearest" });
    return;
  }
  const loc = e.target.closest("a.loc, .ref, .attached span");
  if (loc) { e.preventDefault(); openFile(loc.dataset.path, +loc.dataset.line || undefined); return; }
  const po = e.target.closest("[data-prop-open]"); if (po) { e.preventDefault(); openProposal(po.dataset.propOpen); return; }
  const so = e.target.closest("[data-spec-open]"); if (so) { openSpec(so.dataset.specOpen); return; }
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
// Desktop notification when codepilot finishes or needs approval while you're in another tab or app.
function notifyDone(sid) {
  if (!document.hidden || !("Notification" in window) || Notification.permission !== "granted") return;
  const needs = state.approval;
  const title = (state.sessionList || []).find((s) => s.id === sid)?.title || "codepilot";
  try { const n = new Notification(needs ? "codepilot needs your approval" : "codepilot finished", { body: title, icon: "/static/favicon.png", tag: sid }); n.onclick = () => { window.focus(); n.close(); }; } catch { /* unsupported */ }
}
function askNotifyPermission() { if ("Notification" in window && Notification.permission === "default") Notification.requestPermission().catch(() => {}); }
function updateBusy() {
  const busy = state.streams.has(state.sid);
  input.placeholder = busy ? "Working… Enter steers it now · Tab queues a message to run after" : state.placeholder || input.placeholder;
  $("#sendBtn").hidden = busy; $("#stopBtn").hidden = !busy; $("#steerBtn").hidden = $("#queueBtn").hidden = !busy;
  $("#sbBusy").innerHTML = busy ? '<span class="spinner"></span>working…' : "";
}
// body === null follows a turn that's already running (the page was opened or reloaded while it ran).
async function streamTo(sid, url, body) {
  if (state.streams.has(sid)) return;
  let ended; state.streamEnds.set(sid, new Promise((r) => { ended = r; }));
  state.streams.add(sid); updateBusy(); loadSessions();
  const typing = sid === state.sid ? add(`<div class="typing"><i></i><i></i><i></i></div>`) : null;
  const follow = body === null;
  try {
    const res = await fetch(url, follow ? { headers: H } : { method: "POST", headers: H, body: JSON.stringify(body) });
    if (res.status === 409 && !follow) { const d = await res.json().catch(() => ({})); throw new Error(d.error || "This session is busy."); }
    if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.error || res.statusText); }
    const reader = res.body.getReader(); const dec = new TextDecoder(); let buf = "";
    for (;;) {
      const { value, done } = await reader.read(); if (done) break;
      buf += dec.decode(value, { stream: true });
      let nl;
      while ((nl = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, nl); buf = buf.slice(nl + 1);
        if (!line.trim()) continue;
        if (sid === state.sid) {
          render(JSON.parse(line));
          if (typing && typing.isConnected) $("#transcript").appendChild(typing);
          $$("#transcript .msg.queued").forEach((q) => $("#transcript").appendChild(q)); // queued messages stay last
        }
      }
    }
  } catch (err) { if (sid === state.sid) render({ type: "error", message: err.message }); }
  finally {
    typing?.remove(); state.streams.delete(sid); state.streamEnds.delete(sid); ended(); updateBusy(); loadSessions();
    if (follow) { if (sid === state.sid) await openSession(sid).catch(() => null); return; } // redraw it whole
    notifyDone(sid);
    if (sid === state.sid) {
      const pending = [...state.proposals.values()].filter((p) => p.status === "pending");
      if (pending.length) { state.awaitingReview = sid; state.reviewBatch = new Set(pending.map((p) => p.id)); }
    }
    if (sid === state.sid && (state.runAll || state.tabs.some((t) => t.kind === "spec") || $(".view.on")?.dataset.view === "specs")) afterSpecTurn();
    if (sid === state.sid) { loadGit(); const d = await api(`/api/sessions/${sid}`).catch(() => null); if (d) { state.summary = d.summary; state.allow = d.allow || []; $("#chatTitle").textContent = d.session.title || "New session"; if ($(".view.on")?.dataset.view === "memory") renderMemory(); } }
  }
}
// While a turn runs, a message either steers it (when="now": codepilot reads it at its next step) or waits to
// run as its own turn once the current one finishes (when="after").
const QUEUE_LABEL = { now: "Steering: codepilot reads this at its next step", after: "Queued: runs when the current work finishes" };
const queuedBar = (when) => `${icon(when === "after" ? "list" : "history")}<span>${QUEUE_LABEL[when]}</span><span class="spacer"></span><button class="btn sm ghost" data-qswitch>${when === "after" ? "Steer now instead" : "Run after instead"}</button><button class="btn sm ghost" data-qedit>Edit</button><button class="btn sm ghost" data-qcancel>Remove</button>`;
async function queueMessage(text, when = "now") {
  let q;
  try { q = await api(`/api/sessions/${state.sid}/queue`, { method: "POST", body: { text, when } }); }
  catch (err) { if (err.status === 409) return false; toast(err.message, true); return true; } // 409: the turn just ended
  $("#input").value = ""; autosize(); hideMentions(); resetHistory(); rememberPrompt(text);
  add(`<div class="msg user queued" data-qid="${esc(q.id)}" data-when="${q.when || when}"><div class="body">${userHtml(text)}</div><div class="queued-bar">${queuedBar(q.when || when)}</div></div>`);
  scrollEnd(true);
  return true;
}
async function switchQueued(el) {
  const when = el.dataset.when === "after" ? "now" : "after";
  const r = await api(`/api/sessions/${state.sid}/queue/${el.dataset.qid}`, { method: "PATCH", body: { when } }).catch(() => ({ ok: false }));
  if (!r.ok) return toast("Already sent to codepilot.", true);
  el.dataset.when = when; $(".queued-bar", el).innerHTML = queuedBar(when);
}
// A turn running on the server that this page isn't showing (reloaded, or started in another window): follow it.
function followIfRunning(sid, busy) {
  if (busy && sid === state.sid && !state.streams.has(sid)) streamTo(sid, `/api/sessions/${sid}/follow`, null);
}
async function unqueue(el, edit) {
  const r = await api(`/api/sessions/${state.sid}/queue/${el.dataset.qid}`, { method: "DELETE" }).catch(() => ({ ok: false }));
  if (!r.ok) return toast("Already sent to codepilot.", true);
  const text = $(".body", el).innerText; el.remove();
  if (edit) setInput(input.value ? input.value + "\n" + text : text);
}
async function send(when = "now") {
  const text = $("#input").value.trim();
  const pics = state.attachments.slice();
  if (!pics.length && runSlashCommand(text)) return;
  if (!text && !pics.length) return;
  if (state.sid && state.streams.has(state.sid)) {
    if (pics.length) return toast("Images go with your next message: send them when codepilot finishes (or press Stop).", true);
    if (await queueMessage(text, when)) return;
    await state.streamEnds.get(state.sid); // it was just finishing: send this as the next message
  }
  if (state.creatingSession) await state.creatingSession.catch(() => null); // "New session" still opening
  if (!state.sid) { try { await newSession(state.workspace); } catch (err) { toast(err.message, true); return; } }
  if (state.approval) { // writing instead of approving declines the waiting command (the server does the same)
    const row = $("#transcript .wait-row.waiting");
    if (row) { row.classList.remove("waiting"); row.classList.add("denied"); row.innerHTML = `${icon("x")}<span>Declined (you wrote a message instead): ${state.approval.tools.map((t) => `<code>${esc(t.command)}</code>`).join(", ")}</span>`; }
    state.approval = null; renderReviewBar();
  }
  $("#input").value = ""; autosize(); hideMentions(); resetHistory(); askNotifyPermission(); clearAttachments();
  if (text) { rememberPrompt(text); (state.prompts ||= []).push(text); }
  render({ type: "user", text: text || (pics.length > 1 ? "(see the attached images)" : "(see the attached image)") }); scrollEnd(true);
  if (!state.session?.title) $("#chatTitle").textContent = (text || "Image").split("\n")[0].slice(0, 80);
  streamTo(state.sid, `/api/sessions/${state.sid}/chat`, { message: text, tier: selectedTier(), images: pics.map((a) => ({ data: a.data, media_type: a.type })) });
}

// ---------------------------------------------------------------- composer: images (paste, drop, attach)
// Images are shrunk in the browser (long side ≤ 1568 px, the size Claude reads at full detail) before sending.
async function addImageFile(file) {
  if (!file || !/^image\/(png|jpeg|gif|webp)$/.test(file.type)) return toast("Only PNG, JPEG, GIF and WebP images can be attached.", true);
  if (state.attachments.length >= 8) return toast("Up to 8 images per message.", true);
  try {
    const { data, type } = await shrinkImage(file);
    const url = URL.createObjectURL(file);
    state.attachments.push({ data, type, url, name: file.name || "pasted image" });
    renderAttachments();
  } catch (err) { toast(`Couldn't read that image: ${err.message}`, true); }
}
async function shrinkImage(file, maxSide = 1568, maxBytes = 3_000_000) {
  const toB64 = (blob) => new Promise((res, rej) => { const fr = new FileReader(); fr.onload = () => res(String(fr.result).split(",")[1]); fr.onerror = () => rej(fr.error); fr.readAsDataURL(blob); });
  const bmp = await createImageBitmap(file);
  const scale = Math.min(1, maxSide / Math.max(bmp.width, bmp.height));
  if (scale === 1 && file.size <= maxBytes && file.type !== "image/gif") return { data: await toB64(file), type: file.type };
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bmp.width * scale); canvas.height = Math.round(bmp.height * scale);
  canvas.getContext("2d").drawImage(bmp, 0, 0, canvas.width, canvas.height);
  let blob = await new Promise((res) => canvas.toBlob(res, "image/png"));
  if (blob.size > maxBytes) blob = await new Promise((res) => canvas.toBlob(res, "image/jpeg", 0.85)); // photos
  return { data: await toB64(blob), type: blob.type };
}
function renderAttachments() {
  const tray = $("#attachTray");
  tray.innerHTML = state.attachments.map((a, i) => `<span class="att"><img src="${a.url}" alt="${esc(a.name)}" title="${esc(a.name)}"><button class="icon-btn sm" data-unattach="${i}" title="Remove">${icon("x")}</button></span>`).join("");
  tray.hidden = !state.attachments.length;
}
function clearAttachments() { state.attachments.forEach((a) => URL.revokeObjectURL(a.url)); state.attachments = []; renderAttachments(); }
$("#attachTray").addEventListener("click", (e) => { const b = e.target.closest("[data-unattach]"); if (!b) return; const [a] = state.attachments.splice(+b.dataset.unattach, 1); URL.revokeObjectURL(a.url); renderAttachments(); });
$("#imgBtn").onclick = () => $("#imgFile").click();
$("#imgFile").onchange = (e) => { [...e.target.files].forEach(addImageFile); e.target.value = ""; };
$("#input").addEventListener("paste", (e) => { // ("input" is declared further down)
  const files = [...(e.clipboardData?.items || [])].filter((it) => it.kind === "file" && it.type.startsWith("image/")).map((it) => it.getAsFile());
  if (!files.length) return; // plain text pastes normally
  e.preventDefault(); files.forEach(addImageFile);
});
// Ctrl+V on a Mac (where the system shortcut is ⌘V), in any text box: read the clipboard ourselves. The browser
// asks once for permission ("See text and images copied to the clipboard"); if it's blocked, say how to allow it.
async function pasteFromClipboard(el = input) {
  if (!navigator.clipboard) return pasteFailed("this page isn't a secure context; open codepilot at http://127.0.0.1 or http://localhost");
  try {
    if (navigator.clipboard.read) {
      for (const item of await navigator.clipboard.read()) {
        const img = item.types.find((t) => /^image\/(png|jpeg|gif|webp)$/.test(t));
        if (img && el === input) { const blob = await item.getType(img); await addImageFile(new File([blob], "pasted image", { type: img })); continue; }
        if (item.types.includes("text/plain")) insertAtCaret(await (await item.getType("text/plain")).text(), el);
        else if (item.types.includes("text/html")) insertAtCaret(new DOMParser().parseFromString(await (await item.getType("text/html")).text(), "text/html").body.textContent || "", el);
      }
    } else insertAtCaret(await navigator.clipboard.readText(), el);
  } catch (err) {
    let perm = "";
    try { perm = (await navigator.permissions.query({ name: "clipboard-read" })).state; } catch { /* not every browser can say */ }
    pasteFailed(perm === "denied" ? "the browser is set to block clipboard access for this page" : `the browser refused (${err.name}: ${err.message})`);
  }
}
function pasteFailed(why) {
  notePageError(`Ctrl+V paste: ${why}`);
  const edge = /Edg\//.test(navigator.userAgent), settings = `${edge ? "edge" : "chrome"}://settings/content/clipboard`;
  const chromium = /Chrome\//.test(navigator.userAgent);
  toast(`Ctrl+V couldn't read the clipboard: ${why}. ⌘V always works.${chromium ? ` To allow Ctrl+V, open ${settings} and add ${location.origin} under "Allowed".` : ""}`, true,
    chromium ? { label: "Copy settings link", run: () => copyText(settings) } : null);
}
function insertAtCaret(text, el = input) { el.setRangeText(text, el.selectionStart, el.selectionEnd, "end"); el.dispatchEvent(new Event("input", { bubbles: true })); if (el === input) autosize(); }
$("#sendBtn").onclick = () => send();
$("#steerBtn").onclick = () => { if (input.value.trim()) send("now"); else input.focus(); };
$("#queueBtn").onclick = () => { if (input.value.trim()) send("after"); else input.focus(); };
$("#stopBtn").onclick = async () => {
  if (!state.sid) return;
  state.runAll = null;
  const r = await api(`/api/sessions/${state.sid}/cancel`, { method: "POST" }).catch(() => null);
  if (r?.queued?.length) { // stopped: queued messages come back to the message box, not lost
    $$("#transcript .msg.queued").forEach((q) => q.remove());
    setInput([input.value, ...r.queued].filter(Boolean).join("\n\n"));
    toast("Stopped. Your queued message is back in the box.");
  }
};
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
  $("#input").placeholder = state.placeholder = m && mode !== "build" ? `${m.label}: ${m.description}` : "Ask codepilot…  @ files · / skills · # steering";
}
$("#modeSelect").addEventListener("change", async () => {
  const mode = $("#modeSelect").value; setMode(mode);
  if (state.sid) await api(`/api/sessions/${state.sid}`, { method: "PATCH", body: { mode } }).catch((err) => toast(err.message, true));
});
// ---- model picker: tiers, then the models this account can actually call (one entry per version, newest first)
const winLabel = (w) => (w >= 1_000_000 ? `${w / 1_000_000}M` : `${Math.round(w / 1000)}k`);
function selectedTier() { const v = $("#tier").value || ""; return v.startsWith("tier:") ? v.slice(5) : (state.session?.tier || state.cfg.default_tier); }
function tierTip(r, m) {
  if (r?.upgraded) return `${m}\nThe newest model in its family on your account (.env has ${r.configured}). Set CODEPILOT_LATEST_MODELS=0 to use exactly what's configured.`;
  if (r?.fallback) return `Configured ${r.configured} isn't enabled for this account (${r.reason || ""}); using ${m}`;
  return m;
}
function renderModelSelect() {
  const c = state.cfg, d = state.modelsData, tiers = d?.tiers || {};
  const tierOpts = c.tiers.map((t) => {
    const r = tiers[t], m = r ? r.model : c.models[t];
    return `<option value="tier:${t}" title="${esc(tierTip(r, m))}">${t} · ${esc(shortModel(m) || "not set")}${r?.fallback ? " (fallback)" : ""}</option>`;
  }).join("");
  const usable = (d?.models || []).filter((m) => m.available && !m.same_as);
  const newest = usable.filter((m) => m.newest || !/claude-/.test(m.id)), older = usable.filter((m) => !newest.includes(m));
  const off = (d?.models || []).filter((m) => !m.available).length;
  const name = (m) => `${m.label}${m.api === "Converse" ? " · " + m.id.split(".")[0] : ""} · ${winLabel(m.window)}`;
  const opt = (m) => `<option value="model:${esc(m.id)}" title="${esc(m.id + " · " + m.api)}">${esc(name(m))}</option>`;
  const autoOpt = `<option value="tier:auto" title="Picks a model for each turn: the newest Sonnet for routine work, the newest Opus for planning, debugging, big changes or when runs keep failing, Haiku for quick questions.">auto · picks per turn</option>`;
  const refreshTip = off ? `${off} other model${off === 1 ? " isn't" : "s aren't"} enabled for this account, so they're hidden. \`codepilot models\` lists them with the reason.` : "";
  $("#tier").innerHTML = `<optgroup label="Tiers">${autoOpt}${tierOpts}</optgroup>`
    + (newest.length ? `<optgroup label="Models on your account">${newest.map(opt).join("")}</optgroup>` : "")
    + (older.length ? `<optgroup label="Older versions">${older.map(opt).join("")}</optgroup>` : "")
    + `<option value="refresh" title="${esc(refreshTip)}">${d ? "↻ Refresh model list" : "Find models on my account…"}</option>`;
  syncModelSelect();
}
function syncModelSelect() {
  const s = state.session, tier = s?.tier || state.cfg.default_tier;
  $("#tier").value = s?.model ? "model:" + s.model : "tier:" + tier;
  if (!$("#tier").value) $("#tier").value = "tier:" + tier;
}
async function loadModels(refresh) {
  if (refresh) toast("Checking which models your account can use…");
  const d = await api(`/api/models${refresh ? "?refresh=1" : ""}`).catch((err) => { if (refresh) toast(err.message, true); return null; });
  if (d) {
    state.modelsData = d;
    const fb = Object.entries(d.tiers || {}).filter(([, t]) => t.fallback);
    if (fb.length && refresh !== null) toast(`${fb.map(([k, t]) => `${k}: ${shortModel(t.configured)} not enabled, using ${shortModel(t.model)}`).join("; ")}`);
    else if (refresh) toast(`Found ${(d.models || []).filter((m) => m.available && !m.same_as).length} models on your account. Tiers use the newest of each family.`);
  }
  renderModelSelect();
}
$("#tier").addEventListener("change", async () => {
  const v = $("#tier").value;
  if (v === "refresh") { syncModelSelect(); await loadModels(true); return; }
  if (!state.sid) return;
  const body = v.startsWith("model:") ? { model: v.slice(6) } : { tier: v.slice(5), model: "" };
  const d = await api(`/api/sessions/${state.sid}`, { method: "PATCH", body }).catch((err) => { toast(err.message, true); return null; });
  if (d) { state.session = d.session; setContext(d.context); }
});
$("#autoApprove").addEventListener("change", () => state.sid && api(`/api/sessions/${state.sid}`, { method: "PATCH", body: { auto_approve: $("#autoApprove").checked } }));
$("#autoApply").addEventListener("change", () => state.sid && api(`/api/sessions/${state.sid}`, { method: "PATCH", body: { auto_apply: $("#autoApply").checked } }).then(() => toast($("#autoApply").checked ? "Edits are applied as they're proposed (each can be undone)" : "Edits wait for your review again")));

// ---------------------------------------------------------------- composer: prompt history (Up / Down)
// Like a shell: Up on the first line recalls earlier prompts (this session's, then other sessions'), Down goes
// forward and finally restores what you were typing.
const hist = { list: [], idx: null, draft: "", setting: false };
function rememberPrompt(text) {
  let all = [];
  try { all = JSON.parse(store("cp-prompts") || "[]"); } catch { all = []; }
  all = all.filter((t) => t !== text); all.push(text);
  store("cp-prompts", JSON.stringify(all.slice(-200)));
}
function promptHistory() {
  let global = [];
  try { global = JSON.parse(store("cp-prompts") || "[]"); } catch { global = []; }
  const mine = state.prompts || [];
  const seen = new Set(mine);
  return [...global.filter((t) => !seen.has(t)), ...mine.filter((t, i) => mine.lastIndexOf(t) === i)];
}
function historyStep(dir) {
  if (hist.idx === null) { hist.list = promptHistory(); hist.idx = hist.list.length; hist.draft = input.value; }
  const next = hist.idx + dir;
  if (next < 0 || next > hist.list.length) return false;
  hist.idx = next;
  const text = next === hist.list.length ? hist.draft : hist.list[next];
  hist.setting = true; input.value = text; autosize(); hist.setting = false;
  const caret = dir < 0 ? 0 : text.length; // Up again keeps going back; Down again keeps going forward
  input.setSelectionRange(caret, caret);
  return true;
}
function resetHistory() { hist.idx = null; }

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
  if (mention.kind === "steering") return showSteeringMenu(input.value.slice(mention.start + 1, input.selectionStart));
  const pop = $("#mentionPop");
  if (!mention.items.length) { pop.hidden = true; mention.open = false; return; }
  mention.open = true; pop.hidden = false;
  pop.innerHTML = mention.items.map((f, i) => `<div class="opt ${i === mention.idx ? "on" : ""}" data-i="${i}">${fileIcon(f)}<span>${esc(base(f))}</span><span class="dir">${esc(dirOf(f))}</span></div>`).join("");
}
function hideMentions() { mention.open = false; $("#mentionPop").hidden = true; }
function acceptMention(i) {
  const f = mention.items[i]; if (!f) return;
  const pos = input.selectionStart;
  if (mention.kind === "steering") {
    input.value = input.value.slice(0, mention.start) + "#" + f + " " + input.value.slice(pos);
    const caret = mention.start + f.length + 2; input.setSelectionRange(caret, caret); hideMentions(); autosize(); return;
  }
  if (mention.kind === "skill") {
    const cmd = slashCommands().find((c) => c.name === f && !c.server);
    if (cmd && (!cmd.args || cmd.args.startsWith("[")) && !input.value.slice(pos).trim()) { input.value = "/" + f; hideMentions(); send(); return; } // run it
    input.value = "/" + f + " " + input.value.slice(pos);
    input.setSelectionRange(f.length + 2, f.length + 2); hideMentions(); autosize(); return;
  }
  input.value = input.value.slice(0, mention.start) + "@" + f + " " + input.value.slice(pos);
  const caret = mention.start + f.length + 2; input.setSelectionRange(caret, caret); hideMentions(); autosize();
}
input.addEventListener("input", () => {
  if (!hist.setting) resetHistory();
  autosize();
  const pos = input.selectionStart; const before = input.value.slice(0, pos);
  const slash = before.match(/^\/([\w.-]*)$/);
  if (slash) { showSkillMenu(slash[1]); return; }
  const hash = before.match(/(^|\s)#([\w.-]*)$/);
  if (hash) { mention.start = pos - hash[2].length - 1; showSteeringMenu(hash[2]); return; }
  const m = before.match(/(^|\s)@([\w.\-/~]*)$/);
  if (m) { mention.kind = "file"; mention.start = pos - m[2].length - 1; fetchMentions(m[2]); } else hideMentions();
});
function showSkillMenu(q) {
  const cmds = slashCommands().map((c) => ({ name: c.name, description: (c.args ? c.args + " · " : "") + c.desc, cmd: true }));
  const taken = new Set(cmds.map((c) => c.name));
  const ql = q.toLowerCase(), rank = (n) => (n === ql ? 0 : n.startsWith(ql) ? 1 : 2); // exact, then prefix, then contains
  const skills = [...cmds, ...(state.wsInfo?.skills || []).filter((sk) => !taken.has(sk.name))].filter((s) => s.name.includes(ql))
    .map((s, i) => ({ s, i })).sort((a, b) => rank(a.s.name) - rank(b.s.name) || a.i - b.i).map((x) => x.s);
  if (mention.kind !== "skill" || !mention.open) mention.idx = 0;
  mention.kind = "skill"; mention.start = 0;
  mention.idx = Math.min(mention.idx, Math.max(0, skills.length - 1));
  mention.items = skills.map((s) => s.name); mention.skills = skills;
  const pop = $("#mentionPop");
  if (!skills.length) { hideMentions(); return; }
  mention.open = true; pop.hidden = false;
  pop.innerHTML = skills.map((s, i) => `<div class="opt ${i === mention.idx ? "on" : ""}" data-i="${i}">${icon(s.cmd ? "terminal" : "sparkle")}<span>/${esc(s.name)}</span><span class="desc">${esc(s.description)}</span></div>`).join("");
}

// ---------------------------------------------------------------- slash commands (run in the app; no model call)
// /compact runs on the server; skills (/skill-name) go to the model. Everything else here acts directly.
function slashCommands() {
  const modes = (state.wsInfo?.modes || DEFAULT_MODES).map((m) => ({ name: m.name, args: "[message]", desc: `Switch to ${m.label} mode${m.description ? ": " + m.description.replace(/\.$/, "") : ""}; any text after it is sent`, run: (a) => modeCommand(m.name, a) }));
  return [
    { name: "help", desc: "List commands and skills", run: commandHelp },
    { name: "new", desc: "Start a new session on this folder", run: () => newSession() },
    { name: "compact", args: "[focus]", desc: "Summarise the conversation to free context", server: true },
    { name: "model", args: "auto | fast | main | hard | <model>", desc: "Switch the model for this session", run: modelCommand },
    { name: "mode", args: "<mode>", desc: "Switch mode", run: (a) => modeCommand(a.trim().toLowerCase(), "") },
    ...modes,
    { name: "spec", args: "<what to build>", desc: "Start a spec: requirements, design, tasks, then build", run: specCommand },
    { name: "init", desc: "Draft steering docs (product, tech, structure) from this repo", run: initCommand },
    { name: "retry", desc: "Send your last message again", run: () => { const el = lastTurnBubble(); el ? retryFrom(el) : toast("Nothing to retry yet.", true); } },
    { name: "undo", desc: "Undo the last change you applied", run: undoCommand },
    { name: "remember", args: "<fact>", desc: "Save a note codepilot reads in every session on this folder", run: rememberCommand },
    { name: "export", desc: "Download this conversation as Markdown", run: exportCommand },
    { name: "terminal", desc: "Open a new terminal", run: () => newTerminal() },
    { name: "usage", desc: "Context, token usage and memory", run: () => setView("memory") },
    { name: "steering", desc: "Open the steering docs", run: () => setView("steering") },
    { name: "report", desc: "Report a problem", run: openReport },
    { name: "bug", desc: "Report a problem", run: openReport },
    { name: "restart", desc: "Restart the codepilot server (loads updated code)", run: restartServer },
  ];
}
function runSlashCommand(text) {
  const m = text.match(/^\/([\w-]+)(?:\s+([\s\S]*))?$/); if (!m) return false;
  const cmd = slashCommands().find((c) => c.name === m[1].toLowerCase());
  if (!cmd || cmd.server) return false; // a skill, /compact, or just a path like /Users/...: send it
  $("#input").value = ""; autosize(); hideMentions(); resetHistory(); rememberPrompt(text);
  Promise.resolve(cmd.run((m[2] || "").trim())).catch((err) => toast(err.message, true));
  return true;
}
function commandHelp() {
  const rows = slashCommands().map((c) => `<div><span class="mono">/${esc(c.name)}${c.args ? " " + esc(c.args) : ""}</span><span class="muted">${esc(c.desc)}</span></div>`).join("");
  const skills = (state.wsInfo?.skills || []).map((sk) => `<div><span class="mono">/${esc(sk.name)}</span><span class="muted">${esc(sk.description.slice(0, 120))}</span></div>`).join("");
  add(`<div class="card cmd-help"><div class="hd">${icon("terminal")}<strong>Commands</strong><span class="muted">type / to pick one</span></div><div class="cmd-grid">${rows}</div>${skills ? `<div class="hd">${icon("sparkle")}<strong>Skills</strong></div><div class="cmd-grid">${skills}</div>` : ""}</div>`);
  scrollEnd(true);
}
function modeCommand(name, rest) {
  const modes = state.wsInfo?.modes || DEFAULT_MODES;
  if (!modes.some((m) => m.name === name)) return toast(`No mode called ${name}. Try: ${modes.map((m) => m.name).join(", ")}`, true);
  $("#modeSelect").value = name; $("#modeSelect").dispatchEvent(new Event("change"));
  toast(`${modes.find((m) => m.name === name).label} mode`);
  if (rest) { setInput(rest); send(); }
}
function modelCommand(arg) {
  const a = arg.trim().toLowerCase();
  if (!a) { $("#tier").focus(); return toast("Usage: /model auto | fast | main | hard | <model name>"); }
  let value = ["auto", "fast", "main", "hard"].includes(a) ? "tier:" + a : null;
  if (!value) {
    const hit = (state.modelsData?.models || []).find((m) => m.available && (m.id.toLowerCase().includes(a) || m.label.toLowerCase().includes(a)));
    if (!hit) return toast(`No available model matches “${arg}”.`, true);
    value = "model:" + hit.id;
  }
  $("#tier").value = value; $("#tier").dispatchEvent(new Event("change"));
  toast(`Model: ${$("#tier").selectedOptions[0]?.textContent || value}`);
}
async function specCommand(arg) {
  if (!arg) return newSpec("feature");
  if (!needFolder()) return;
  const kind = /\b(bug|broken|fails?|failing|error|crash|regression|wrong)\b/i.test(arg) ? "bugfix" : "feature";
  try {
    const sp = await api(`/api/sessions/${state.sid}/specs`, { method: "POST", body: { description: arg, kind } });
    setMode("spec"); await loadSpecs(true); openSpec(sp.name); setInput(arg); send();
  } catch (err) { toast(err.message, true); }
}
async function initCommand() {
  if (!needFolder()) return;
  const d = await api(`/api/sessions/${state.sid}/steering`).catch(() => null);
  if (!d?.foundation_prompt) return toast("Open a folder first.", true);
  setInput(d.foundation_prompt); send();
}
async function undoCommand() {
  const last = [...state.proposals.values()].filter((p) => p.status === "applied").sort((a, b) => b.id - a.id)[0];
  if (!last) return toast("No applied change to undo.", true);
  try {
    const p = await api(`/api/proposals/${last.id}/revert`, { method: "POST" }); state.proposals.set(p.id, p);
    refreshProposalViews(p.id); loadGit(); reloadOpenFiles([p]); toast(`Undid #${p.id}; ${p.path} restored`);
  } catch (err) { toast(err.message, true); }
}
async function rememberCommand(fact) {
  if (!fact) return toast("Usage: /remember <fact>, e.g. /remember tests need make db-up first", true);
  if (!needFolder()) return;
  const n = await api(`/api/sessions/${state.sid}/notes`);
  const notes = (n.notes || "").replace(/\s*$/, "") + `\n- ${fact}\n`;
  await api(`/api/sessions/${state.sid}/notes`, { method: "PUT", body: { notes: notes.replace(/^\n/, "") } });
  toast("Saved to this folder's notes");
}
async function exportCommand() {
  if (!state.sid) return toast("Nothing to export yet.", true);
  const d = await api(`/api/sessions/${state.sid}`);
  const out = [`# ${d.session.title || "codepilot session"}`, "", `_Folder: ${tilde(d.session.repo || "")} · exported ${new Date().toLocaleString()}_`, ""];
  for (const ev of d.events) {
    if (ev.type === "user") out.push(`**You:** ${ev.text}`, "");
    else if (ev.type === "assistant") out.push(`**codepilot:** ${ev.text}`, "");
    else if (ev.type === "tool_call") out.push(`> \`${ev.name}\` ${argSummary(ev.name, ev.input)}`, "");
    else if (ev.type === "proposal_ref") { const p = d.proposals.find((x) => x.id === ev.id); if (p) out.push(`> change #${p.id} to \`${p.path}\`: ${p.status}`, ""); }
  }
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([out.join("\n")], { type: "text/markdown" }));
  a.download = `${(d.session.title || "session").replace(/[^\w-]+/g, "-").slice(0, 50)}.md`;
  document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
// #name: attach a steering doc to this message (any doc; "manual" ones load only this way)
async function showSteeringMenu(q) {
  if (!state.steering && state.sid) await loadSteering(true);
  const docs = (state.steering?.docs || []).filter((d) => d.name.toLowerCase().includes(q.toLowerCase()));
  if (mention.kind !== "steering" || !mention.open) mention.idx = 0;
  mention.kind = "steering";
  if (!docs.length) { hideMentions(); return; }
  mention.items = docs.map((d) => d.name); mention.idx = Math.min(mention.idx, docs.length - 1);
  const pop = $("#mentionPop"); mention.open = true; pop.hidden = false;
  pop.innerHTML = docs.map((d, i) => `<div class="opt ${i === mention.idx ? "on" : ""}" data-i="${i}">${icon("compass")}<span>#${esc(d.name)}</span><span class="desc">${esc(inclLabel(d))} · ${esc(d.label)}</span></div>`).join("");
}
input.addEventListener("keydown", (e) => {
  if (mention.open) {
    if (e.key === "ArrowDown") { e.preventDefault(); mention.idx = (mention.idx + 1) % mention.items.length; renderMentions(); return; }
    if (e.key === "ArrowUp") { e.preventDefault(); mention.idx = (mention.idx - 1 + mention.items.length) % mention.items.length; renderMentions(); return; }
    if (e.key === "Enter" || e.key === "Tab") { e.preventDefault(); acceptMention(mention.idx); return; }
    if (e.key === "Escape") { hideMentions(); return; }
  }
  if ((e.key === "ArrowUp" || e.key === "ArrowDown") && !e.shiftKey && !e.altKey && !e.metaKey && !e.ctrlKey && !e.isComposing
      && input.selectionStart === input.selectionEnd) {
    const v = input.value, pos = input.selectionStart;
    const edge = e.key === "ArrowUp" ? !v.slice(0, pos).includes("\n") : !v.slice(pos).includes("\n");
    if (edge && historyStep(e.key === "ArrowUp" ? -1 : 1)) { e.preventDefault(); return; }
  }
  if (e.key === "Tab" && !e.shiftKey && state.streams.has(state.sid) && input.value.trim()) { e.preventDefault(); send("after"); return; }
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); }
});
$("#mentionPop").addEventListener("mousedown", (e) => { const o = e.target.closest("[data-i]"); if (o) { e.preventDefault(); acceptMention(+o.dataset.i); } });
$("#atBtn").onclick = () => { const pos = input.selectionStart ?? input.value.length; const pad = input.value && !/\s$/.test(input.value.slice(0, pos)) ? " " : ""; input.setRangeText(pad + "@", pos, pos, "end"); input.focus(); input.dispatchEvent(new Event("input")); };
const box = $("#composerBox");
box.addEventListener("dragover", (e) => { e.preventDefault(); box.classList.add("drop"); });
box.addEventListener("dragleave", () => box.classList.remove("drop"));
box.addEventListener("drop", (e) => {
  e.preventDefault(); box.classList.remove("drop");
  const files = [...(e.dataTransfer.files || [])].filter((f) => f.type.startsWith("image/"));
  if (files.length) { files.forEach(addImageFile); return; }
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
const fd = { path: "", sel: null, resolve: null, seq: 0 };
function browseFolder(start) {
  return new Promise((resolve) => {
    fd.resolve = resolve; fd.sel = null; fd.typed = false;
    $("#folderDialog").hidden = false;
    fdLoad(start || "");
  });
}
async function fdLoad(path, fromInput = false) {
  const seq = ++fd.seq;
  try {
    const d = await api(`/api/browse?path=${encodeURIComponent(path)}&hidden=${$("#fdHidden").checked ? 1 : 0}`);
    if (seq !== fd.seq) return; // a newer navigation won; a slow earlier listing mustn't overwrite it
    fd.path = d.path; fd.parent = d.parent; fd.sel = null;
    // Don't clobber a path the user is typing or pasting (only the path they just submitted may be normalised).
    const typing = fd.typed || (document.activeElement === $("#fdInput") && !fromInput);
    if (!typing) $("#fdInput").value = d.path;
    const places = d.places.filter((p) => !p.recent), recent = d.places.filter((p) => p.recent);
    const placeRow = (p) => `<div class="row ${p.path === d.path ? "on" : ""}" data-fdgo="${esc(p.path)}" title="${esc(p.path)}">${icon(p.name === "Home" ? "home" : p.path.includes("CloudStorage") ? "cloud" : p.recent ? "history" : "folder")}<span class="name">${esc(p.name)}</span></div>`;
    $("#fdPlaces").innerHTML = `<div class="sec">Places</div>${places.map(placeRow).join("")}${recent.length ? `<div class="sec">Recent</div>${recent.map(placeRow).join("")}` : ""}`;
    $("#fdList").innerHTML = d.dirs.map((x) => `<div class="row" data-fdpath="${esc(x.path)}"><span class="ficon dir">${icon("folder")}</span><span class="name">${esc(x.name)}</span>${x.project ? `<span class="proj">${esc(x.project)}</span>` : ""}</div>`).join("")
      || `<div class="empty-state">No subfolders here.</div>`;
    fdHint();
  } catch (err) { if (seq === fd.seq) $("#fdHint").textContent = err.message; }
}
function fdHint() { $("#fdHint").textContent = "Open: " + (fd.sel || fd.path); $("#fdOpen").textContent = fd.sel ? "Open selected" : "Open this folder"; }
function fdClose(value) { $("#folderDialog").hidden = true; const r = fd.resolve; fd.resolve = null; r && r(value); }
$("#fdList").addEventListener("click", (e) => {
  const row = e.target.closest("[data-fdpath]"); if (!row) return;
  $$("#fdList .row").forEach((x) => x.classList.toggle("sel", x === row)); fd.sel = row.dataset.fdpath; fdHint();
});
$("#fdList").addEventListener("dblclick", (e) => { const row = e.target.closest("[data-fdpath]"); if (row) { fd.typed = false; fdLoad(row.dataset.fdpath); } });
$("#fdPlaces").addEventListener("click", (e) => { const row = e.target.closest("[data-fdgo]"); if (row) { fd.typed = false; fdLoad(row.dataset.fdgo); } });
$("#fdUp").onclick = () => { if (fd.parent) { fd.typed = false; fdLoad(fd.parent); } };
$("#fdHidden").onchange = () => fdLoad(fd.path);
$("#fdInput").addEventListener("input", () => { fd.typed = true; });
$("#fdInput").addEventListener("keydown", (e) => { if (e.key === "Enter") { fd.typed = false; fdLoad($("#fdInput").value.trim(), true); } if (e.key === "Escape") fdClose(null); });
$("#fdOpen").onclick = () => fdClose(fd.sel || fd.path);
$("#fdCancel").onclick = () => fdClose(null);
$("#fdClose").onclick = () => fdClose(null);
$("#folderDialog").addEventListener("mousedown", (e) => { if (e.target.id === "folderDialog") fdClose(null); });
$("#folderDialog").addEventListener("keydown", (e) => {
  if (e.target.id === "fdInput") return;
  if (e.key === "Escape") fdClose(null);
  if (e.key === "Enter") { fd.typed = false; fd.sel ? fdLoad(fd.sel) : fdClose(fd.path); }
  if (e.key === "Backspace" && fd.parent) { fd.typed = false; fdLoad(fd.parent); }
});

// ---------------------------------------------------------------- file operations (File menu, explorer, editor)
const fsApi = (body) => api(`/api/sessions/${state.sid}/fs`, { method: "POST", body });
function needFolder() { if (state.sid && state.workspace) return true; toast("Open a folder first.", true); return false; }
// New items go in the selected folder, or next to the selected file, else at the top of the workspace.
function targetDir() { return !state.picked ? "" : state.pickedDir ? state.picked : dirOf(state.picked); }
async function revealInTree(path) {
  state.tree.clear();
  for (let p = dirOf(path); p; p = dirOf(p)) state.expanded.add(p);
  state.picked = path; state.pickedDir = false;
  ide.classList.remove("no-sidebar"); setView("explorer");
  await renderTree();
}
async function newItem(kind, dir = targetDir()) {
  if (!needFolder()) return;
  const where = dir ? dir + "/" : "";
  const name = await promptDialog(kind === "file" ? "New file" : "New folder", "",
    `In ${where || base(state.workspace) + "/"} · use / for subfolders, e.g. ${kind === "file" ? "utils/helpers.py" : "src/components"}`);
  if (!name) return;
  try {
    const d = await fsApi({ op: kind === "file" ? "new_file" : "new_folder", path: where + name });
    await revealInTree(d.path); state.pickedDir = d.dir; renderTree();
    if (kind === "file") { await openFile(d.path); editFile("file:" + d.path); }
    toast(`Created ${d.path}`); loadGit();
  } catch (err) { toast(err.message, true); }
}
async function renamePath(rel) {
  if (!needFolder()) return;
  const name = base(rel), dot = name.lastIndexOf(".");
  const next = await promptDialog(`Rename ${name}`, name, "A new name, or a workspace-relative path to move it.", { select: [0, dot > 0 ? dot : name.length] });
  if (!next || next === name) return;
  const to = next.includes("/") ? next : (dirOf(rel) ? dirOf(rel) + "/" : "") + next;
  try {
    const d = await fsApi({ op: "rename", path: rel, to });
    for (const t of state.tabs) {
      if (t.kind !== "file" || !(t.path === rel || t.path.startsWith(rel + "/"))) continue;
      const p = d.path + t.path.slice(rel.length);
      if (state.active === t.id) state.active = "file:" + p;
      Object.assign(t, { id: "file:" + p, path: p, title: base(p), tip: p });
    }
    await revealInTree(d.path); state.pickedDir = d.dir; renderEditor(); renderTree(); loadGit();
    toast(`Renamed to ${d.path}`);
  } catch (err) { toast(err.message, true); }
}
async function deletePath(rel, isDir) {
  if (!needFolder()) return;
  const inside = (t) => t.kind === "file" && (t.path === rel || t.path.startsWith(rel + "/"));
  const unsaved = state.tabs.some((t) => inside(t) && t.dirty);
  const ok = await confirmDialog(`Delete ${base(rel)}?`, `${isDir ? "The folder and everything in it move" : "It moves"} to codepilot's trash (~/.codepilot/trash), so you can undo.${unsaved ? " Unsaved edits will be lost." : ""}`, "Delete");
  if (!ok) return;
  try {
    const d = await fsApi({ op: "delete", path: rel });
    state.tabs = state.tabs.filter((t) => !inside(t));
    if (!state.tabs.some((t) => t.id === state.active)) state.active = state.tabs.at(-1)?.id || null;
    if (state.picked === rel || state.picked?.startsWith(rel + "/")) state.picked = null;
    state.tree.clear(); renderEditor(); renderTree(); loadGit();
    toast(`Deleted ${rel}`, false, { label: "Undo", run: async () => {
      try { const back = await fsApi({ op: "restore", trash_id: d.trash_id }); await revealInTree(back.path); state.pickedDir = back.dir; renderTree(); loadGit(); toast(`Restored ${back.path}`); }
      catch (err) { toast(err.message, true); }
    } });
  } catch (err) { toast(err.message, true); }
}
function activeFileTab() { const t = state.tabs.find((x) => x.id === state.active); return t?.kind === "file" ? t : null; }
function fileMenuItems() {
  const mod = isMac ? "⌘" : "Ctrl+", t = activeFileTab();
  return [
    { label: "New File…", icon: "filePlus", run: () => newItem("file") },
    { label: "New Folder…", icon: "folderPlus", run: () => newItem("folder") },
    "-",
    { label: "Open Folder…", icon: "folderOpen", run: openFolder },
    { label: "Go to File…", icon: "search", kbd: mod + "P", run: openPalette },
    ...(t ? ["-",
      t.editing ? { label: "Save", icon: "check", kbd: mod + "S", run: () => saveFile(t) } : { label: "Edit File", icon: "edit", run: () => editFile(t.id) },
      { label: "Rename File…", icon: "edit", run: () => renamePath(t.path) },
      { label: "Close Tab", icon: "x", kbd: "Alt+W", run: () => closeTab(t.id) }] : []),
  ];
}
$("#fileMenuBtn").onclick = (e) => menuBelow(e.currentTarget, fileMenuItems());
$("#newFileBtn").onclick = () => newItem("file");
$("#newFolderBtn").onclick = () => newItem("folder");
// Keyboard, VS Code style, only while the explorer has focus: F2 renames, Delete (or ⌘⌫) deletes.
let treeFocused = false;
document.addEventListener("mousedown", (e) => { treeFocused = !!e.target.closest("#tree"); }, true);

// ---------------------------------------------------------------- specs (spec-driven development)
const SPEC_PHASES = ["requirements", "design", "tasks", "implement"];
const phaseLabel = (spec, ph) => ({ requirements: spec?.kind === "bugfix" ? "Bug analysis" : "Requirements", design: "Design", tasks: "Tasks", implement: "Implement" })[ph];
const specSlug = (t) => { const stop = new Set(["a", "an", "the", "to", "for", "of", "and", "with", "in", "on", "i", "we", "want", "add", "make"]); const w = (t.toLowerCase().match(/[a-z0-9]+/g) || []); return ((w.filter((x) => !stop.has(x)).slice(0, 5).length ? w.filter((x) => !stop.has(x)) : w).slice(0, 5).join("-") || "spec").slice(0, 60); };
async function loadSpecs(quiet) {
  if (!state.sid || !state.workspace) { state.specs = null; if (!quiet) renderSpecs(); return; }
  state.specs = await api(`/api/sessions/${state.sid}/specs`).catch((err) => ({ specs: [], error: err.message }));
  renderSpecs();
  if (state.tabs.some((t) => t.kind === "spec" && t.id === state.active)) renderEditor();
}
const findSpec = (name) => (state.specs?.specs || []).find((x) => x.name === name);
function renderSpecs() {
  const el = $("#specsView"); if (!el) return;
  const d = state.specs;
  if (!d) { el.innerHTML = `<div class="empty-state">Open a folder to work with specs.</div>`; return; }
  const row = (x) => `<div class="row spec-row ${x.name === d.active ? "on" : ""}" data-spec-open="${esc(x.name)}" title="${esc(x.folder)}"><span class="ficon">${icon(x.kind === "bugfix" ? "alert" : "list")}</span><span class="name">${esc(x.name)}</span>${x.source !== "codepilot" ? `<span class="incl">${x.source === "speckit" ? "spec kit" : x.source}</span>` : ""}<span class="incl phase-${x.phase}">${x.phase === "implement" ? `${x.progress[0]}/${x.progress[1]}` : esc(phaseLabel(x, x.phase).toLowerCase())}</span></div>`;
  el.innerHTML = `<div class="hint" style="padding:6px 14px 2px">Plan bigger changes before coding: requirements, then design, then tasks, each reviewed, then build task by task. Kiro-compatible (<span class="mono">.codepilot/specs</span>; Kiro and Spec Kit specs are listed too).</div>
    <div style="display:flex;gap:6px;padding:8px 14px 4px;flex-wrap:wrap"><button class="btn sm primary" id="specNew">${icon("plus")}New spec</button><button class="btn sm" id="specNewBug">${icon("alert")}New bugfix spec</button></div>
    ${(d.specs || []).map(row).join("") || `<div class="hint" style="padding:4px 14px">No specs yet.</div>`}
    ${d.error ? `<div class="banner error">${esc(d.error)}</div>` : ""}`;
  $("#specNew").onclick = () => newSpec("feature");
  $("#specNewBug").onclick = () => newSpec("bugfix");
}
$("#specsView").addEventListener("click", (e) => { const r = e.target.closest("[data-spec-open]"); if (r) openSpec(r.dataset.specOpen); });
$("#newSpecBtn").onclick = () => newSpec("feature");
$("#refreshSpecsBtn").onclick = () => loadSpecs();
async function newSpec(kind) {
  if (!needFolder()) return;
  const desc = await promptDialog(kind === "bugfix" ? "Describe the bug" : "What do you want to build?", "", kind === "bugfix" ? "What happens, what should happen, and how to reproduce it if you know." : "A sentence or two. codepilot drafts the requirements first; you review each step before any code.");
  if (!desc) return;
  const name = await promptDialog("Spec name", specSlug(desc), "Lowercase letters, digits and dashes. It becomes .codepilot/specs/<name>/.");
  if (!name) return;
  try {
    const sp = await api(`/api/sessions/${state.sid}/specs`, { method: "POST", body: { name, kind, description: desc } });
    setMode("spec"); state.session && (state.session.mode = "spec");
    await loadSpecs(true); openSpec(sp.name);
    setInput(desc); send();
  } catch (err) { toast(err.message, true); }
}
function openSpec(name) {
  if (!findSpec(name) && !state.specs) { loadSpecs(true).then(() => openSpec(name)); return; }
  openTab({ id: "spec:" + name, kind: "spec", icon: "list", title: name, tip: `Spec ${name}`, name, view: null });
}
async function ensureSpecActive(spec) {
  if (state.specs?.active === spec.name && state.mode === "spec") return;
  await api(`/api/sessions/${state.sid}/specs/${encodeURIComponent(spec.name)}/activate`, { method: "POST" });
  setMode("spec"); state.specs.active = spec.name;
}
async function specSay(spec, text) {
  await ensureSpecActive(spec); setInput(text); send(); // while codepilot works, send() queues it for the next step
}
async function renderSpecTab(tab) {
  const spec = findSpec(tab.name);
  if (!spec) { $("#editor").innerHTML = `<div class="empty-state">Spec ${esc(tab.name)} not found. <button class="btn sm" id="spRefresh">Refresh</button></div>`; $("#spRefresh").onclick = () => loadSpecs(); return; }
  const cur = SPEC_PHASES.indexOf(spec.phase);
  const view = tab.view && SPEC_PHASES.indexOf(tab.view) <= cur ? tab.view : spec.phase;
  const steps = SPEC_PHASES.map((ph, i) => `<button class="sp-step ${i < cur ? "done" : i === cur ? "current" : "todo"} ${ph === view ? "on" : ""}" data-sp-view="${ph}" ${i > cur ? "disabled" : ""}>${i < cur ? icon("check") : `<span class="n">${i + 1}</span>`}${esc(phaseLabel(spec, ph))}</button>`).join(`<span class="sp-sep">›</span>`);
  const head = `<div class="ed-bar sp-head"><span class="crumbs"><b>${esc(spec.name)}</b> <span class="muted">${spec.kind === "bugfix" ? "bugfix spec" : "spec"}${spec.source !== "codepilot" ? " · " + spec.source : ""}</span></span><div class="sp-steps">${steps}</div><span class="spacer"></span>${spec.name === state.specs.active ? `<span class="incl">active</span>` : ""}</div>`;
  let body = "";
  if (view === "implement") {
    const pending = spec.tasks.filter((t) => t.status !== "done");
    const pct = spec.tasks.length ? Math.round((spec.progress[0] / spec.tasks.length) * 100) : 0;
    body = `<div class="sp-impl"><div class="sp-bar"><div class="sp-progress"><i style="width:${pct}%"></i></div><span class="muted">${spec.progress[0]} of ${spec.progress[1]} tasks done</span><span class="spacer"></span>
      ${pending.length ? `<button class="btn sm primary" id="spNext">${icon("play")}Run next task</button><button class="btn sm" id="spAll" title="Runs tasks one after another, pausing when something needs your review">${icon("play")}Run all remaining</button>` : `<span class="status applied">complete</span>`}
      <button class="btn sm" id="spDrift" title="Compare the spec with the code and report differences">${icon("diff")}Check spec vs code</button>${state.specs.eval_cmd ? `<button class="btn sm" id="spEvals" title="Run the eval command and map results to acceptance criteria">${icon("beaker")}Verify with evals</button>` : ""}
      <button class="btn sm ghost" id="spEditTasks">${icon("edit")}Edit tasks</button></div>
      ${!$("#autoApply").checked && pending.length ? `<div class="hint sp-tip">Tip: tick <b>auto-apply edits</b> below the chat so tasks can run back to back; every change can still be undone in Changes.</div>` : ""}
      <div class="sp-tasks">${spec.tasks.map((t) => `<div class="sp-task ${t.status}" style="--depth:${t.depth}"><span class="sp-check">${t.status === "done" ? icon("check") : t.status === "in_progress" ? '<span class="spinner"></span>' : ""}</span><span class="sp-id">${esc(t.id)}</span><div class="sp-tt"><div>${esc(t.title)}</div>${t.requirements.length ? `<div class="muted sp-req">requirements ${esc(t.requirements.join(", "))}</div>` : ""}</div>${t.status !== "done" ? `<button class="btn sm" data-sp-run="${esc(t.id)}">${icon("play")}Run</button>` : ""}</div>`).join("") || `<div class="hint">No tasks found in tasks.md.</div>`}</div></div>`;
  } else {
    const rel = spec.docs[view];
    let content = null;
    if (rel) { const f = await api(`/api/sessions/${state.sid}/files?path=${encodeURIComponent(rel)}`).catch(() => null); content = f?.content ?? null; }
    if (state.active !== tab.id) return; // the user moved on while we loaded
    const isCurrent = view === spec.phase;
    body = `<div class="sp-doc-bar">${rel ? `<span class="mono muted">${esc(rel)}</span>` : ""}<span class="spacer"></span>
        ${rel ? `<button class="btn sm" id="spEdit">${icon("edit")}Edit</button>` : ""}
        ${isCurrent && rel ? `<button class="btn sm primary" id="spApprove">${icon("check")}Approve ${esc(phaseLabel(spec, view).toLowerCase())} &amp; continue</button>` : ""}</div>
      <div class="sp-doc md-doc" id="docBody">${content != null ? renderDoc(content, dirOf(rel)) : `<div class="empty-state">${state.streams.has(state.sid) ? '<span class="spinner"></span> codepilot is drafting this…' : `Not written yet.<br><button class="btn sm" id="spWrite">${icon("sparkle")}Ask codepilot to write it</button>`}</div>`}</div>
      ${rel ? `<div class="rv-ask"><textarea class="field" id="spAsk" rows="2" placeholder="Ask for changes to the ${esc(phaseLabel(spec, view).toLowerCase())}…"></textarea><button class="btn" id="spAskBtn">${icon("send")}Send</button></div>` : ""}`;
  }
  $("#editor").innerHTML = `<div class="spec-tab">${head}<div class="sp-body">${body}</div></div>`;
  renderMermaid($("#docBody"));
  $$(".sp-step[data-sp-view]").forEach((b) => (b.onclick = () => { tab.view = b.dataset.spView; renderSpecTab(tab); }));
  const on = (id, fn) => $(id) && ($(id).onclick = fn);
  on("#spEdit", async () => { const rel = spec.docs[view]; await openFile(rel); editFile("file:" + rel); });
  on("#spEditTasks", async () => { const rel = spec.doc_paths.tasks; await openFile(rel); editFile("file:" + rel); });
  on("#spWrite", () => specSay(spec, `Write the ${view} for spec ${spec.name}.`));
  on("#spApprove", () => approveSpec(spec, view));
  const ask = () => { const t = $("#spAsk").value.trim(); if (t) specSay(spec, `About the ${phaseLabel(spec, view).toLowerCase()} of spec ${spec.name}: ${t}`); };
  on("#spAskBtn", ask);
  $("#spAsk") && ($("#spAsk").onkeydown = (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(); } });
  on("#spNext", () => runSpecTask(spec, spec.tasks.find((t) => t.status !== "done")));
  on("#spAll", () => { state.runAll = spec.name; runSpecTask(spec, spec.tasks.find((t) => t.status !== "done")); });
  on("#spDrift", () => specSay(spec, `Check spec ${spec.name} against the current code. List: acceptance criteria that aren't implemented or only partly; behaviour in the code the spec doesn't describe; tasks marked done whose code doesn't match the design. If the code is right and the spec is stale, update the spec with write_spec. Don't change code without asking.`));
  on("#spEvals", () => specSay(spec, `Verify spec ${spec.name} with the evals: run the eval command (${state.specs.eval_cmd}), then map the results to the acceptance criteria in the requirements: for each criterion, which scenarios, test cases or traces exercise it and whether they pass. List criteria with no coverage and suggest new scenarios for them.`));
  $$("[data-sp-run]").forEach((b) => (b.onclick = () => runSpecTask(spec, spec.tasks.find((t) => t.id === b.dataset.spRun))));
}
async function approveSpec(spec, phase) {
  try {
    await api(`/api/sessions/${state.sid}/specs/${encodeURIComponent(spec.name)}/approve`, { method: "POST", body: { phase } });
    await loadSpecs(true); setMode("spec");
    const tab = state.tabs.find((t) => t.id === "spec:" + spec.name); if (tab) tab.view = null;
    if (phase === "tasks") { toast("Task list approved: run tasks from the Implement step."); renderEditor(); return; }
    specSay(spec, phase === "requirements" ? `${spec.kind === "bugfix" ? "The bug analysis is" : "The requirements are"} approved. Write the design.` : "The design is approved. Write the task list.");
  } catch (err) { toast(err.message, true); }
}
function runSpecTask(spec, task) {
  if (!task) { state.runAll = null; return toast("All tasks are done."); }
  state.runTask = { spec: spec.name, id: task.id };
  specSay(spec, `Implement task ${task.id} of spec ${spec.name}: ${task.title}`);
}
async function afterSpecTurn() {
  await loadSpecs(true);
  if (!state.runAll || !state.runTask) return;
  const spec = findSpec(state.runAll), ran = spec?.tasks.find((t) => t.id === state.runTask.id);
  const pendingChanges = [...state.proposals.values()].some((p) => p.status === "pending");
  let why = null;
  if (!spec) why = "the spec is gone";
  else if (state.approval) why = "a command needs your approval";
  else if (pendingChanges) why = "changes are waiting for your review (or tick auto-apply edits)";
  else if (ran?.status !== "done") why = `task ${state.runTask.id} isn't marked done`;
  if (why) { state.runAll = null; toast(`Run all paused: ${why}. Press Run next task to continue.`, true); return; }
  const next = spec.tasks.find((t) => t.status !== "done");
  if (!next) { state.runAll = null; toast(`Spec ${spec.name}: all tasks done.`); return; }
  runSpecTask(spec, next);
}

// ---------------------------------------------------------------- steering docs
const inclLabel = (d) => ({ always: "always on", fileMatch: "for " + d.patterns.join(", "), manual: "when you write #" + d.name, auto: "when relevant" })[d.inclusion];
async function loadSteering(quiet) {
  if (!state.sid) { state.steering = null; if (!quiet) renderSteering(); return; }
  state.steering = await api(`/api/sessions/${state.sid}/steering`).catch((err) => ({ docs: [], error: err.message }));
  if (!quiet || $(".view.on")?.dataset.view === "steering") renderSteering();
}
function renderSteering() {
  const el = $("#steeringView"), d = state.steering;
  if (!d) { el.innerHTML = `<div class="empty-state">Start a session to see its steering.</div>`; return; }
  const docs = d.docs.map((x, i) => ({ ...x, i }));
  const row = (x) => `<div class="row steer" data-steer="${x.i}" title="${esc(x.path)}\n${esc(inclLabel(x))}"><span class="ficon">${icon(x.scope === "global" ? "home" : "compass")}</span><span class="name">${esc(x.name)}</span><span class="incl ${x.inclusion}">${esc(x.inclusion === "fileMatch" ? x.patterns.join(", ") : x.inclusion === "manual" ? "#" + x.name : x.inclusion)}</span></div>`;
  const group = (title, list, empty) => `<div class="group-head">${title}</div>${list.map(row).join("") || `<div class="hint" style="padding:0 14px">${empty}</div>`}`;
  el.innerHTML = `<div class="hint" style="padding:6px 14px 2px">Standing instructions codepilot follows, in Kiro's format. Each doc is <b>always</b> on (default), loads <b>for matching files</b>, <b>manually</b> when you write <span class="mono">#name</span>, or <b>auto</b> when relevant.</div>
    <div style="display:flex;gap:6px;padding:8px 14px 2px;flex-wrap:wrap"><button class="btn sm" id="steerNew">${icon("plus")}New steering doc</button>${d.workspace_dir ? `<button class="btn sm" id="steerFoundation" title="Have codepilot study this repo and propose product.md, tech.md and structure.md">${icon("sparkle")}Generate foundation docs</button>` : ""}</div>
    ${d.workspace_dir ? group(`This workspace <span class="muted mono">.codepilot/steering</span>`, docs.filter((x) => x.scope === "workspace" && x.source === "codepilot"), "None yet.") : ""}
    ${group(`All workspaces <span class="muted mono">~/.codepilot/steering</span>`, docs.filter((x) => x.scope === "global" && x.source === "codepilot"), "None yet.")}
    ${group("From other tools", docs.filter((x) => x.source !== "codepilot"), "None found (AGENTS.md, CLAUDE.md, .kiro/steering, .cursor/rules, .github/instructions …).")}
    ${d.error ? `<div class="banner error">${esc(d.error)}</div>` : ""}`;
  $("#steerNew").onclick = (e) => menuBelow(e.currentTarget, newSteeringItems());
  $("#steerFoundation") && ($("#steerFoundation").onclick = () => { setInput(d.foundation_prompt); send(); });
}
$("#steeringView").addEventListener("click", (e) => {
  const r = e.target.closest("[data-steer]"); if (r) openSteering(state.steering.docs[+r.dataset.steer]);
});
$("#newSteeringBtn").onclick = (e) => menuBelow(e.currentTarget, newSteeringItems());
$("#refreshSteeringBtn").onclick = () => loadSteering();
function newSteeringItems() {
  const ws = !!state.steering?.workspace_dir;
  const item = (scope, inclusion, label) => ({ label, icon: scope === "global" ? "home" : "compass", run: () => newSteering(scope, inclusion) });
  return [
    ...(ws ? [item("workspace", "always", "This workspace: always on"), item("workspace", "fileMatch", "This workspace: for matching files…"),
      item("workspace", "manual", "This workspace: manual (#name)"), item("workspace", "auto", "This workspace: auto (when relevant)"), "-"] : []),
    item("global", "always", "All workspaces: always on"), item("global", "manual", "All workspaces: manual (#name)"),
  ];
}
async function newSteering(scope, inclusion) {
  const name = await promptDialog("New steering doc", "", `Name, e.g. ${inclusion === "fileMatch" ? "api-style" : "coding-standards"}. Saved as ${scope === "global" ? "~/.codepilot/steering" : ".codepilot/steering"}/<name>.md`);
  if (!name) return;
  let pattern = "";
  if (inclusion === "fileMatch") {
    pattern = await promptDialog("Which files?", "src/**/*.py", "A glob: ** spans folders, * stays within one, {a,b} for alternatives. Without a / it matches the file name anywhere (*.tsx).");
    if (!pattern) return;
  }
  try {
    const d = await api(`/api/sessions/${state.sid}/steering`, { method: "POST", body: { scope, name, inclusion, pattern } });
    await loadSteering(true); setView("steering");
    if (d.rel) { state.tree.clear(); renderTree(); await openFile(d.rel); editFile("file:" + d.rel); }
    else { await openGlobalSteering(d.name); editFile("global:" + d.name); }
  } catch (err) { toast(err.message, true); }
}
async function openGlobalSteering(name, reload) {
  try {
    const d = await api(`/api/steering/global?name=${encodeURIComponent(name)}`);
    const id = "global:" + name, existing = state.tabs.find((t) => t.id === id);
    if (existing && !reload) { state.active = id; renderEditor(); return; }
    openTab({ id, kind: "file", path: `~/.codepilot/steering/${name}.md`, title: name + ".md", tip: d.path, content: d.content, mtime: d.mtime, global: name, editing: false, draft: null, dirty: false });
  } catch (err) { toast(err.message, true); }
}
function openSteering(doc) {
  if (!doc) return;
  if (doc.rel) return openFile(doc.rel);
  if (doc.source === "codepilot") return openGlobalSteering(doc.name);
  openTab({ id: "steer:" + doc.path, kind: "file", path: doc.label, title: base(doc.label), tip: doc.path, content: doc.content || "", readonly: true });
}

// ---------------------------------------------------------------- help & problem reports
$("#helpBtn").onclick = (e) => menuBelow(e.currentTarget, [
  { label: "Report a problem…", icon: "alert", run: openReport },
  { label: "Documentation", icon: "file", run: () => window.open("https://github.com/bbrennan/codepilot/tree/main/docs", "_blank", "noopener") },
  { label: "Restart the server", icon: "refresh", run: restartServer },
]);
function reportClient() {
  return {
    browser: (navigator.userAgent.match(/(Edg|Chrome|Firefox|Version)\/[\d.]+/)?.[0] || navigator.userAgent).replace("Version/", "Safari ").replace("Edg/", "Edge ").replace("/", " ") + (/Mac/.test(navigator.platform) ? " (macOS)" : /Win/.test(navigator.platform) ? " (Windows)" : ""),
    viewport: `${innerWidth}×${innerHeight}`, errors: pageErrors.slice(),
    activity: $$("#activity .act").slice(-40).map((a) => a.innerText.replace(/\s+/g, " ").slice(0, 300)),
    ui: { view: $(".view.on")?.dataset.view, tabs: state.tabs.map((t) => t.kind), active: state.active?.split(":")[0],
      panel: $(".panel-tabs .on")?.dataset.ptab, busy: state.streams.has(state.sid), approval: !!state.approval,
      pendingChanges: [...state.proposals.values()].filter((p) => p.status === "pending").length },
  };
}
async function buildReport() {
  return api("/api/report", { method: "POST", body: { sid: state.sid, title: $("#rpTitle").value, description: $("#rpDesc").value,
    include_transcript: $("#rpTranscript").checked, client: reportClient() } });
}
const refreshReportPreview = debounce(async () => { const r = await buildReport().catch((e) => ({ issue_body: e.message })); $("#rpPreview").textContent = r.issue_body; }, 300);
function openReport() {
  $("#reportDialog").hidden = false; $("#rpHint").textContent = ""; $("#rpTitle").focus(); refreshReportPreview();
}
const closeReport = () => { $("#reportDialog").hidden = true; };
$("#rpClose").onclick = closeReport;
$("#reportDialog").addEventListener("mousedown", (e) => { if (e.target.id === "reportDialog") closeReport(); });
$("#reportDialog").addEventListener("keydown", (e) => { if (e.key === "Escape") closeReport(); });
["#rpTitle", "#rpDesc"].forEach((id) => $(id).addEventListener("input", refreshReportPreview));
$("#rpDownload").onclick = async () => {
  const r = await buildReport().catch((e) => { toast(e.message, true); return null; }); if (!r) return;
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([JSON.stringify(r.report, null, 1)], { type: "application/json" }));
  a.download = r.filename; document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  $("#rpHint").textContent = `Saved ${r.filename} to your downloads.`;
};
$("#rpIssue").onclick = async () => {
  if (!$("#rpTitle").value.trim()) { $("#rpTitle").focus(); return toast("Give the issue a short title first.", true); }
  const r = await buildReport().catch((e) => { toast(e.message, true); return null; }); if (!r) return;
  window.open(r.issue_url, "_blank", "noopener");
  $("#rpHint").textContent = "Opened GitHub: review the issue there, then press Submit.";
};

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
    ...(isDir ? [{ label: "New File…", icon: "filePlus", run: () => newItem("file", rel) }, { label: "New Folder…", icon: "folderPlus", run: () => newItem("folder", rel) }]
              : [{ label: "Edit", icon: "edit", run: async () => { await openFile(rel); editFile("file:" + rel); } }]),
    { label: "Add to chat", icon: "at", run: () => insertRef(rel) },
    "-",
    { label: "Copy relative path", icon: "copy", kbd: mod + "C", run: () => copyText(rel) },
    { label: "Copy absolute path", icon: "copy", run: () => copyText(absPath(rel)) },
    { label: "Copy @reference", icon: "link", run: () => copyText("@" + rel) },
    "-",
    { label: "Open in Terminal", icon: "terminal", run: () => newTerminal(absPath(isDir ? rel : dirOf(rel) || ".")) },
    ...(isDir ? [{ label: "Open as workspace folder", icon: "folderOpen", run: () => useFolder(absPath(rel)) }] : []),
    "-",
    { label: "Rename…", icon: "edit", kbd: "F2", run: () => renamePath(rel) },
    { label: "Delete", icon: "trash", kbd: isMac ? "⌘⌫" : "Del", run: () => deletePath(rel, isDir) },
  ];
}
document.addEventListener("contextmenu", (e) => {
  const el = e.target.closest("[data-file],[data-dir],[data-tab^='file:'],[data-gfile],[data-gitfile],[data-trace]");
  if (!el && e.target.closest("#tree") && state.workspace) { // empty space in the explorer: create at the top level
    e.preventDefault();
    showMenu(e.clientX, e.clientY, [{ label: "New File…", icon: "filePlus", run: () => newItem("file", "") },
      { label: "New Folder…", icon: "folderPlus", run: () => newItem("folder", "") },
      { label: "Open in Terminal", icon: "terminal", run: () => newTerminal(state.workspace) }]);
    return;
  }
  if (!el) return;
  e.preventDefault();
  const rel = el.dataset.file || el.dataset.dir || el.dataset.gfile || el.dataset.gitfile || el.dataset.trace || el.dataset.tab.slice(5);
  showMenu(e.clientX, e.clientY, pathMenu(rel, !!el.dataset.dir));
});

// ---------------------------------------------------------------- terminals (xterm.js <-> /api/terminals, /api/terminal)
// Terminals live on the server: they keep running (with scrollback) across page reloads and panel switches.
const terms = { list: [], active: store("cp-term-active") || null, views: new Map(), loaded: false };
const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const termToken = () => document.querySelector('meta[name="codepilot-token"]')?.content || "";
const termApi = (path, opts = {}) => api(path, { ...opts, headers: { ...H, "X-Codepilot-Terminal": termToken() } });
const termInfo = (id) => terms.list.find((t) => t.id === id);
const termLabel = (t) => `${terms.list.indexOf(t) + 1}: ${t.name}`;
function termTheme() {
  return { background: cssVar("--bg-2"), foreground: cssVar("--fg"), cursor: cssVar("--accent"), cursorAccent: cssVar("--bg-2"),
    selectionBackground: cssVar("--sel"), black: "#1d2027", red: cssVar("--err"), green: cssVar("--ok"), yellow: cssVar("--warn"),
    blue: cssVar("--accent"), magenta: cssVar("--syn-kw"), cyan: cssVar("--syn-attr"), white: cssVar("--fg-2"),
    brightBlack: cssVar("--faint"), brightWhite: cssVar("--fg") };
}
function terminalsEnabled() {
  if (termToken() && window.Terminal) return true;
  $("#termEmpty").hidden = false;
  $("#termEmptyText").textContent = "The terminal is disabled (CODEPILOT_TERMINAL=0).";
  $("#termEmptyNew").hidden = true;
  return false;
}
async function loadTerminals() {
  if (!termToken()) return renderTermBar();
  try { terms.list = (await termApi("/api/terminals")).terminals; } catch { terms.list = []; }
  terms.loaded = true;
  for (const id of [...terms.views.keys()]) if (!termInfo(id)) dropView(id);
  if (!termInfo(terms.active)) terms.active = terms.list.at(-1)?.id || null;
  renderTermBar();
}
// The Terminal panel was shown: show the active terminal, starting one if there are none.
async function openTerminal() {
  if (!terminalsEnabled()) return;
  if (!terms.loaded) await loadTerminals();
  if (!terms.list.length) return newTerminal();
  activateTerminal(terms.active || terms.list[0].id);
}
async function newTerminal(cwd) {
  if (!terminalsEnabled()) return showPanelTab("terminal");
  let t;
  try { t = await termApi("/api/terminals", { method: "POST", body: { cwd: cwd || null, sid: state.sid || null } }); }
  catch (e) { return toast(e.message, true); }
  terms.list.push(t);
  terms.active = t.id;
  if ($(".panel-body[data-ptab=terminal]").hidden || ide.classList.contains("no-panel")) showPanelTab("terminal");
  activateTerminal(t.id);
}
function activateTerminal(id) {
  if (!termInfo(id)) return;
  terms.active = id; store("cp-term-active", id);
  const v = termView(id);
  for (const [vid, view] of terms.views) view.el.hidden = vid !== id;
  renderTermBar();
  requestAnimationFrame(() => { fitTerm(v); v.xterm.focus(); });
}
function termView(id) {
  let v = terms.views.get(id);
  if (!v) {
    const el = document.createElement("div");
    el.className = "term-pane"; el.dataset.term = id;
    $("#termHost").appendChild(el);
    const xterm = new Terminal({ fontFamily: cssVar("--mono"), fontSize: 12.5, lineHeight: 1.15, cursorBlink: true,
      theme: termTheme(), scrollback: 5000, allowProposedApi: false });
    const fit = new FitAddon.FitAddon();
    xterm.loadAddon(fit);
    xterm.open(el);
    v = { id, el, xterm, fit, ws: null };
    xterm.onData((data) => {
      if (termInfo(id) && !termInfo(id).alive) return killTerminal(id); // "press any key to close"
      if (v.ws?.readyState === 1) v.ws.send(JSON.stringify({ type: "input", data }));
    });
    terms.views.set(id, v);
  }
  if (termInfo(id)?.alive && (!v.ws || v.ws.readyState > 1)) connectTerm(v);
  return v;
}
function connectTerm(v) {
  v.xterm.reset(); // the server replays the scrollback on every attach
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/api/terminal?token=${encodeURIComponent(termToken())}&id=${encodeURIComponent(v.id)}`);
  v.ws = ws;
  ws.onopen = () => fitTerm(v);
  ws.onmessage = (ev) => v.xterm.write(ev.data);
  ws.onclose = (ev) => {
    if (v.ws !== ws) return;
    const t = termInfo(v.id);
    if (ev.code === 4000) termExited(v.id, ev.reason === "" ? null : Number(ev.reason));
    else if (ev.code === 4004) { if (t) forgetTerminal(v.id); }
    else if (t && ev.code === 1008) { t.status = "Refused: reload the page (the server restarted)."; renderTermBar(); }
    else if (t) { t.status = "Disconnected. Click the terminal to reconnect."; renderTermBar(); }
  };
}
function fitTerm(v) {
  if (!v || v.el.offsetParent === null) return;
  try { v.fit.fit(); } catch { return; }
  if (v.ws?.readyState === 1) v.ws.send(JSON.stringify({ type: "resize", cols: v.xterm.cols, rows: v.xterm.rows }));
}
function termExited(id, code) {
  const t = termInfo(id); if (!t) return;
  t.alive = false; t.exit_code = code;
  // Like VS Code: a clean `exit` closes the terminal; a failure stays open so you can read why.
  if (code === 0) return killTerminal(id);
  terms.views.get(id)?.xterm.write("\r\n\x1b[2mPress any key to close this terminal, or click Restart.\x1b[0m\r\n");
  renderTermBar();
}
function dropView(id) {
  const v = terms.views.get(id); if (!v) return;
  v.ws?.close(); v.ws = null; v.xterm.dispose(); v.el.remove(); terms.views.delete(id);
}
function forgetTerminal(id) {
  const i = terms.list.findIndex((t) => t.id === id);
  if (i < 0) return;
  terms.list.splice(i, 1); dropView(id);
  if (terms.active === id) {
    const next = terms.list[Math.min(i, terms.list.length - 1)];
    terms.active = next?.id || null;
    if (next) activateTerminal(next.id);
  }
  renderTermBar();
}
async function killTerminal(id) {
  if (!id) return;
  await termApi(`/api/terminals/${id}`, { method: "DELETE" }).catch(() => null);
  forgetTerminal(id);
}
async function killAllTerminals() { for (const t of [...terms.list]) await killTerminal(t.id); }
async function renameTerminal(id) {
  const t = termInfo(id); if (!t) return;
  const name = await promptDialog("Rename terminal", t.name, "Shown in the terminal list.");
  if (!name) return;
  try { Object.assign(t, await termApi(`/api/terminals/${id}`, { method: "PATCH", body: { name } })); } catch (e) { toast(e.message, true); }
  renderTermBar();
}
async function restartTerminal(id) {
  const t = termInfo(id); if (!t) return;
  const cwd = t.cwd;
  await killTerminal(id);
  newTerminal(cwd);
}
function renderTermBar() {
  const sel = $("#termSelect"), t = termInfo(terms.active);
  sel.innerHTML = terms.list.map((x) => `<option value="${esc(x.id)}" ${x.id === terms.active ? "selected" : ""}>${esc(termLabel(x))}${x.alive ? "" : " (exited)"}</option>`).join("");
  sel.disabled = !terms.list.length;
  for (const b of ["#termRename", "#termKill", "#termSendSel"]) $(b).disabled = !t;
  $("#termCount").textContent = terms.list.length; $("#termCount").hidden = terms.list.length < 2;
  $("#termCwd").textContent = t ? tilde(t.cwd) : "";
  $("#termCwd").title = t ? t.cwd : "";
  const exited = t && !t.alive;
  $("#termStatus").textContent = exited ? `Exited with code ${t.exit_code ?? "?"}` : t?.status || "";
  $("#termStatus").className = exited ? "term-status err" : "term-status muted";
  $("#termRestart").hidden = !exited;
  $("#termEmpty").hidden = terms.list.length > 0;
  if (!terms.list.length && termToken()) { $("#termEmptyText").textContent = "No terminals are open."; $("#termEmptyNew").hidden = false; }
}
function terminalMenuItems() {
  const t = termInfo(terms.active);
  return [
    { label: "New Terminal", icon: "plus", run: () => newTerminal() },
    { label: "New Terminal in Folder…", icon: "folderOpen", run: async () => { const p = await browseFolder(state.workspace || state.cfg?.home); if (p) newTerminal(p); } },
    { label: "New Terminal in Home Folder", icon: "home", run: () => newTerminal(state.cfg?.home) },
    ...(terms.list.length ? ["-", ...terms.list.map((x) => ({ label: `${termLabel(x)}${x.alive ? "" : " (exited)"}  ·  ${tilde(x.cwd) === "~" ? "~" : base(x.cwd)}`, icon: x.id === terms.active ? "check" : "terminal",
      run: () => { showPanelTab("terminal"); activateTerminal(x.id); } }))] : []),
    ...(t ? ["-", { label: "Rename Terminal…", icon: "edit", run: () => renameTerminal(t.id) },
      { label: "Kill Terminal", icon: "trash", run: () => killTerminal(t.id) }] : []),
    ...(terms.list.length > 1 ? [{ label: "Kill All Terminals", icon: "trash", run: killAllTerminals }] : []),
  ];
}
function menuBelow(btn, items) { const r = btn.getBoundingClientRect(); showMenu(r.left, r.bottom + 4, items); }
$("#terminalMenuBtn").onclick = (e) => menuBelow(e.currentTarget, terminalMenuItems());
$("#termMore").onclick = (e) => menuBelow(e.currentTarget, terminalMenuItems());
$("#termNew").onclick = () => newTerminal();
$("#termEmptyNew").onclick = () => newTerminal();
$("#termSelect").onchange = (e) => activateTerminal(e.target.value);
$("#termRename").onclick = () => renameTerminal(terms.active);
$("#termKill").onclick = () => killTerminal(terms.active);
$("#termRestart").onclick = () => restartTerminal(terms.active);
$("#termSelect").ondblclick = () => renameTerminal(terms.active);
$("#termHost").addEventListener("mousedown", () => { const v = terms.views.get(terms.active); if (v && termInfo(v.id)?.alive && (!v.ws || v.ws.readyState > 1)) { termInfo(v.id).status = ""; connectTerm(v); renderTermBar(); } });
new ResizeObserver(() => fitTerm(terms.views.get(terms.active))).observe($("#termHost"));
$("#termSendSel").onclick = () => {
  const sel = terms.views.get(terms.active)?.xterm.getSelection();
  if (!sel) return toast("Select some terminal text first.", true);
  setInput(`${input.value ? input.value + "\n\n" : ""}Terminal output:\n\`\`\`\n${sel.trimEnd()}\n\`\`\``);
};
function onWorkspaceChangedForTerminal() {
  const v = terms.views.get(terms.active), t = termInfo(terms.active);
  if (v && t?.alive && t.cwd !== state.workspace && state.workspace)
    v.xterm.write(`\r\n\x1b[2m[codepilot] workspace is now ${tilde(state.workspace)}; use + for a terminal there]\x1b[0m\r\n`);
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

function promptDialog(title, value, hint, opts = {}) {
  return new Promise((resolve) => {
    $("#dialogTitle").textContent = title; $("#dialogInput").value = value || ""; $("#dialogHint").textContent = hint || "";
    $("#dialog").hidden = false; $("#dialogInput").focus();
    if (opts.select) $("#dialogInput").setSelectionRange(...opts.select); else $("#dialogInput").select();
    const done = (v) => { $("#dialog").hidden = true; $("#dialogOk").onclick = $("#dialogCancel").onclick = $("#dialogInput").onkeydown = null; resolve(v); };
    $("#dialogOk").onclick = () => done($("#dialogInput").value.trim());
    $("#dialogCancel").onclick = () => done(null);
    $("#dialogInput").onkeydown = (e) => { if (e.key === "Enter") done($("#dialogInput").value.trim()); if (e.key === "Escape") done(null); };
  });
}
function confirmDialog(title, hint, okLabel = "OK") {
  return new Promise((resolve) => {
    $("#dialogTitle").textContent = title; $("#dialogHint").textContent = hint || "";
    $("#dialogInput").hidden = true; $("#dialogOk").textContent = okLabel; $("#dialogOk").classList.toggle("danger", /delete|discard|overwrite/i.test(okLabel));
    $("#dialog").hidden = false; $("#dialogOk").focus();
    const done = (v) => {
      $("#dialog").hidden = true; $("#dialogInput").hidden = false; $("#dialogOk").textContent = "OK"; $("#dialogOk").classList.remove("danger");
      $("#dialogOk").onclick = $("#dialogCancel").onclick = $("#dialog").onkeydown = null; resolve(v);
    };
    $("#dialogOk").onclick = () => done(true);
    $("#dialogCancel").onclick = () => done(false);
    $("#dialog").onkeydown = (e) => { if (e.key === "Escape") done(false); };
  });
}
function toast(msg, isErr, action) {
  const el = document.createElement("div");
  el.className = "toast";
  el.textContent = msg;
  if (action) {
    const b = document.createElement("button"); b.className = "toast-act"; b.textContent = action.label;
    b.onclick = () => { el.remove(); action.run(); }; el.appendChild(b);
  }
  el.style.cssText = `position:fixed;bottom:36px;left:50%;transform:translateX(-50%);z-index:60;padding:7px 14px;border-radius:8px;font-size:12.5px;box-shadow:var(--shadow);background:var(--bg-4);border:1px solid var(--line-2);color:${isErr ? "var(--err)" : "var(--fg)"}`;
  document.querySelectorAll(".toast").forEach((t) => { if (t !== el) t.style.transform = "translate(-50%, -44px)"; });
  document.body.appendChild(el); setTimeout(() => el.remove(), action ? 8000 : 2600);
}

// ---------------------------------------------------------------- keyboard
// A text box Ctrl+V pastes into on a Mac (not the terminal, where Ctrl+V means something to the shell).
const isTextBox = (el) => !el.readOnly && !el.disabled && !el.closest(".xterm")
  && (el.tagName === "TEXTAREA" || (el.tagName === "INPUT" && /^(text|search|url|email|)$/.test(el.type)));
document.addEventListener("keydown", (e) => {
  const mod = isMac ? e.metaKey : e.ctrlKey;
  if (isMac && e.ctrlKey && !e.metaKey && !e.altKey && !e.shiftKey && e.key.toLowerCase() === "v" && isTextBox(e.target)) {
    e.preventDefault(); pasteFromClipboard(e.target); return;
  }
  if (mod && e.key.toLowerCase() === "p") { e.preventDefault(); openPalette(); }
  else if (mod && e.key.toLowerCase() === "b") { e.preventDefault(); toggle("no-sidebar"); }
  else if (mod && e.key.toLowerCase() === "j") { e.preventDefault(); toggle("no-panel"); }
  else if (mod && e.key.toLowerCase() === "l") { e.preventDefault(); ide.classList.remove("no-chat"); input.focus(); }
  else if (e.altKey && e.code === "KeyW") { e.preventDefault(); if (state.active) closeTab(state.active); }
  else if (mod && e.key === "Enter" && state.approval) { e.preventDefault(); decideApproval(true); }
  else if (reviewKeys(e)) e.preventDefault();
  else if (mod && e.key.toLowerCase() === "s") { e.preventDefault(); const t = activeFileTab(); if (t?.editing) saveFile(t); }
  else if (treeFocused && state.picked && !e.target.closest("input,textarea") && e.key === "F2") { e.preventDefault(); renamePath(state.picked); }
  else if (treeFocused && state.picked && !e.target.closest("input,textarea") && (e.key === "Delete" || (mod && e.key === "Backspace"))) { e.preventDefault(); deletePath(state.picked, state.pickedDir); }
  else if (e.ctrlKey && e.key === "`") { e.preventDefault(); const on = !$(".panel-body[data-ptab=terminal]").hidden && !ide.classList.contains("no-panel"); if (on) toggle("no-panel"); else showPanelTab("terminal"); }
  else if (mod && e.key.toLowerCase() === "c" && state.picked && !String(getSelection()) && !e.target.closest("input,textarea")) { e.preventDefault(); copyText(state.picked); }
  else if (e.key === "Escape") { closePalette(); hideMentions(); $("#ctxMenu").hidden = true; }
});

init().catch((err) => { document.body.insertAdjacentHTML("afterbegin", `<div class="banner error" style="position:fixed;top:44px;left:60px;z-index:99">${esc(err.message)}</div>`); });
