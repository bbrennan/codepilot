"use strict";
// One place per file tab: the line at the top of the view or the editor, kept as tab.topLine and shared by both, so
// Edit opens where you were reading, Done goes back to where you were editing, and a tab you come back to is where you
// left it. A line number rather than pixels, because the view and the editor scroll different elements.

const LINE = 20; // px: the line height of .code-view and .code-edit (app.css)

function topLine(scrollEl) {
  return Math.floor(scrollEl.scrollTop / LINE) + 1;
}

function showLine(scrollEl, n) {
  scrollEl.scrollTop = Math.max(0, ((n || 1) - 1) * LINE);
}

// The character offset where line n starts, for putting the caret on it.
function lineStart(text, n) {
  let at = 0;
  for (let i = 1; i < n; i++) {
    const nl = text.indexOf("\n", at);
    if (nl < 0) break;
    at = nl + 1;
  }
  return at;
}

// Keep tab.topLine up to date as el scrolls, after showing it there.
function keepPlace(tab, el) {
  showLine(el, tab.topLine);
  el.onscroll = () => { tab.topLine = topLine(el); };
}

// Where a jump to line n puts the top of the view: a few lines of context above it.
function jumpTop(n) {
  return Math.max(1, n - 7);
}
