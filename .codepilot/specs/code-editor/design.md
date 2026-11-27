# Design

**Check the current CodeMirror documentation (codemirror.net) before writing code.** The package and function names
below are from memory and may have moved; the structure is what this design decides.

## The bundle (5.1–5.3)

`tools/codemirror/` (new, at the repo root, not in the Python package):

- `package.json` and its lockfile: exact versions of `@codemirror/state`, `@codemirror/view`,
  `@codemirror/commands`, `@codemirror/language`, `@codemirror/search`, `@lezer/highlight`, the language packages
  (`lang-python`, `lang-javascript`, `lang-json`, `lang-markdown`, `lang-html`, `lang-css`, `lang-yaml`, `lang-rust`,
  `lang-go`, `lang-java`, `lang-cpp`, `lang-sql`, `lang-xml`, `lang-php`), `@codemirror/legacy-modes` and `esbuild`.
  Not the `codemirror` package: it exists for `basicSetup`, which brings completion and close-brackets.
- `entry.js`: imports what `editor.js` uses and assigns one flat object to `window.CM` (the named exports of state,
  view, commands, search and language, the highlight `tags`, and a `languages` table of functions that make each
  language's extension). JavaScript, TypeScript, JSX and TSX use the language objects, not `javascript()`, which closes
  JSX tags; HTML and XML pass `autoCloseTags: false`; Markdown passes `pasteURLAsLink: false`.
- `build.sh`: `npm ci`, then `npx esbuild entry.js --bundle --minify --format=iife --target=es2020
  --legal-comments=none --metafile=…` with `--outfile` set to `codepilot/static/vendor/codemirror.min.js`, then writes
  the versions into the file's first-line comment. `licenses.mjs` writes `LICENSE-codemirror` from the metafile: every
  bundled package (CodeMirror's, Lezer's, `style-mod`, `w3c-keyname`, `crelt`, `@marijn/find-cluster-break`), each
  distinct MIT text once, and it stops the build on a package that isn't MIT.
- Size (2026-11-27, `@codemirror/view` 6.44.2): 1.1 MB minified, 380 KB gzipped. The 14 Lezer grammars are about
  650 KB of it (C++, PHP and Rust the largest); the editor itself (view, state, language, commands, search) about
  300 KB.
- `README.md`: when and how to rebuild. Not in `.github/dependabot.yml`: re-vendoring is by hand, like the others.

The built file and `LICENSE-codemirror` are committed. `pyproject.toml`'s `static/vendor/*` already ships them. The
package guard will look the npm names up when `npm ci` asks for approval; that is expected.

## Module: `static/editor.js` (new, loaded after `app.js` and `place.js`)

The only script that touches `window.CM`. `app.js`, `tabstate.js` and `folders.js` talk to it through these and never
to CodeMirror.

| Function | Behaviour |
|---|---|
| `loadEditor()` | `loadScript("/static/vendor/codemirror.min.js")` once (the helper Mermaid uses); a promise. A failed load is tried again on the next Edit |
| `mountEditor(host, tab, { readOnly, change })` | Creates the view in `host` for `tab` (its draft or text, language, read-only, place); `change(text)` on every edit; returns a handle, also kept as `tab.ed`. One editor at a time: a new one removes the last |
| `codeEditor()` | The handle shown in `#editor`, or null (`folders.js`, the Ctrl+V paste in `app.js`, and the test helpers) |
| `unmountEditor()` | Removes it; `renderEditor` calls it before `#editor` is drawn again |
| `handle.text()`, `handle.setText(t)` | The document, always with `\n` line ends (the server restores the file's own). `setText` changes only what differs, so the caret and the scroll stay |
| `handle.place()` | `{ topLine, caret }`; `topLine` as in `place.js`. (No `show`: the place is applied when the editor mounts, and nothing else moves it) |
| `handle.readOnly(on)`, `handle.editable()` | The read-only compartment (`folders.js` while the session's folders change) |
| `handle.insert(t)`, `handle.owns(el)` | Text over the selection as one undoable step, and whether `el` is the text (not a panel): the Mac's Ctrl+V paste in `app.js` (`isTextBox`, `insertAtCaret`) |
| `handle.focus()`, `handle.destroy()` | |

There is no `on.save`: ⌘S stays the global `keydown` handler's in `app.js`, which already saves the active editing tab.
CodeMirror would have run its binding and then let the key bubble there too, saving twice.

The place is kept on the tab as it changes (`tab.topLine` on scroll, `tab.caret` on a selection change), so a redraw
that removes the editor loses nothing and `renderEditor` copies nothing. The top line is applied with `place.js`'s own
`showLine` once CodeMirror has measured its lines (`requestMeasure`), not with `scrollIntoView`: that lines up a
character's box, which sits about 3px inside its 20px line, by an amount that depends on the font.

Extensions, in one `editorExtensions(tab)` function: line numbers, active-line highlight (line and gutter), special
characters, history, `drawSelection`, multiple selections, rectangular selection, the drop cursor, indent-on-input,
bracket matching, `indentUnit` and tab size 4 from `indentUnit(tab.content)` (moved here from `app.js`), the
language, the highlight style, the theme, an `aria-label` of "Edit <path>" on the text, search (`search({ top: true
})`, the panel at the top), phrases that give the panel the app's words (sentence case; "Whole word", "Regular
expression"), and one keymap: Tab and Shift+Tab, `Ctrl-g` for go-to-line, then the search, history and default
keymaps. `Ctrl-g` comes first: CodeMirror binds go-to-line to `Mod-Alt-g`, and `Mod-g` is find next, which on Windows
and Linux is Ctrl+G; first, it wins there, and F3 and Enter in the panel still find next. ⌘F and Ctrl+G have their
default prevented, so the browser's own find doesn't open (2.4). No autocompletion and no close-brackets extension.

**Tab.** Not `indentWithTab`: that binds Tab to `indentMore`, which indents the caret's whole line. With a selection,
Tab runs `indentMore` (the selected lines); at a caret it inserts the file's unit there, as the textarea did, padding
spaces to the next stop. Shift+Tab is `indentLess`. Tab no longer leaves the editor: CodeMirror's way out is Escape,
then Tab within two seconds (`docs/usage.md`), and F6 (a11y.js) works from inside it.

**The app's keys.** A key CodeMirror handles has its default prevented but still bubbles to the document, where
`app.js` and `a11y.js` listen. So a binding for one of the app's keys is left out of the keymap (`editorOwnKeys`):
⌘P, ⌘B, ⌘J, ⌘L, ⌘., ⌘S, ⌘Enter, Alt+W, F6 and Ctrl+\`, and on a Mac Ctrl+V. Shift is ignored, as the app's handlers
ignore it. That removes `Mod-Enter` (`insertBlankLine`), the Mac's Emacs-style `Ctrl-v` (page down) and
`Mod-Shift-l` (`selectSelectionMatches`).

**Languages.** `LANG_FOR` maps `extOf(path)` (app.js) to an entry of `CM.languages`: packages for py, js, mjs, jsx,
ts, tsx, json, jsonl, md, html, xml, css, yml, yaml, rs, go, java, c, h, cpp, sql, php; legacy stream modes for
scss (`sCSS`), sh, bash, zsh, toml, ini, cfg (`properties`), rb, kt, cs, swift, dockerfile. legacy-modes has no
Makefile mode, so `makefile` maps to `null` (plain text, on purpose), as txt and log do. Anything else: no language.
The read view's `LANGS` table stays as it is; a test asserts every key of `LANGS` is in `LANG_FOR` and every name in
it is a language in the bundle.

**Theme (4.1).** One `EditorView.theme` written with CSS variables only: `var(--bg-2)` and `var(--fg)` for the
editor, `var(--bg-2)` and `var(--faint)` for the gutter, `var(--bg-3)` for the caret's line (`var(--fg-2)` for its
number), `var(--sel)` for the selection, `var(--accent)` for the caret, `var(--accent-soft)` for a matching bracket.
One `HighlightStyle` maps Lezer tags to `--syn-kw`, `--syn-str`, `--syn-num`, `--syn-fn`, `--syn-com` (italic),
`--syn-type`, `--syn-attr` and `--syn-var`, as `app.css` maps highlight.js's classes. Because every value is a
variable, the theme toggle needs no call into the editor. The theme's rules beat the base theme's `&light`/`&dark`
ones (checked in the browser, by computed style). Font, 12px/20px line height, 6px above the first line and the
gutter's 16px/12px padding match `.code-view`, so a line is at the same height in the view and the editor (a test
measures it), which is what makes `topLine` carry over (4.2). The focus ring is drawn by `.code-edit:focus-within::after`
over the editor: the host's own outline is painted under CodeMirror's layers (its gutter is sticky, on top). The search
panel and the go-to-line dialog are styled in the same theme, as `.field` and `.btn.sm` look-alikes from the same
tokens (`--bg-1` panel, `--hl-line` matches, `--sel` and an `--accent` outline for the current one), not in `app.css`:
everything inside the editor is styled in one place. The panel wraps inside a 440px editor (1024×700, tested).

## Changes outside `editor.js`

- `app.js`, `renderEditTab`: the textarea in the template becomes `<div class="code-edit" id="codeEdit"></div>`. Then
  `loadEditor()`, and once it has loaded, if the host is still in the page, `mountEditor(host, tab, { readOnly, change
  })` and focus, where `change` does what `ta.oninput` did (`tab.draft = text; setDirty(tab)`, which stores the
  draft). On a load failure: toast, `tab.editing = false`, render the read view (4.5). Done's Discard question, when
  cancelled, puts focus back in the text (since #131 it would go back to the Done button). `indentUnit` moves out.
- `app.js`, `renderEditor`: `unmountEditor()` first. `ta.onblur`'s bookkeeping goes (the place is kept live).
- `app.js`, `checkDisk`'s in-place reload of a clean editing tab calls `tab.ed.setText(f.content)` and keeps the place,
  instead of re-rendering.
- `app.js`, `isTextBox` and `insertAtCaret`: the Mac's Ctrl+V paste goes through the handle when the text has focus.
- `app.js`, `saveFile` is unchanged: it sends `tab.draft`. The global `mod+s` branch in the `keydown` handler saves
  from inside the editor too.
- `folders.js` sets `readOnly` on `#editor textarea` while the folders change; it also calls `codeEditor()?.readOnly()`.
  (It doesn't call `renderEditor`; a redraw while locked mounts the editor read-only from `state.changingFolders`.)
- `tabstate.js`, `fileRecord`: the caret and top line from `tab.ed.place()`, not `$("#codeEdit").selectionStart`.
- `a11y.js`: the page-wide `MutationObserver` skips `.cm-editor`, as it skips `.xterm` (it changes on every key), and
  `A11Y_TABBABLE` counts an editable `[contenteditable='true']`.
- `index.html`: `editor.js` after `place.js`. `app.css`: `.code-edit` is a column host; the textarea rules go.

## Decisions

- **The read view stays highlight.js.** It renders a file as static HTML in a few milliseconds, and its gutter is how
  you reference lines in chat. Replacing it means re-doing line selection, the flash on jump, and `path:line` links.
  Rejected for now: one always-editable CodeMirror for both. Revisit after using this.
- **No completion.** A popup that takes Enter is a different feature, and without a language server it suggests words.
- **Loaded on first Edit,** not with the page: most sessions never click Edit, and the bundle is 1.1 MB (380 KB
  gzipped; see The bundle).
- **No textarea fallback.** Two editors to keep in step is worse than a toast for a file that ships with the app.
- **Find in the read view is still the browser's ⌘F.** Only the editor takes the key (2.4).

## Tests

- `tests/e2e/uihelpers.py`: `wait_editor`, `editor_open`, `editor_text`, `set_editor_text`, `focus_editor`,
  `editor_has_focus`, `click_editor`, `type_in_editor`, `press_in_editor`, `editor_caret_line`, `editor_top_line`,
  `scroll_editor_to_line`, going through `#codeEdit`, the handle (`codeEditor()`) and the scroller found by its style,
  so tests don't depend on CodeMirror's DOM. Each waits for the editor first: it mounts after the bundle loads, so
  `wait_for` on `#codeEdit` alone no longer means it's ready. The 52 existing uses of `#codeEdit` in seven test files,
  and the one of `.code-edit` in `test_design_tokens_ui.py`, moved to these before the swap and passed against the
  textarea.
- `tests/e2e/test_code_editor_ui.py` (new): highlighting spans in a `.py` and a `.tsx` file and none in a `.txt`; line
  numbers; Enter after `def f():` indents four spaces and after a tab-indented line a tab; Tab and Shift+Tab on three
  selected lines; ⌘Z; ⌘F find, next, replace all, then one ⌘Z restores; Ctrl+G to line 40; the theme toggle changes
  the editor's computed background; read-only while folders change; a 2 MB file is editable within a second; a blocked
  bundle (`page.route` aborting it) shows the toast and the read view. Also: the bundle is fetched on the first Edit
  only; ⌘Enter approves a waiting command with the text unchanged; ⌘P, ⇧⌘L, ⌘L and F6 do the app's thing from inside
  the editor; Ctrl+V pastes on a Mac; Escape then Tab leaves; Done's cancelled Discard puts focus back in the text; the
  editor is one Tab stop named "Edit <path>" and the keyboard audit (#128) passes with it open; a line is at the same
  height in the view and the editor.
- The ui-review-fixes place test and the restore-tabs draft tests run unchanged through the helpers (4.2, 4.3).
- `tests/test_repo_hygiene.py`: the notices table names every `static/vendor/*.js`; `tools/codemirror/package.json`
  pins exact versions (no `^` or `~`).
