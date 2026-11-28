# Design

## Backend: `codepilot/gitwork.py` (new)

The user's git actions, separate from `gitcmd.py` (what the model's read-only tool may run) so neither can grow into
the other. Functions take the repository's root and an injected `run(argv, cwd, timeout)` (default: `procenv.run`,
non-interactive, killed as a process group on timeout), so tests use real temporary repositories or a fake runner.

Every command starts `git --no-pager --no-optional-locks --literal-pathspecs`. **No optional locks:** the status runs
in the background (each poll that sees a change, every list redraw), and a plain `git status` rewrites the index when it
can, which would get in the way of a `git` command typed in the terminal at that moment. **Literal pathspecs:** git
reads `*`, `?`, `[` and a leading `:` in a path argument as a pattern or "magic", so `git add -- a*.txt` would also
add `ab.txt`, and `:notes.txt` wouldn't match at all; a path the user ticked is always just a name.

| Function | Behaviour |
|---|---|
| `changes(repo)` | Every changed file: `git status --porcelain=v1 -z --untracked-files=all`, parsed by `parse_status` (moved here from `folders.git_status`, which skipped a rename's old name) with `kind` per file: `modified`, `untracked`, `added`, `deleted`, `renamed`, `conflict`; a rename carries `from`. `--untracked-files=all` is explicit: without it git lists a new folder as one `dir/` entry (marks, ticks and Discard need each file), and a `status.showUntrackedFiles` setting could hide them or change the answer |
| `status(repo)` | What the page gets: `{files, total, dirs}`, None when the folder isn't a repository's root. At most `LIMIT` (2,000) files, tracked changes first; `total` counts them all and `dirs` holds every folder that contains a change (the shallowest first, at most 10,000). **A very large untracked tree** (an un-ignored `node_modules` or `.venv`: 50,000 files is 0.3 s and 2 MB of git output) is counted, not listed: the list says "2,000 of 51,204 changed files shown" and that such a folder usually belongs in `.gitignore`; its folders still carry their dot. Commit and Discard check paths against `changes`, not this capped list |
| `stamp(repo)` | For the disk poll: the size and mtime of the index, `HEAD`, the branch `HEAD` names (`refs/heads/<branch>`; a commit moves that, not `.git/HEAD`) and `packed-refs`. Stat only, no git process, never a path outside the repository's git directory (a worktree's `.git` file and `commondir` are followed) |
| `commit(repo, message, paths)` | Checks every path is in `changes` (5.3; never the page's capped list) and the message isn't blank. A rename's old name goes with it. `git add --all -- <the names on disk or in the index>`, then `git commit --quiet --cleanup=verbatim --message <message> -- <paths>`; when the paths are **all** the changed files, no pathspec, so a merge can be concluded. **The message is yours, exactly:** `--cleanup=verbatim` (git would otherwise strip `#` lines, trailing spaces and blank lines, whatever `commit.cleanup` says), nothing appended (no trailer, no sign-off), and your own git identity (no `-c user.*`, no `GIT_AUTHOR_*`). Returns `{hash, subject}` from `git log -1 --format=%h%x00%s` |
| `discard(repo, path, kept)` | Checks the path is in `changes`. `kept` (`gitkeep.Kept`) first **moves** the file, if there, into codepilot's trash: never reads it into memory, never follows a symlink (the link itself moves), and resolves names through the server's own `workspace_path`, as every other file operation does. Then, by whether the **last commit has each name** (`ls-tree HEAD`, not the status letter): a name it hasn't (untracked, added, a rename's new name) leaves the index (`rm --cached --ignore-unmatch`); a name it has goes back, index and working tree (`restore --source=HEAD --staged --worktree`). A rename: both names. If git fails, the file is put back. A folder (a submodule) is refused. Returns `{path, names, were_absent, gone}` |
| `GitError` | Carries git's stderr, trimmed to 2,000 characters, for 3.4 |

Never passed: `--no-verify`, `--amend`, `push`, `checkout <branch>`. Hooks run with a 120 s timeout; a timeout is a
`GitError` naming it, and the index locks that the killed commit left (`index.lock`, `next-index-*.lock`, only those
made since it started) are removed, or every git command after it would fail. **A refusal leaves the index as it found
it (3.4):** before the add, `commit` saves the ticked paths' index entries (`git ls-files -s -z`, stage numbers and
all); if git refuses, it writes exactly those back (`git update-index -z --index-info`, each path first taken out).
Resetting only the paths it staged itself (the first design) would lose a partly staged file's staged version and a
conflict's three stages. `procenv.run` takes an optional `input` for this; stdin stays closed otherwise.

## Server (`server.py`, wiring)

- `git_view` builds the main folder's answer with `gitwork.status` too and returns `files: [{path, code, kind,
  from?}]`, `total` and `dirs` beside `branch` and `diff`; the `status` text field is gone (2.2). Its other git calls
  (branch, diff) take no optional locks either. The diff is against `HEAD` (before the first commit, the index), not
  the index: there's no staging area here, and a `git rm`'d file is only in the former (2.3).
- `stat_paths` (the disk poll, `/stat`) takes `git: [".", <added folder>, …]` and answers `gitwork.stamp` for each:
  covers a commit, staging, a reset or a checkout made in the terminal (1.3), which change no working file.
- `POST /api/sessions/{sid}/git/commit` `{folder?, message, paths}` and `POST …/git/discard` `{folder?, path}`.
  `folder` is the main folder when absent, else must be one of the session's added folders by its full path
  (`folders.repo_for`: never a folder inside one, or any other path; a 400). Both go through one `git_action`: it takes
  `busy_lock` as `restore` does, marks this session busy for the action (no turn starts meanwhile), and answers 409
  **while any session whose folders include that repository is working** (`folders.uses`): sessions can share a
  folder, and a turn in another one may be between two writes too. **A turn paused for an approval counts as
  working**: it hasn't finished (the server no longer marks it busy, so `pending` is checked too). `GitError` is a 409
  with git's text. The `/git` answer carries `working` per repository, so the page can say why before you press.
- Discard's kept copy is a trash slot like `move_to_trash`'s (same folder; `codepilot/gitkeep.py`, not more of
  `server.py`): the moved item, and `meta.json` with `kind: "discard"`, the repository, the name as the tree shows it,
  each touched name's state after the discard (its mtime and size, or absent), and the names it brought back from the
  last commit. `fs`'s `restore` operation, for that kind, checks the repository is still one of the session's folders,
  then puts the item back and removes what the discard brought back, only if every touched name is as the discard
  left it; otherwise 409 "changed since", and the kept copy stays (4.3). Undo restores files, not the index: a staged
  file comes back unstaged.
- After either action `retire_stale_proposals` runs, as after any file operation.

## Front end: `static/gitview.js` (new, loaded after `app.js`)

`loadGit`'s list rendering moves here from `app.js` (`loadGit`, and the added folders' `addedGit` from `folders.js`);
`loadGit` keeps fetching, updates the status bar's branch, and calls `renderGitView(g)`. Loaded after `folders.js`.

- **State:** `state.git = { files: Map<path, {code, kind, from?}>, dirs: Set<path>, roots: Set<folder> }` for the main
  folder and each added one (added folders' paths are absolute in the tree, so their keys are `folder + "/" + path`).
  `dirs` comes from the server (complete even when the file list is capped); `roots` are the session's folders whose
  repository has changes, for the dot on a folder's own row (folders.js).
- **Explorer marks (1.x):** `markTree()` runs at the end of `renderTree` and of `renderGitView`: for each `#tree .row`
  it adds `<span class="gmark" data-kind="modified" title="Modified" aria-hidden="true">M</span>` before the hover
  button and sets `data-git` on the row (the name colour comes from CSS); folders in `dirs` get a dot with
  `title="Contains changes"`. The rows are `treeitem`s with one roving Tab stop (keyboard-access, #129): a mark is never
  focusable and never a tab stop, and type-ahead still matches `.name` only. A row's name comes from its content, and a
  mark inside a flex row would read "core.py , modified"; so the marked row gets `aria-label="core.py, modified"`
  ("agent, contains changes"), removed again when the mark goes (1.5). Freshness: `checkDisk` → `loadGitSoon` on any
  tree change (as before), and `loadGit` when a repository's `stamp` or an open file's mtime changes (an edit in place
  changes no folder's stamp); `loadGit` after save, apply, undo, commit and discard.
- **Changes list (2.x):** per repository, under the existing heading: a tick box, the file icon and path, the letter,
  and a Discard button shown on hover and focus. A header row has a tick-all box and "3 of 4". Clicking a deleted
  file opens the working-tree diff tab scrolled to that file (`openGitDiff(path)`); `openGitDiff()` with no path, as
  "View working tree diff" and `tabstate.js` call it, still opens it at the top, and `tabstate.js` records the path so
  a reload reopens it there. **A row holds controls, so the row itself isn't a button:** `a11y.js` made every
  `#gitList .row` a `role=button`, and a button can't contain a tick box or Discard. The row is a plain container with
  one Tab stop per control: the tick box, the name (a `<button class="gname">`, named "core.py, modified"), and
  Discard. `a11y.js`'s selector becomes `#gitList #openGitDiff`, and the keyboard audit (#128) still passes. Focus
  stays where it was when the list redraws after a tick, a commit or a discard (task 2, 3).
- **Fit (1024×700):** since #126 the sidebar is 200px wide at 1024×700 (`layout.js` fits it to 186px there) and can be
  180px. Names ellipsize; the letter, the tick box and Discard keep their width; each row stays one line inside the
  list. Tested as geometry (rectangles inside rectangles) at 180 and 200, never a font's width.
- **Commit box (3.x):** under each repository's list: a two-line `textarea.field` ("Message", named "Commit message
  for api"), a primary **Commit** button with the count ("Commit 3", `aria-describedby` its reason), and a hint line
  for why it is disabled: "Write a message to commit.", "Tick at least one file to commit.", "codepilot is working:
  commit when the turn is done." (this session streaming, an approval waiting, or `working` from the server).
  **⌘Enter in the box commits, or does nothing when Commit is unavailable, and never approves:** `app.js`'s global
  handler approves a waiting command on ⌘Enter wherever focus is, so the box's own handler stops the event. On
  success: toast ``Committed abc1234: subject``, clear, `loadGit()`, focus back in the box. On refusal: git's text in a
  `.banner.error` (`role="alert"`) under the box; the message is kept. Ticks (the unticked, per repository), the
  message and the refusal live outside the DOM, so a redraw keeps them; the count, the tick-all box and Commit update
  in place on each tick and keystroke, never by redrawing. **Focus through a redraw** (a tick, a commit, a discard, a
  poll): the focused control is found again by its data attribute, a message box keeps its selection, and a control
  whose row went moves to the same control in the row that took its place, else to the message box.
- **Discard (4.x):** a button per row (`aria-label="Discard changes to X"`), seen on hover and focus but always there
  (opacity, not `display`), so it's a Tab stop in both directions. `confirmDialog("Discard changes to X?", …,
  "Discard")`, starting on Cancel; the hint says "goes back to the last commit", "moves to codepilot's trash", "comes
  back as it was in the last commit" (a deleted file) or both (a rename), and adds "Your unsaved edits in the open tab
  are lost too" when `tab.dirty`. Then the request; then `toast("Discarded changes to X", false, { label: "Undo", run
  })`. **The open tab follows** (`gitTabFollows`): its draft is forgotten (`tab.dirty = false`, `saveTabs()` at once,
  so the draft stored for restore by #125 goes too), and it shows the file as it now is, through the editor's handle
  (`tab.ed.setText`) in Edit mode (#134), or closes without asking when `gone`. Undo does the same with what comes
  back. Focus goes to the next row's Discard.
- Colours: `--warn` modified, `--ok` untracked and added, `--err` deleted and conflicts, from the tokens fixed in
  ui-review-fixes task 7.

## Decisions

- **No staging area.** Ticks are the selection; `git add` happens at commit. One less state to show, test and explain.
- **Commit is refused while a turn runs.** The agent may be between two writes of one change.
- **Discard keeps a copy.** It is the one action here that destroys work, so it gets the same trash as Delete, and an
  Undo that refuses rather than overwrite something newer.
- **A second module, not a flag on the model's tool.** `gitcmd.py` answers "what may the model run"; nothing in
  `gitwork.py` is importable from `tools.py`, and a test says so.

## Tests

- `tests/test_gitwork.py` (new, temporary repositories): status kinds, a name with a space and an accent, a rename;
  commit of a subset leaves the rest uncommitted and anything staged before still staged; a new and a deleted file;
  blank message and a path not in status refused; a failing `pre-commit` hook raises with its output and leaves the
  index as before; concluding a merge with all files ticked, and the refusal with a subset; discard of modified,
  staged, untracked, deleted and renamed files; the kept copy.
- `tests/test_server.py`: both endpoints; 409 while busy; an added folder; a folder not in the session refused; Undo
  after discard, and its refusal once the file changed; the missing-header 403 the middleware already gives.
- `tests/test_tools.py`: the `git` tool still refuses `commit`, `add`, `restore` and `reset`; `tools.py` doesn't import
  `gitwork`.
- `tests/e2e/test_git_changes_ui.py` (new): marks on a modified and an untracked file and the dot on their folder,
  gone after a commit; a file saved in the editor gains its mark; `notes with spaces.txt` opens; a deleted file opens
  the diff; untick one, commit, the toast and the remaining row; Commit disabled with its reason (no message, nothing
  ticked, a slow turn running); a refused commit shows the hook's text; Discard, the tab reloading, Undo; an added
  folder with its own repository commits there.

## Corrected while building

The spec was written before roadmap items 1–6 merged. What changed, and why:

- **By name, not line numbers.** `app.js:1038–1052` had moved; the design names functions (`loadGit`, `addedGit`).
- **Each untracked file, explicitly.** Today's call listed a new folder as one `dir/` entry; `changes` asks for
  `--untracked-files=all`, so a user's `status.showUntrackedFiles` can't change the answer. A very large untracked tree
  is counted, not listed (`status`, above).
- **Literal paths.** `*`, `?`, `[` and a leading `:` are patterns to git; every `gitwork` command passes
  `--literal-pathspecs`.
- **git's own state in the poll.** `/stat` watched folders and open files, not `.git`, and a commit in the terminal
  changes no working file. It now stamps each repository's index, `HEAD` and the branch `HEAD` names (a commit
  doesn't touch `.git/HEAD` itself). The background status never takes optional locks.
- **The working-tree diff is against `HEAD`**, so a staged deletion shows (2.3).
- **The parser moved** from `folders.git_status` (which dropped a rename's old name) to `gitwork.parse_status`.
- **Rows and focus** (`a11y.js`): see the Changes list and the Explorer marks above.
- **⌘Enter in a message box** commits or does nothing; it never reaches `app.js`'s approve-on-⌘Enter.
- **"While the session is working"** means any session whose folders include that repository, running or paused for
  an approval.
- **A commit is yours:** the message verbatim (`--cleanup=verbatim`), nothing appended, your git identity.
- **A refusal restores the index exactly** (saved entries written back), not by resetting what was staged; a hook
  stopped on its timeout leaves no lock behind.
- **Discard's kept copy is moved, not read** (`keep(bytes)` would have read every file into memory), through the same
  path checks as the other file operations, and a symlink is moved as a link. Whether a name goes back or leaves is
  decided by the last commit, not the status letter (a conflict, a staged deletion and a rename all fit).
- **The open tab after a discard** forgets its stored draft and shows the file through the editor's handle, rather
  than `tab.content = null; openFile` (which kept the draft, and with it the unsaved edits, for the next reload).
- **A late git answer for a session you've left is dropped** (`loadGit`): drawn, it showed the old folder's files, or
  threw while the page had no folder.
- **Known limit (1.3):** an in-place edit, in the terminal, of a file that is neither open nor already changed changes
  no folder's stamp and no git state, so its mark waits for the next thing that reloads the list (a save, a turn, a
  tree change, the Changes view, ↻). Running `git status` on every poll would cover it, at a cost that grows with the
  repository; not done.
