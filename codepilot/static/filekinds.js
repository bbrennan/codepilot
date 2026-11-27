"use strict";
// What kind of file a tab shows. A binary file (a NUL in its first 8,000 bytes: git's rule, textfile.kind) isn't text:
// its tab says so, with its size, and offers nothing that treats it as text (no Edit, Ask or text view). A text file
// that isn't UTF-8 is shown as it is, but can't be edited here: saving would write it back as UTF-8 and corrupt every
// character UTF-8 can't read. The server refuses that save too; this says so before you type, not after.

function renderBinaryTab(tab) {
  $("#editor").innerHTML = `<div class="ed-bar"><span class="crumbs"><b>${esc(tab.path)}</b></span><span class="spacer"></span>
      <button class="btn ghost" id="fCopy" title="Copy path">${icon("copy")}</button></div>
    <div class="ed-scroll"><div class="empty-state bin-file">${icon("file")}<b>${esc(base(tab.path))}</b>
      <span>Binary file: not shown as text · ${fmtBytes(tab.size || 0)}</span></div></div>`;
  $("#fCopy").onclick = () => copyText(tab.path);
}

const NOT_UTF8 = "This file isn't UTF-8 text, so it can't be edited here: saving would change every character UTF-8 can't read.";

// One line under the bar of a file that isn't UTF-8 ("" for any other).
function encodingNote(tab) {
  return tab.encoding ? `<div class="enc-note">${icon("alert")}<span>${esc(NOT_UTF8)}</span></div>` : "";
}

// Whether a tab may go into the editor; says why not when it may not.
function editable(tab) {
  if (!tab.encoding) return true;
  toast(NOT_UTF8, true);
  return false;
}
