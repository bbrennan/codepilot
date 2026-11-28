# Design

## Backend: `codepilot/gitwork.py` (new)

The user's git actions, separate from `gitcmd.py` (what the model's read-only tool may run) so neither can grow into
the other. Functions take the repository's root and an injected `run(args, cwd, timeout)` (default: `subprocess.run`
with `procenv`'s non-interactive environment), so tests use real temporary repositories or a fake runner.

| Function | Behaviour |
|---|---|
| `status(repo)` | `git status --porcelain=v1 -z` through `folders.git_status` (already NUL-safe), plus `kind` per file: `modified`, `untracked`, `added`, `deleted`, `renamed`, `conflict`; a rename carries `from` |
| `commit(repo, message, paths)` | Checks every path is in `status` (5.3) and the message isn't blank. `git add -A -- <paths>`, then `git commit -m <message> -- <paths>`; when the paths are **all** the changed files, `git commit -m <message>` with no pathspec, so a merge can be concluded. Returns `{hash, subject}` from `git log -1 --format=%h%x00%s` |
| `discard(repo, path, keep)` | Checks the path is in `status`. `keep(bytes) -> trash_id` saves the current content first (when the file exists). Untracked or added: unstage if staged, then the file goes to the trash. Otherwise `git restore --source=HEAD --staged --worktree -- <path>` (a rename: both names, and the new file to the trash). Returns `{path, trash_id, gone}` |
| `GitError` | Carries git's stderr, trimmed to 2,000 characters, for 3.4 |

Never passed: `--no-verify`, `--amend`, `push`, `checkout <branch>`. Hooks run with a 120 s timeout; a timeout is a
`GitError` naming it. Before the add, `commit` notes which of the paths were already staged
(`git diff --cached --name-only`); if the commit then fails it runs `git reset -q --` on the ones it staged itself, so
a refusal leaves the index as it found it (3.4).

## Server (`server.py`, wiring)

- `git_view` builds the main folder's answer with `gitwork.status` too and returns `files: [{path, code, kind}]` beside
  `branch` and `diff`; the `status` text field goes once the page no longer reads it (2.2).
- `POST /api/sessions/{sid}/git/commit` `{folder?, message, paths}` and `POST …/git/discard` `{folder?, path}`.
  `folder` is the main folder when absent, else must be one of the session's added folders (`folders.added`). Both take
  `busy_lock` as `restore` does and answer 409 while the session is working (3.2); `GitError` is a 409 with git's text.
- Discard's `keep` writes a trash slot like `move_to_trash` (same folder, `meta.json` with `kind: "discard"` and the
  file's mtime after the discard). `fs`'s `restore` operation, for that kind, writes the content back when the file's
  mtime still equals the recorded one, or the file is still absent; otherwise 409 "changed since" (4.3).
- After either action `retire_stale_proposals` runs, as after any file operation.

## Front end: `static/gitview.js` (new, loaded after `app.js`)

`loadGit`'s list rendering moves here from `app.js` (app.js:1038–1052); `loadGit` keeps fetching, updates the status
bar's branch, and calls `renderGitView(g)`.

- **State:** `state.git = { files: Map<path, {code, kind}>, dirs: Set<path> }` for the main folder and each added one
  (added folders' paths are absolute in the tree, so their keys are `folder + "/" + path`). `dirs` holds every ancestor
  of a changed file.
- **Explorer marks (1.x):** `markTree()` runs at the end of `renderTree` and of `renderGitView`: for each `#tree .row`
  it adds `<span class="gmark" data-kind="modified" title="Modified" aria-label="modified">M</span>` before the
  hover button and sets `data-git` on the row (the name colour comes from CSS); folders in `dirs` get a dot with
  `title="Contains changes"`. Freshness is the existing loop: `checkDisk` → `loadGitSoon` on any tree change, `loadGit`
  after save, apply, undo; add `loadGitSoon()` when an open file's mtime changes, and after commit and discard.
- **Changes list (2.x):** per repository, under the existing heading: a tick box, the file icon and path, the letter,
  and a Discard button shown on hover and focus. A header row has a tick-all box and "3 of 4". Clicking a deleted
  file opens the working-tree diff tab scrolled to that file (`openGitDiff(path)`).
- **Commit box (3.x):** under each repository's list: a two-line `textarea.field` ("Message"), a primary **Commit**
  button with the count, and a hint line for why it is disabled. ⌘Enter in the box commits. On success: toast
  ``Committed abc1234: subject``, clear, `loadGit()`. On refusal: git's text in a `.banner.error` under the box.
- **Discard (4.x):** `confirmDialog("Discard changes to X?", …, "Discard")`; the hint says "back to the last commit"
  or "moved to codepilot's trash", and adds "Your unsaved edits in the open tab are lost too" when `tab.dirty`. Then
  the request; then `toast("Discarded changes to X", false, { label: "Undo", run })`; the open tab reloads
  (`tab.content = null; openFile`) or closes when `gone`.
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
