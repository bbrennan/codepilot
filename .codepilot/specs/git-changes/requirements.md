# Requirements: git where you work

## Introduction

Roadmap 4, item 7. From the UI review of 2026-11-26:

- The Explorer shows no git state. A modified file, a new one and an untouched one look the same.
- The Changes view lists the working tree with git's raw codes (`??`, `M`, `D`), and nothing can be done there:
  committing or throwing a change away means the terminal. Clicking a deleted file shows an error.
- Roadmap 3 follow-up, still open: the main folder's list is parsed from `git status --short`, so a name with spaces or
  accents, or a rename, opens the wrong path (added folders already use `--porcelain -z`, #103).

Decided 2026-11-26: **Commit and Discard, with no staging area.** You tick files, write a message and commit; or
discard one file's changes. codepilot's own `git` tool stays read-only (`gitcmd.py`): these are your actions, made by
clicking, never the model's.

Out of scope: staging and unstaging, amend, push, pull, branches, stash, blame, a commit history view; folders that are
a subdirectory of a repository (as today, git features need the folder to be the repository's root).

## 1. Git state in the Explorer

**User story:** As the developer, I want to see what has changed while I look at files, so that I know what the last
turn touched without opening Changes.

1.1 A file with uncommitted changes SHALL show a letter at the end of its row and a matching name colour: M modified,
U untracked, A added, R renamed, and ! for a conflict.
1.2 A folder that contains such files SHALL show a dot, open or closed.
1.3 Marks SHALL be current within two seconds of a save, an applied or undone change, a commit, a discard, or a change
made in the terminal.
1.4 Each folder of the session SHALL show the state of its own repository; a folder that isn't one shows no marks.
1.5 Each mark SHALL have a text alternative ("modified") and SHALL NOT rely on colour alone.

## 2. A Changes list that reads plainly

2.1 The working-tree list SHALL use the same letters as the Explorer, each with a tooltip in words, and SHALL show
deleted files (D).
2.2 Names with spaces or non-ASCII characters, and renamed files, SHALL be listed with their real path and open it.
2.3 Clicking a deleted file SHALL open what was deleted as a diff, not an error.
2.4 Each file SHALL have a tick box, ticked by default, and the list SHALL say how many are ticked ("3 of 4").

## 3. Commit

**User story:** As the developer, I want to commit reviewed work from the Changes view, so that a good state is saved
before the next request.

3.1 WHEN the user writes a message and presses Commit (or ⌘Enter in the message box) THEN the system SHALL commit the
ticked files as they are on disk, including new and deleted ones, on the current branch.
3.2 Commit SHALL be unavailable with an empty message, with nothing ticked, or while the session is working, and SHALL
say which.
3.3 WHEN the commit succeeds THEN the list and the Explorer SHALL update, the message box SHALL clear, and a toast
SHALL give the short hash and the subject.
3.4 IF git refuses (a failing hook, no identity, a merge in progress with only some files ticked) THEN the system
SHALL show git's own message and SHALL leave the working tree as it was.
3.5 The system SHALL never push, amend, skip hooks, or change branch.

## 4. Discard

4.1 Each changed file SHALL offer Discard, which asks first, naming the file and saying what is lost.
4.2 WHEN confirmed THEN a tracked file SHALL return to its last committed state, and an untracked file SHALL move to
codepilot's trash.
4.3 The toast SHALL offer Undo, which puts the discarded content back unless the file has changed since.
4.4 IF the file is open with unsaved edits THEN the confirmation SHALL say they will be lost too; afterwards the open
tab SHALL show the file as it now is, or close if the file is gone.

## 5. Yours, not the model's

5.1 Commit and Discard SHALL be reachable only through the app's own requests (the localhost and header checks every
write endpoint has), and SHALL NOT be offered to the model as a tool or through its `git` tool.
5.2 Each folder that is its own repository SHALL have its own message box and commit to its own repository.
5.3 Paths sent with either action SHALL be accepted only if git lists them as changed in that repository.
