# Requirements: go anywhere from ⌘P

## Introduction

Roadmap 4, item 6 (Roadmap 3's "possible item 4"). From the UI review of 2026-11-26: ⌘P finds files and nothing else.
`>theme` and `handlers.py:300` both answer "No matching files." There is no list of what the app can do, so anything
without a button or a remembered shortcut is found by hunting through menus; an empty ⌘P shows an arbitrary list rather
than the files you were just in; and it refuses to open at all without a folder.

Out of scope: go to symbol (`@`), fuzzy search of file contents (that is the Search view), remappable shortcuts.

## 1. Files, faster

**User story:** As the developer, I want ⌘P to start from where I've been, so that going back to a file is two keys.

1.1 WHEN ⌘P opens with nothing typed THEN it SHALL list this folder's recently opened files, most recent first, with
the file opened before the current one on top (so ⌘P then Enter switches between two files).
1.2 WHEN the text ends in `:<number>` THEN Enter SHALL open the chosen file at that line; `:<number>` alone SHALL go to
that line in the file being shown.
1.3 ⌘P SHALL open without a folder; the files section then says to open one.

## 2. Commands

**User story:** As the developer, I want to type what I want to do, so that I don't need to know where its button is.

2.1 WHEN the text starts with `>` THEN the palette SHALL list commands, filtered as the user types, each with its
shortcut if it has one; ⇧⌘P SHALL open the palette with `>` already typed.
2.2 Enter SHALL run the command and close the palette; a command that can't run right now (Save with nothing being
edited, Stop with nothing running) SHALL NOT be listed.
2.3 The commands SHALL cover at least: the three pane toggles and the theme; each sidebar view; new session, new file,
new folder, add folder, new terminal; save, close tab, close other tabs; run tests, run checks; stop; review changes,
apply all; compact now; each mode; each model tier; report a problem; restart the server.
2.4 A script SHALL add a command by registering it, with no change to the palette's own code.

## 3. Sessions

3.1 WHEN text is typed without a prefix THEN, after the files, the palette SHALL list up to five sessions whose title
or folder matches, under their own heading.
3.2 Enter on a session SHALL open it.
3.3 The palette's placeholder SHALL say what can be typed: a file name, `>` for commands, `:` for a line.
