"use strict";
// Edit mode's editor (spec code-editor): CodeMirror 6, vendored as static/vendor/codemirror.min.js (built from
// tools/codemirror) and loaded on the first Edit. This is the only script that touches window.CM: app.js mounts an
// editor in #codeEdit and talks to the handle mountEditor returns. Loaded after app.js and place.js, and uses their
// helpers.

let editorLoading = null;
// The bundle, once. A load that failed is tried again on the next Edit.
function loadEditor() {
  if (window.CM) return Promise.resolve();
  editorLoading ||= loadScript("/static/vendor/codemirror.min.js")
    .then(() => { if (!window.CM) throw new Error("the editor's script loaded but didn't start"); })
    .catch((err) => { editorLoading = null; throw err; });
  return editorLoading;
}

// ---- keys
// app.js and a11y.js listen for their shortcuts on the document, and a key CodeMirror handles still gets there (it
// prevents the key's default, it doesn't stop it). So a CodeMirror binding for one of the app's keys is left out, and
// ⌘Enter approves a waiting command without also inserting a line. Shift doesn't count, as the app's handlers don't
// look at it: ⇧⌘L would otherwise select every match and go to the chat.
const EDITOR_APP_KEYS = ["Mod-p", "Mod-b", "Mod-j", "Mod-l", "Mod-.", "Mod-s", "Mod-Enter", "Alt-w", "F6", "Ctrl-`",
  ...(isMac ? ["Ctrl-v"] : [])]; // on a Mac Ctrl+V pastes (app.js); CodeMirror's Emacs-style keys make it page down
const EDITOR_PLATFORM = isMac ? "mac" : /Win/.test(navigator.platform) ? "win" : "linux";
const EDITOR_MODS = { mod: isMac ? "meta" : "ctrl", cmd: "meta", m: "meta", control: "ctrl", c: "ctrl", a: "alt",
  s: "shift" };
function editorKeyId(name) {
  const parts = name.split(/-(?!$)/), key = parts.pop();
  const mods = new Set(parts.map((m) => EDITOR_MODS[m.toLowerCase()] || m.toLowerCase()));
  mods.delete("shift");
  return [...[...mods].sort(), key.length === 1 ? key.toLowerCase() : key].join("-");
}
const editorAppKeys = new Set(EDITOR_APP_KEYS.map(editorKeyId));
function editorOwnKeys(bindings) {
  return bindings.filter((b) => {
    const name = b[EDITOR_PLATFORM] || b.key; // (as CodeMirror picks it)
    return !name || !editorAppKeys.has(editorKeyId(name));
  });
}

// Tab: a selection's lines are indented; at a caret, the file's unit goes in (as the textarea did), spaces padded to
// the next stop. Shift+Tab dedents the lines. Read-only, Tab still stays here: it would otherwise leave mid-word.
function editorTab(view) {
  const st = view.state;
  if (st.readOnly) return true;
  if (st.selection.ranges.some((r) => !r.empty)) return CM.indentMore(view);
  const unit = st.facet(CM.indentUnit);
  view.dispatch(st.changeByRange((r) => {
    const col = r.head - st.doc.lineAt(r.head).from;
    const text = unit === "\t" ? "\t" : " ".repeat(unit.length - (col % unit.length));
    return { changes: { from: r.from, insert: text }, range: CM.EditorSelection.cursor(r.from + text.length) };
  }), { scrollIntoView: true, userEvent: "input.indent" });
  return true;
}

// ---- the editor
let editorShown = null; // the handle in #editor: one at a time
function codeEditor() { return editorShown; }

// Where line n starts, clamped to the document.
const editorLinePos = (doc, n) => doc.line(Math.max(1, Math.min(n || 1, doc.lines))).from;

// The smallest change from the document to text, so the caret and the scroll stay where they are.
function editorDiff(doc, text) {
  const old = doc.toString();
  let a = 0; const n = Math.min(old.length, text.length);
  while (a < n && old.charCodeAt(a) === text.charCodeAt(a)) a++;
  let b = 0;
  while (b < n - a && old.charCodeAt(old.length - 1 - b) === text.charCodeAt(text.length - 1 - b)) b++;
  return { from: a, to: old.length - b, insert: text.slice(a, text.length - b) };
}

// An editor in host for tab: its draft (else its text), read-only or not, at its place (place.js: the top line and
// the caret, else the start of the top line). opts.change(text) runs on every edit. One editor at a time: mounting a
// new one removes the last. Its place is kept on the tab as it changes (tab.topLine, tab.caret), so a redraw that
// removes it loses nothing.
function mountEditor(host, tab, opts) {
  editorShown?.destroy();
  const text = tab.draft ?? tab.content;
  const ro = new CM.Compartment();
  const doc = CM.EditorState.create({ doc: text }).doc;
  const caret = Math.min(tab.caret ?? editorLinePos(doc, tab.topLine), doc.length);
  const view = new CM.EditorView({
    parent: host,
    state: CM.EditorState.create({ doc, selection: { anchor: caret }, extensions: [
      editorExtensions(tab), ro.of(CM.EditorState.readOnly.of(!!opts.readOnly)),
      CM.EditorView.updateListener.of((u) => {
        if (u.selectionSet) tab.caret = u.state.selection.main.head;
        if (u.docChanged) opts.change(u.state.doc.toString());
      }),
    ] }),
  });
  // The top line by place.js's own arithmetic, as the view does it (a 20px line, 6px above the first), once the first
  // layout has measured the lines. Not scrollIntoView: that lines up a character's box, a few px inside its line.
  const scrollToLine = (n) => view.requestMeasure({ read: () => null, write: () => showLine(view.scrollDOM, n) });
  scrollToLine(tab.topLine);
  view.scrollDOM.addEventListener("scroll", () => { tab.topLine = topLine(view.scrollDOM); });
  const handle = editorShown = tab.ed = {
    tab,
    text: () => view.state.doc.toString(),
    setText: (t) => view.dispatch({ changes: editorDiff(view.state.doc, t) }),
    place: () => ({ topLine: topLine(view.scrollDOM), caret: view.state.selection.main.head }),
    show(p) {
      const d = view.state.doc;
      view.dispatch({ selection: { anchor: Math.min(p.caret ?? editorLinePos(d, p.topLine), d.length) } });
      scrollToLine(p.topLine);
    },
    readOnly: (on) => view.dispatch({ effects: ro.reconfigure(CM.EditorState.readOnly.of(on)) }),
    // Text from outside (a Mac's Ctrl+V, app.js), over the selection, as one undoable step.
    insert(t) {
      if (view.state.readOnly) return;
      view.dispatch(view.state.replaceSelection(t), { scrollIntoView: true, userEvent: "input.paste" });
    },
    owns: (el) => view.contentDOM.contains(el), // the text, not a panel of the editor's (find has its own boxes)
    editable: () => !view.state.readOnly,
    focus: () => view.focus(),
    destroy() {
      if (editorShown === handle) editorShown = null;
      if (tab.ed === handle) tab.ed = null;
      view.destroy();
    },
  };
  return handle;
}

// Before #editor is drawn again (app.js: renderEditor).
function unmountEditor() { editorShown?.destroy(); }

// ---- what the editor does
// The read view's languages (app.js LANGS) by extension, as CM.languages names; null: plain text, on purpose.
const LANG_FOR = {
  py: "python", js: "javascript", mjs: "javascript", jsx: "jsx", ts: "typescript", tsx: "tsx", json: "json",
  jsonl: "json", md: "markdown", yml: "yaml", yaml: "yaml", toml: "toml", ini: "properties", cfg: "properties",
  sh: "shell", bash: "shell", zsh: "shell", go: "go", rs: "rust", java: "java", kt: "kotlin", rb: "ruby", css: "css",
  scss: "scss", html: "html", xml: "xml", sql: "sql", c: "cpp", h: "cpp", cpp: "cpp", cs: "csharp", php: "php",
  swift: "swift", dockerfile: "dockerfile",
  makefile: null, txt: null, log: null, // (CodeMirror has no Makefile mode)
};

function editorExtensions(tab) {
  const lang = LANG_FOR[extOf(tab.path)];
  return [
    CM.lineNumbers(), CM.highlightActiveLineGutter(), CM.highlightActiveLine(), CM.highlightSpecialChars(),
    CM.history(), CM.drawSelection(), CM.dropCursor(), CM.EditorState.allowMultipleSelections.of(true),
    CM.rectangularSelection(), CM.crosshairCursor(), CM.indentOnInput(), CM.bracketMatching(),
    CM.indentUnit.of(indentUnit(tab.content)), CM.EditorState.tabSize.of(4),
    lang ? CM.languages[lang]() : [],
    CM.syntaxHighlighting(editorHighlightStyle()), editorTheme(),
    // Find and replace at the top, as in the app's other editors; its words as the rest of the app says them.
    CM.search({ top: true }),
    CM.EditorState.phrases.of({ next: "Next", previous: "Previous", all: "All", replace: "Replace",
      "replace all": "Replace all", "match case": "Match case", "by word": "Whole word", regexp: "Regular expression",
      close: "Close", go: "Go" }),
    CM.keymap.of(editorOwnKeys([
      { key: "Tab", run: editorTab, shift: CM.indentLess },
      // Ctrl+G: go to line, as in VS Code on every platform. First, so it beats Mod-g (find next) where Mod is Ctrl.
      { key: "Ctrl-g", run: CM.gotoLine, preventDefault: true },
      ...CM.searchKeymap, ...CM.historyKeymap, ...CM.defaultKeymap,
    ])),
    CM.EditorView.contentAttributes.of({ "aria-label": `Edit ${tab.path}`, spellcheck: "false", autocorrect: "off",
      autocapitalize: "off" }),
  ];
}

// The file's indent unit: a tab if any line starts with one, else four spaces.
function indentUnit(text) { return /^\t/m.test(text) ? "\t" : "    "; }

// Lezer's tags in the read view's colours (app.css: .hljs-*), so a file looks the same in the view and the editor.
function editorHighlightStyle() {
  const t = CM.tags, syn = (name) => `var(--syn-${name})`;
  return CM.HighlightStyle.define([
    { tag: [t.keyword, t.controlKeyword, t.operatorKeyword, t.definitionKeyword, t.moduleKeyword, t.modifier],
      color: syn("kw") },
    { tag: [t.string, t.special(t.string), t.regexp, t.character, t.inserted], color: syn("str") },
    { tag: [t.number, t.integer, t.float, t.bool, t.null, t.atom], color: syn("num") },
    { tag: [t.function(t.variableName), t.function(t.propertyName), t.macroName, t.heading], color: syn("fn") },
    { tag: [t.comment, t.lineComment, t.blockComment, t.docComment, t.meta], color: syn("com"), fontStyle: "italic" },
    { tag: [t.typeName, t.className, t.namespace], color: syn("type") },
    { tag: [t.attributeName, t.propertyName, t.labelName], color: syn("attr") },
    { tag: [t.tagName, t.special(t.variableName), t.deleted], color: syn("var") },
    { tag: [t.heading, t.strong], fontWeight: "600" },
    { tag: t.emphasis, fontStyle: "italic" },
    { tag: t.link, textDecoration: "underline" },
    { tag: t.invalid, color: "var(--err)" },
  ]);
}

// ---- the look: the app's tokens only, so the theme toggle needs no call in here (4.1). A line is 20px with 6px above
// the first, as in .code-view (app.css), so a line is at the same height in the view and the editor, and the top line
// (place.js) carries over.
const EDITOR_PAD_TOP = 6;
function editorTheme() {
  return CM.EditorView.theme({
    "&": { flex: "1", minHeight: "0", color: "var(--fg)", backgroundColor: "var(--bg-2)" }, // (in .code-edit, a column)
    "&.cm-focused": { outline: "none" }, // the host draws the ring (app.css)
    ".cm-scroller": { fontFamily: "var(--mono)", fontSize: "var(--fs-ui)", lineHeight: "20px", overflow: "auto" },
    ".cm-content": { padding: `${EDITOR_PAD_TOP}px 0 24px`, caretColor: "var(--accent)" },
    ".cm-line": { padding: "0 24px 0 8px" },
    ".cm-gutters": { backgroundColor: "var(--bg-2)", color: "var(--faint)", border: "none" },
    ".cm-lineNumbers .cm-gutterElement": { padding: "0 12px 0 16px" }, // (as .gutter in the view)
    ".cm-activeLine": { backgroundColor: "var(--bg-3)" },
    ".cm-activeLineGutter": { backgroundColor: "var(--bg-3)", color: "var(--fg-2)" },
    ".cm-cursor, .cm-dropCursor": { borderLeftColor: "var(--accent)", borderLeftWidth: "2px" },
    ".cm-selectionBackground, &.cm-focused > .cm-scroller > .cm-selectionLayer .cm-selectionBackground, ::selection":
      { backgroundColor: "var(--sel)" },
    ".cm-matchingBracket": { backgroundColor: "var(--accent-soft)", color: "inherit",
      outline: "1px solid var(--line-2)" },
    ".cm-nonmatchingBracket": { color: "var(--err)" },
    ".cm-specialChar": { color: "var(--err)" },
    // Find and replace, and go to line: the app's .field and .btn.sm (app.css), wrapping in a narrow editor.
    ".cm-panels": { backgroundColor: "var(--bg-1)", color: "var(--fg)" },
    ".cm-panels-top": { borderBottom: "1px solid var(--line)" },
    ".cm-panels-bottom": { borderTop: "1px solid var(--line)" }, // (go to line)
    ".cm-panel.cm-search, .cm-dialog": { padding: "4px 28px 4px 8px", fontSize: "var(--fs-ui)" },
    ".cm-panel.cm-search input, .cm-panel.cm-search button, .cm-panel.cm-search label": { margin: "2px 6px 2px 0" },
    ".cm-panel.cm-search label, .cm-dialog label": { fontSize: "var(--fs-ui)", color: "var(--fg-2)" },
    ".cm-panel input[type=checkbox]": { accentColor: "var(--accent)", verticalAlign: "-2px" },
    ".cm-textfield": { height: "24px", padding: "2px 6px", border: "1px solid var(--line)", borderRadius: "var(--r-md)",
      backgroundColor: "var(--bg-2)", color: "var(--fg)", font: "inherit", fontSize: "var(--fs-ui)", outline: "none",
      verticalAlign: "middle" },
    ".cm-textfield:focus": { borderColor: "var(--accent)", boxShadow: "0 0 0 2px var(--accent-soft)" },
    ".cm-button": { height: "24px", padding: "0 8px", border: "1px solid var(--line-2)", borderRadius: "var(--r-md)",
      backgroundImage: "none", backgroundColor: "var(--bg-3)", color: "var(--fg)", fontSize: "var(--fs-ui)" },
    ".cm-button:hover": { borderColor: "var(--faint)" },
    ".cm-button:active": { backgroundImage: "none", backgroundColor: "var(--bg-4)" },
    ".cm-panel.cm-search [name=close], .cm-dialog-close": { top: "6px", right: "8px", color: "var(--muted)",
      fontSize: "16px", lineHeight: "1", cursor: "pointer" },
    ".cm-searchMatch": { backgroundColor: "var(--hl-line)" },
    ".cm-searchMatch.cm-searchMatch-selected": { backgroundColor: "var(--sel)", outline: "1px solid var(--accent)" },
  });
}
