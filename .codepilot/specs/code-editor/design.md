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

## Module: `static/editor.js` (new, loaded after `app.js`)

The only script that touches `window.CM`. `app.js` talks to it through five functions and never to CodeMirror.

| Function | Behaviour |
|---|---|
| `loadEditor()` | `loadScript("/static/vendor/codemirror.min.js")` once (the helper Mermaid uses); a promise |
| `mountEditor(host, tab, on)` | Creates the view in `host` for `tab` (text, language, read-only, place); `on.change(text)`, `on.save()`; returns a handle |
| `handle.text()`, `handle.setText(t)` | The document, always with `\n` line ends (the server restores the file's own) |
| `handle.place()`, `handle.show(place)` | `{ topLine, caret }`, read and applied; `topLine` as in `place.js` |
| `handle.destroy()` | Removes the view; called before `#editor` is redrawn |

Extensions, in one `extensions(tab)` function: line numbers, active-line highlight, history, bracket matching,
indent-on-input, multiple selections, the default and history keymaps, `indentWithTab`, search with its keymap,
`indentUnit` and tab size from `indentUnit(tab.content)` (app.js:733, moved here), the language, the theme, an update
listener that calls `on.change`, a `Mod-s` key that calls `on.save`, `Ctrl-g` for go-to-line, and a read-only
compartment. No autocompletion and no close-brackets extension.

**Languages.** `LANG_FOR` maps `extOf(path)` (app.js:99) to an entry of `CM.languages`: packages for py, js, mjs, jsx,
ts, tsx, json, jsonl, md, html, xml, css, yml, yaml, rs, go, java, c, h, cpp, sql, php; legacy stream modes for
scss (`sCSS`), sh, bash, zsh, toml, ini, cfg (`properties`), rb, kt, cs, swift, dockerfile. legacy-modes has no
Makefile mode, so a Makefile is plain text, as txt and log are. Anything else: no language. The read view's
`LANGS` table stays as it is; a test asserts every key of `LANGS` has an editor language or is plain text.

**Theme (4.1).** One `EditorView.theme` written with CSS variables only (`var(--bg-2)`, `var(--fg)`, `var(--sel)`,
`var(--line)`, `var(--faint)` for the gutter, `var(--accent)` for the caret) and one `HighlightStyle` mapping Lezer
tags to `--syn-kw`, `--syn-str`, `--syn-num`, `--syn-fn`, `--syn-com`, `--syn-type`, `--syn-attr`, `--syn-var`.
Because every value is a variable, the theme toggle needs no call into the editor. Font, 12px/20px line height and
6px/16px padding match `.code-view`, so a line is at the same height in the view and the editor, which is what makes
`topLine` carry over (4.2). The search panel is styled with `.field` and `.btn` look-alikes in `app.css`.

## Changes in `app.js` (`renderEditTab` and `saveFile` only)

- The textarea in `renderEditTab`'s template becomes `<div class="code-edit" id="codeEdit"></div>`. After the bar is
  bound: `await loadEditor()`, then `tab.ed = mountEditor($("#codeEdit"), tab, { change, save })`, where `change` does
  what `ta.oninput` does now (`tab.draft = text; setDirty(tab); saveTabsSoon()`). On a load failure: toast, set
  `tab.editing = false`, render the read view (4.5).
- `renderEditor` calls `tab.ed?.destroy()` for the tab being replaced, after copying `tab.ed.place()` into
  `tab.topLine` and `tab.caret`. `ta.onblur`'s bookkeeping goes.
- Read-only: `state.changingFolders` reconfigures the read-only compartment (folders.js calls `renderEditor` already).
- `checkDisk`'s in-place reload of a clean editing tab (app.js:366) calls `tab.ed.setText(f.content)` and keeps the
  place, instead of re-rendering.
- `saveFile` is unchanged: it sends `tab.draft`.
- The global `mod+s` branch in the `keydown` handler stays for focus outside the editor.

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

- `tests/e2e/uihelpers.py`: `editor_text(page)`, `type_in_editor(page, text)`, `set_editor_text(page, text)`, going
  through `#codeEdit` and the handle on the active tab, so tests don't depend on CodeMirror's DOM. The 27 existing uses
  of `#codeEdit` in six test files move to these (`wait_for` on `#codeEdit` still works: the id is kept).
- `tests/e2e/test_code_editor_ui.py` (new): highlighting spans in a `.py` and a `.tsx` file and none in a `.txt`; line
  numbers; Enter after `def f():` indents four spaces and after a tab-indented line a tab; Tab and Shift+Tab on three
  selected lines; ⌘Z; ⌘F find, next, replace all, then one ⌘Z restores; Ctrl+G to line 40; the theme toggle changes
  the editor's computed background; read-only while folders change; a 2 MB file is editable within a second; a blocked
  bundle (`page.route` aborting it) shows the toast and the read view.
- The ui-review-fixes place test and the restore-tabs draft tests run unchanged through the helpers (4.2, 4.3).
- `tests/test_repo_hygiene.py`: the notices table names every `static/vendor/*.js`; `tools/codemirror/package.json`
  pins exact versions (no `^` or `~`).
