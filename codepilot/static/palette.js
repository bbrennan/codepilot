"use strict";
// ⌘P: go to a file. Loaded straight after app.js and using its helpers; app.js calls openPalette and closePalette
// from its keys, the welcome page and the File menu.

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
  $("#paletteList").innerHTML = pal.items.map((f, i) => `<div class="opt ${i === pal.idx ? "on" : ""}" data-i="${i}">${fileIcon(f)}<span class="n">${esc(base(f))}</span><span class="dir">${esc(dirOf(shownPath(f)))}</span></div>`).join("") || `<div class="hint" style="padding:8px 10px">No matching files.</div>`;
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
