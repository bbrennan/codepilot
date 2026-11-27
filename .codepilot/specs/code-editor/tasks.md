# Tasks

One branch and PR per numbered task. After ui-review-fixes task 2 (`place.js`) and spec restore-tabs.

- [x] 1. Vendor CodeMirror 6 as one file (`feature/vendor-codemirror`)
  - [x] 1.1 The recipe and the built bundle
    - Read the current CodeMirror docs first. `tools/codemirror/` (`package.json`, lockfile, `entry.js`, `build.sh`,
      `README.md`, and `licenses.mjs`, which writes `LICENSE-codemirror` from what was bundled); run it; commit
      `static/vendor/codemirror.min.js` and `LICENSE-codemirror`.
    - Marked done as untested (a build output); 1.2 and task 2 exercise it.
    - _Requirements: 5.1, 5.2_
    - _Tests: none (a build output: 1.2 checks it names the pinned versions; task 2 loads it)_
  - [x] 1.2 Notices and hygiene
    - Test first (unit): every vendored script is in `THIRD_PARTY_NOTICES.md`; versions in `package.json` are exact.
    - `THIRD_PARTY_NOTICES.md` (a File column), `tests/test_repo_hygiene.py`; `docs/architecture.md` (Front end: the
      vendored list).
    - _Requirements: 5.2, 5.3_
    - _Tests: tests/test_repo_hygiene.py (every `static/vendor/*.js` is named in the notices table and each licence
      file it names exists; `tools/codemirror/package.json` pins exact versions, the bundle's first line names each of
      them, and the CodeMirror row names `@codemirror/view`'s version; none of the app's own `static/*.js` imports,
      exports or requires a package); tests/test_no_mcp.py unchanged and green_
- [x] 2. Edit mode uses it (`feature/code-editor`)
  - [x] 2.1 Test helpers, and the existing editor tests moved onto them
    - `tests/e2e/uihelpers.py` (`wait_editor`, `editor_text`, `type_in_editor`, `set_editor_text` and the rest in
      design.md); the seven test files that use `#codeEdit` (52 uses) and `test_design_tokens_ui.py` (`.code-edit`).
      They pass against the textarea first, so the swap in 2.2 is checked by tests that didn't change.
    - _Requirements: 3.1_
    - _Tests: the moved tests in tests/e2e/test_files_ui.py, test_markdown_ui.py, test_specs_ui.py,
      test_multi_folder_ui.py, test_keyboard_access_ui.py, test_restore_tabs_ui.py, test_steering_ui.py and
      test_design_tokens_ui.py (126 passed against the textarea, unchanged after the swap)_
  - [x] 2.2 `editor.js` and the swap in `renderEditTab`
    - Test first (Playwright): type, the unsaved mark, ⌘S, Done with and without edits; a blocked bundle.
    - `static/editor.js` (new: `loadEditor`, `mountEditor`, the handle), `index.html`, `app.js` (`renderEditTab`,
      `renderEditor`, `checkDisk`, `isTextBox`, `insertAtCaret`), `tabstate.js` (the caret from the handle),
      `folders.js` (read-only through the handle), `a11y.js` (skips the editor's DOM; an editable div is a tab stop),
      `app.css` (`.code-edit` as a host; remove the textarea rules).
    - _Requirements: 3.1, 3.2, 3.3, 3.5, 4.5, 5.1_
    - _Tests: tests/e2e/test_code_editor_ui.py (the bundle is fetched on the first Edit and only then; typing marks the
      tab unsaved, ⌘S saves it, typing back to the file's text clears the mark, Done without edits asks nothing; Done
      asks before discarding and Cancel puts focus back in the text; a blocked bundle says so in a toast, leaves the
      read view, and the next Edit tries again; ⌘Enter approves a waiting command and the text is unchanged; ⌘P, ⇧⌘L,
      ⌘L and F6 do the app's thing from inside the editor; Ctrl+V pastes on a Mac; Tab indents and Escape then Tab
      leaves; the editor is one Tab stop named "Edit agent/core.py" and the keyboard audit passes with it open); the
      moved tests from 2.1 for the rest (changes on disk, line endings via the server, Markdown preview, steering docs)_
  - [x] 2.3 Languages, line numbers, indentation, brackets, history
    - Test first (Playwright): the cases in design.md; (unit-style, in the page) every `LANGS` key has an answer.
    - `static/editor.js` (`editorExtensions`, `LANG_FOR`, the highlight style).
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_
    - _Tests: tests/e2e/test_code_editor_ui.py (spans in a .py and a .tsx file, none in a .txt; every `LANGS` key is
      in `LANG_FOR` and every name there is in the bundle; line numbers 1 and 2 at 6px and 26px, and the caret's line
      marked as it moves; Enter after `def total(xs):` indents four spaces, after a tab-indented line a tab; Tab and
      Shift+Tab on three selected lines; a tab-indented file indents with a tab; ⌘Z and ⇧⌘Z are the editor's own; a
      bracket shows its match; two cursors type at once)_
  - [x] 2.4 Theme from the app's tokens
    - Test first (Playwright): background, text and a keyword's colour equal the tokens in dark and light, and change
      with the toggle while the editor is open.
    - `static/editor.js` (theme), `app.css` (the focus ring over the editor). The keyword's colour came with 2.3's
      highlight style; the gutter's failed first here. Looking at the real UI found two more, each test first: the
      focus ring was computed but painted under the editor, and the editor sat 3px off the view's line.
    - _Requirements: 4.1, 4.2_
    - _Tests: tests/e2e/test_code_editor_ui.py (background, text, gutter, line number and keyword colours equal the
      tokens in dark and light, and change with the theme toggle while the editor is open; line 120 is at the same
      height in the view and the editor, within 1px); tests/e2e/test_design_tokens_ui.py (the editor's focus ring, drawn
      over it)_
- [x] 3. Find, replace, go to line, and the rest (`feature/code-editor-find`)
  - [x] 3.1 Find and replace in the editor; go to line
    - Test first (Playwright): ⌘F, options, next and previous, replace, replace all and one undo; Ctrl+G.
    - `static/editor.js` (search extension, phrases, `Ctrl-g`, the panel's look in the theme; not `app.css`).
    - _Requirements: 2.1, 2.2, 2.3, 2.4_
    - _Tests: tests/e2e/test_code_editor_ui.py (⌘F opens find in the editor with its default prevented and focus in the
      Find box; Enter and Shift+Enter go to the next and previous match; Esc closes it with focus back in the text at
      the match; Match case, Whole word and Regular expression each narrow the matches; Replace and Replace all are one
      ⌘Z each; Ctrl+G, its default prevented, goes to line 240 with it in view and focus in the text; every control of
      the panel is inside the editor at 1024×700 and 1440×900)_
  - [x] 3.2 Place, drafts, read-only and large files
    - Test first (Playwright): the place and draft tests through the editor; read-only while folders change; 2 MB.
    - `static/editor.js`: `place` and the read-only compartment came with 2.2, which the moved place, draft and
      read-only tests needed; `show` went unused and was removed. (`tabstate.js` already reads `tab.ed.place()`.) These
      tests first failed only because they reach their line with Ctrl+G (3.1); what they check held from 2.2.
    - _Requirements: 3.4, 4.2, 4.3, 4.4_
    - _Tests: tests/e2e/test_code_editor_ui.py (a tab switch keeps the editor's caret line and top line; a reload brings
      back the caret and the draft; with the folders changing, find works but offers no Replace and changes nothing; a
      2 MB file mounts within a second, timed in the page around the mount to the frame after layout (about 30 ms on
      the dev Mac), draws its middle within 250 ms of a scroll, and takes typing at its end); the moved place and draft
      tests in test_files_ui.py and test_restore_tabs_ui.py, and the read-only ones in test_multi_folder_ui.py_
  - [x] 3.3 Docs and screenshots
    - `docs/usage.md` (Files and folders: editing, find and replace, leaving the editor by keyboard; Keyboard
      shortcuts), `docs/assets/editor-light.webp` and `editor-dark.webp`, `README.md` (its editing line).
    - _Requirements: 2.1, 2.3_
    - _Tests: none (documentation only)_
