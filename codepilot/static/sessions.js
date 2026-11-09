"use strict";
// Getting to your sessions: the Sessions sidebar (searchable, grouped by folder) and the switcher under the chat's
// title. Both show the list loadSessions (app.js) last fetched: state.sessionList, newest first.

const sessionTitle = (s) => s.title || "New session";
// A search matches a session's title or its folder's name (what the rows show), ignoring case.
function sessionMatches(s, q) {
  q = q.trim().toLowerCase();
  return !q || [sessionTitle(s), s.repo ? base(s.repo) : ""].some((t) => t.toLowerCase().includes(q));
}
// One group per folder, in the order of each folder's newest session: the session you just used is at the top.
function sessionGroups(list) {
  const groups = new Map();
  for (const s of list) groups.set(s.repo || "", [...(groups.get(s.repo || "") || []), s]);
  return [...groups].map(([repo, items]) => ({ repo, items }));
}
const sessionBusy = (s) => s.busy || state.streams.has(s.id);

// The list changed: redraw the sidebar, and the switcher if it's open.
function renderSessions(list) {
  renderSessionList(list);
  if (!$("#sessPop").hidden) renderSwitcher();
}

// ---------------------------------------------------------------- the sidebar
function renderSessionList(list) {
  const row = (s) => `<div class="session ${s.id === state.sid ? "on" : ""}" data-id="${s.id}">
      <div class="t">${esc(sessionTitle(s))}</div>
      <div class="r">${sessionBusy(s) ? '<span class="spinner"></span>' : ""}<span>${ago(s.updated)}</span></div>
      <button class="icon-btn sm del" data-del="${s.id}" title="Delete session">${icon("trash")}</button></div>`;
  $("#sessionList").innerHTML = list.length ? sessionGroups(list).map((g) => `<div class="sess-group">
      <div class="sess-gh" title="${esc(g.repo ? tilde(g.repo) : "Sessions with no folder")}">${icon(g.repo ? "folder" : "chat")}<span>${esc(g.repo ? base(g.repo) : "No folder")}</span></div>
      ${g.items.map(row).join("")}</div>`).join("") + '<div class="empty-state sess-none" hidden>No sessions match.</div>'
    : `<div class="empty-state">No sessions yet.<br><button class="btn primary" onclick="newSession()">${icon("plus")}New session</button></div>`;
  filterSessionList(); // (rows are hidden rather than redrawn, so a search survives the refresh while a session works)
}
function filterSessionList() {
  const q = $("#sessFilter").value, byId = new Map((state.sessionList || []).map((s) => [s.id, s]));
  let any = false;
  for (const g of $$("#sessionList .sess-group")) {
    let n = 0;
    for (const r of g.querySelectorAll(".session")) { const hit = sessionMatches(byId.get(r.dataset.id) || {}, q); r.hidden = !hit; n += hit; }
    g.hidden = !n; any ||= n > 0;
  }
  const none = $("#sessionList .sess-none"); if (none) none.hidden = any;
}
$("#sessFilter").addEventListener("input", filterSessionList);

// ---------------------------------------------------------------- the switcher under the chat's title
// A combobox: focus stays in the search box, and the highlighted option (by session id, so a refresh that reorders the
// list keeps it; "new" for New session, just above the first) is its active descendant.
const sw = { hits: [], sel: null };
const NEW = "new";
function openSwitcher() {
  $("#sessPop").hidden = false; $("#chatTitleBtn").setAttribute("aria-expanded", "true"); $("#sessSearch").setAttribute("aria-expanded", "true");
  $("#sessSearch").value = ""; sw.sel = null; renderSwitcher(); $("#sessSearch").focus();
  loadSessions(); // (fresh ages and spinners; it redraws this when it arrives)
}
function closeSwitcher() {
  $("#sessPop").hidden = true; $("#chatTitleBtn").setAttribute("aria-expanded", "false"); $("#sessSearch").setAttribute("aria-expanded", "false");
}
function renderSwitcher() {
  sw.hits = (state.sessionList || []).filter((s) => sessionMatches(s, $("#sessSearch").value));
  if (sw.sel !== NEW && !sw.hits.some((s) => s.id === sw.sel)) sw.sel = sw.hits[0]?.id ?? NEW; // (the first shown)
  const opt = (id, cls, inner) => `<div class="opt ${cls}${id === sw.sel ? " hi" : ""}" id="sess-opt-${id}" ${id === NEW ? "" : `data-id="${id}"`} role="option" aria-selected="${id === sw.sel}">${inner}</div>`;
  $("#sessPopList").innerHTML = opt(NEW, "sess-new", `${icon("plus")}<span class="t">New session</span>`)
    + (sw.hits.map((s) => opt(s.id, `sess-opt${s.id === state.sid ? " on" : ""}`,
        `${sessionBusy(s) ? '<span class="spinner"></span>' : icon("history")}<span class="t">${esc(sessionTitle(s))}</span>
        <span class="dir">${esc(s.repo ? base(s.repo) : "no folder")}</span><span class="age">${ago(s.updated)}</span>`)).join("")
      || '<div class="hint sess-none">No sessions match.</div>');
  $("#sessSearch").setAttribute("aria-activedescendant", `sess-opt-${sw.sel}`);
  $("#sessPopList .hi")?.scrollIntoView({ block: "nearest" });
}
function pickSession(sid) {
  closeSwitcher();
  if (sid === NEW) newSession();
  else if (sid && sid !== state.sid) openSession(sid);
}
$("#chatTitleBtn").onclick = () => ($("#sessPop").hidden ? openSwitcher() : closeSwitcher());
$("#sessSearch").addEventListener("input", () => { sw.sel = null; renderSwitcher(); });
$("#sessSearch").addEventListener("keydown", (e) => {
  if (e.isComposing) return; // (Enter that ends an IME composition isn't a choice)
  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    e.preventDefault();
    const ids = [NEW, ...sw.hits.map((s) => s.id)], at = ids.indexOf(sw.sel) + (e.key === "ArrowDown" ? 1 : -1);
    sw.sel = ids[Math.max(0, Math.min(at, ids.length - 1))]; renderSwitcher();
  }
  else if (e.key === "Enter") { e.preventDefault(); pickSession(sw.sel); }
  else if (e.key === "Escape") { e.stopPropagation(); closeSwitcher(); $("#chatTitleBtn").focus(); }
});
$("#sessPopList").addEventListener("click", (e) => {
  if (e.target.closest(".sess-new")) return pickSession(NEW);
  const o = e.target.closest(".sess-opt"); if (o) pickSession(o.dataset.id);
});
document.addEventListener("mousedown", (e) => { if (!e.target.closest("#sessPop, #chatTitleBtn")) closeSwitcher(); });
