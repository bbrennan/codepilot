# Tasks

One branch and PR per numbered task. After keyboard-access task 2 (the tree's rows) and ui-review-fixes task 7
(colours).

- [ ] 1. Git state in the Explorer and a plainer Changes list (`feature/git-marks`)
  - [ ] 1.1 `gitwork.status`, and the main folder listed from it
    - Test first (unit): kinds; a name with a space and an accent; a rename; the `git` endpoint's `files`.
    - `codepilot/gitwork.py` (new), `server.py` (`git_view` wiring); `docs/architecture.md` (module table).
    - _Requirements: 2.2, 1.4_
  - [ ] 1.2 The Changes list moves to `gitview.js` with letters, tooltips and deleted files that open a diff
    - Test first (Playwright): the letters and their tooltips; the file with spaces opens; a deleted file opens the
      diff.
    - `static/gitview.js` (new: `renderGitView`), `index.html`, `app.js` (`loadGit` calls it; `openGitDiff(path)`),
      `folders.js` (`addedGit` uses the same renderer), `app.css`.
    - _Requirements: 2.1, 2.2, 2.3_
  - [ ] 1.3 Marks on files and folders in the Explorer
    - Test first (Playwright): marks and the folder dot; a mark appears after a save and after an applied change, and
      goes after Undo; an added folder's marks; each mark's text alternative.
    - `static/gitview.js` (`state.git`, `markTree`), `app.js` (`renderTree` ends with one call; `checkDisk` calls
      `loadGitSoon` when an open file's mtime changes), `app.css`.
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_
- [ ] 2. Commit (`feature/git-commit`)
  - [ ] 2.1 `gitwork.commit` and its endpoint
    - Test first (unit): the cases in design.md; the endpoint; 409 while busy; a path not in status.
    - `codepilot/gitwork.py`, `server.py` (route, wiring); `tests/test_tools.py` (the model's tool is unchanged).
    - _Requirements: 3.1, 3.4, 3.5, 5.1, 5.3_
  - [ ] 2.2 Tick boxes, the message box and Commit
    - Test first (Playwright): tick and untick, the count, commit of a subset, the toast, the disabled reasons, a
      refused commit, ⌘Enter, an added folder's own box.
    - `static/gitview.js`, `app.css`.
    - _Requirements: 2.4, 3.1, 3.2, 3.3, 3.4, 5.2_
- [ ] 3. Discard (`feature/git-discard`)
  - [ ] 3.1 `gitwork.discard`, the kept copy, and Undo through the trash
    - Test first (unit): each kind of change; Undo; Undo refused after the file changed.
    - `codepilot/gitwork.py`, `server.py` (route; `restore` for `kind: "discard"`).
    - _Requirements: 4.2, 4.3, 5.1, 5.3_
  - [ ] 3.2 Discard in the list, with its confirmation, Undo and the open tab following
    - Test first (Playwright): the confirmation's wording for tracked, untracked and a tab with unsaved edits; the tab
      reloads or closes; Undo.
    - `static/gitview.js`.
    - _Requirements: 4.1, 4.2, 4.3, 4.4_
  - [ ] 3.3 Docs
    - `docs/usage.md` (Changes: a new "Committing and discarding" part; Files and folders: the marks),
      `docs/security.md` (what the UI's git actions can and can't do, and that the model can't reach them),
      `README.md` feature list if it names Changes. Marked done as untested (documentation only).
    - _Requirements: 3.5, 5.1_
