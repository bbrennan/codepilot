# Tasks

One branch and PR per numbered task. After keyboard-access task 2 (the tree's rows) and ui-review-fixes task 7
(colours).

- [x] 1. Git state in the Explorer and a plainer Changes list (`feature/git-marks`)
  - [x] 1.1 `gitwork.status`, and the main folder listed from it
    - Test first (unit): kinds; a name with a space and an accent; a rename; the `git` endpoint's `files`.
    - `codepilot/gitwork.py` (new), `server.py` (`git_view` wiring); `docs/architecture.md` (module table).
    - _Requirements: 2.2, 1.4_
    - _Tests: tests/test_gitwork.py (each kind named, a conflict, spaces and accents, each file of a new folder even
      with `status.showUntrackedFiles=no`, a very large untracked tree counted not listed, no optional locks: the index
      isn't rewritten where plain `git status` would, a rename keeps its old name, not a repository); tests/test_server.py
      (the main folder's `files` by real name and kind, `total`, `dirs`; an added folder's files carry their kind).
      `folders.git_status`'s test moved to test_gitwork.py with the parser_
  - [x] 1.2 The Changes list moves to `gitview.js` with letters, tooltips and deleted files that open a diff
    - Test first (Playwright): the letters and their tooltips; the file with spaces opens; a deleted file opens the
      diff.
    - `static/gitview.js` (new: `renderGitView`), `index.html`, `app.js` (`loadGit` calls it; `openGitDiff(path)`),
      `folders.js` (`addedGit` uses the same renderer), `app.css`.
    - _Requirements: 2.1, 2.2, 2.3_
    - _Tests: tests/e2e/test_git_changes_ui.py (each letter with its word as a tooltip and in the name, "new.py,
      untracked"; a name with spaces opens by click and by Enter; a deleted file, on disk or `git rm`'d, opens the diff
      scrolled to it, and a reload reopens it there; a clean tree says so; an added folder's rows read the same way;
      the keyboard audit on the list; rows fit at 1024×700 with a 180 and a 200px sidebar);
      test_multi_folder_ui.py (an added folder's new folder is listed file by file);
      test_keyboard_access_ui.py's audit decorates what was just drawn first, as a key would_
  - [x] 1.3 Marks on files and folders in the Explorer
    - Test first (Playwright): marks and the folder dot; a mark appears after a save and after an applied change, and
      goes after Undo; an added folder's marks; each mark's text alternative.
    - `static/gitview.js` (`state.git`, `markTree`), `app.js` (`renderTree` ends with one call; `checkDisk` calls
      `loadGitSoon` when an open file's mtime changes), `app.css`.
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_
    - _Tests: tests/e2e/test_git_changes_ui.py (letters, colours by `data-git`, a dot on open and closed folders,
      "core.py, modified" and "agent, contains changes" as names; one roving Tab stop and type-ahead unchanged, and the
      audit; a save, an applied change and its Undo; a commit and a reset in the terminal, seen at the next disk check;
      an open file changed in place; an added folder's marks and its root's dot; marks fit at 180 and 200px. They failed
      with `markTree` stubbed out, as it came with `renderGitView` in 1.2); tests/test_gitwork.py (the stamp changes
      with staging and a commit made outside, never reads outside the repository); tests/test_server.py (`/stat`
      answers each of the session's repositories' stamps, null for another folder)_
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
