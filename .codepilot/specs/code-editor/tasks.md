# Tasks

One branch and PR per numbered task. After ui-review-fixes task 2 (`place.js`) and spec restore-tabs.

- [ ] 1. Vendor CodeMirror 6 as one file (`feature/vendor-codemirror`)
  - [ ] 1.1 The recipe and the built bundle
    - Read the current CodeMirror docs first. `tools/codemirror/` (`package.json`, lockfile, `entry.js`, `build.sh`,
      `README.md`); run it; commit `static/vendor/codemirror.min.js` and `LICENSE-codemirror`.
    - Marked done as untested (a build output); 1.2 and task 2 exercise it.
    - _Requirements: 5.1, 5.2_
  - [ ] 1.2 Notices and hygiene
    - Test first (unit): every vendored script is in `THIRD_PARTY_NOTICES.md`; versions in `package.json` are exact.
    - `THIRD_PARTY_NOTICES.md`, `tests/test_repo_hygiene.py`; `docs/architecture.md` (Front end: the vendored list).
    - _Requirements: 5.2, 5.3_
- [ ] 2. Edit mode uses it (`feature/code-editor`)
  - [ ] 2.1 Test helpers, and the existing editor tests moved onto them
    - `tests/e2e/uihelpers.py` (`editor_text`, `type_in_editor`, `set_editor_text`); the six test files that use
      `#codeEdit`. They pass against the textarea first, so the swap in 2.2 is checked by tests that didn't change.
    - _Requirements: 3.1_
  - [ ] 2.2 `editor.js` and the swap in `renderEditTab`
    - Test first (Playwright): type, the unsaved mark, ⌘S, Done with and without edits; a blocked bundle.
    - `static/editor.js` (new: `loadEditor`, `mountEditor`, the handle), `index.html`, `app.js` (`renderEditTab`,
      `renderEditor`, `checkDisk`), `app.css` (`.code-edit` as a host; remove the textarea rules).
    - _Requirements: 3.1, 3.2, 3.3, 3.5, 4.5, 5.1_
  - [ ] 2.3 Languages, line numbers, indentation, brackets, history
    - Test first (Playwright): the cases in design.md; (unit-style, in the page) every `LANGS` key has an answer.
    - `static/editor.js` (`extensions`, `LANG_FOR`).
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_
  - [ ] 2.4 Theme from the app's tokens
    - Test first (Playwright): background, text and a keyword's colour equal the tokens in dark and light, and change
      with the toggle while the editor is open.
    - `static/editor.js` (theme, highlight style), `app.css` (search panel, gutter).
    - _Requirements: 4.1_
- [ ] 3. Find, replace, go to line, and the rest (`feature/code-editor-find`)
  - [ ] 3.1 Find and replace in the editor; go to line
    - Test first (Playwright): ⌘F, options, next and previous, replace, replace all and one undo; Ctrl+G.
    - `static/editor.js` (search extension, keys), `app.css`.
    - _Requirements: 2.1, 2.2, 2.3, 2.4_
  - [ ] 3.2 Place, drafts, read-only and large files
    - Test first (Playwright): the place and draft tests through the editor; read-only while folders change; 2 MB.
    - `static/editor.js` (`place`, `show`, the read-only compartment), `tabstate.js` (reads `tab.ed.place()`).
    - _Requirements: 3.4, 4.2, 4.3, 4.4_
  - [ ] 3.3 Docs and screenshots
    - `docs/usage.md` (Files and folders: editing, find and replace, keys), `docs/assets` (the editor, light and dark),
      `README.md` if it describes editing. `untested: documentation only`.
    - _Requirements: 2.1, 2.3_
