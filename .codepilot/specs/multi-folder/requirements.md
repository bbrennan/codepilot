# Requirements: several folders in a session

## Introduction

Roadmap 3, item 3. Owner, 2026-11-09: "I'm trapped in the workspace root folder. What if my workspace has multiple repos
or I want to reference a file outside my workspace. I cannot navigate directories without changing the entire
workspace." Today a session has one folder, and the Explorer, @-mentions, search and codepilot's tools all stop at it;
the title bar's folder button silently switches the whole session to another folder.

Decided 2026-11-09, after studying VS Code, Cursor, JetBrains, Zed, Codex and Claude Code (ROADMAP.md, "Research for
item 3"): a session has a **main folder** plus folders you **add**, saved with the session, with no workspace file. The
top complaint about every tool that has this is "only the first folder works", so every feature reaches every folder,
each with a test on the second folder.

Out of scope: a single file outside every folder without adding its folder (later, if wanted), settings per folder.

## 1. Folders belong to the session

**User story:** As the developer, I want to add another repo or folder to my session, so that codepilot and I can work
across them without switching sessions.

1.1 A session SHALL have a main folder and any number of added folders, saved with the session and kept across reloads
and restarts.
1.2 The title bar's folder button SHALL open a menu listing the session's folders (the main one marked), **Add
folder…**, and **Open folder in a new session…**; it SHALL no longer replace the session's folder without asking.
1.3 WHEN the user picks a folder to add THEN the system SHALL add it to the session; a folder already in it, inside one
of its folders, or that doesn't exist SHALL be refused with the reason.
1.4 The Explorer SHALL show each folder as a top-level entry, the main one first; its context menu SHALL offer
**Remove from session** (added folders) and **Make main folder**.
1.5 WHEN a session's folder no longer exists THEN the Explorer SHALL say so for that folder, with **Remove from session**.

## 2. codepilot works in every folder

2.1 codepilot SHALL be told the session's folders: relative paths are in the main folder, and files in added folders
are named by their full path.
2.2 codepilot's file tools (read, list, search, propose a change) SHALL work in every folder, and a change in an added
folder SHALL be reviewed, applied and undone as one in the main folder is.
2.3 Paths outside every folder SHALL still be refused, as today.
2.4 Opening, editing and saving a file in an added folder SHALL work from the Explorer.

## 3. Finding things in every folder

3.1 @-mentions, Go to file (⌘P) and the Search view SHALL find files in every folder, showing which folder each is in.
3.2 Steering files (`.codepilot/steering/`, `AGENTS.md`, `CLAUDE.md`, …) of added folders SHALL be read as the main
folder's are.
3.3 The Changes view SHALL list each folder's git working tree under its own heading.
