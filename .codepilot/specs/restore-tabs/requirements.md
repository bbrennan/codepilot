# Requirements: tabs and unsaved edits come back

## Introduction

Roadmap 4, item 2. From the UI review of 2026-11-26: a reload (or `make restart`, or the window closing) drops every
open editor tab, the Explorer's open folders and any unsaved edit, without a word. Terminals, the theme, the layout and
the conversation already survive. Switching to a session on another folder also drops file tabs, unsaved ones included
(`setWorkspace`, app.js:302), with no question asked.

Decided 2026-11-26: tabs and unsaved edits are saved in the browser and restored, like the terminals. No "Leave site?"
prompt, except when an edit could not be saved.

Out of scope: syncing tabs between two windows open on the same folder (the last one to change wins); undo history
across a reload; restoring the bottom panel's Activity log.

## 1. Tabs come back

**User story:** As the developer, I want the files I had open to be open when I come back, so that a reload or a
restart doesn't cost me my place.

1.1 WHEN the page loads or a session on a folder is opened THEN the system SHALL reopen that folder's tabs in their
order, with the same tab active: files, images, traces, specs, the Review tab and the working-tree diff.
1.2 Each file tab SHALL come back where it was: its top line, Preview or Source for Markdown, and its selected lines.
1.3 IF a tab's file no longer exists and it has no unsaved edit THEN the system SHALL leave that tab out, without an
error.
1.4 The Explorer SHALL come back with the same folders open.

## 2. Unsaved edits survive

**User story:** As the developer, I want an edit I haven't saved to still be there after a reload, so that I never
lose typing to a refresh.

2.1 WHEN a tab with unsaved edits is restored THEN it SHALL open in the editor with those edits, marked unsaved.
2.2 IF the file changed on disk since the edit was made THEN the system SHALL keep the edit, say so once, and ask
before overwriting on Save, as it does today for a file that changes while open.
2.3 IF the file was deleted since THEN the tab SHALL still be restored with the edit, saying the file is gone, and
Save SHALL write the file again.
2.4 IF an unsaved edit could not be stored (too large, or the browser's storage is full or blocked) THEN the browser
SHALL ask before the page is left; otherwise it SHALL NOT ask.

## 3. Folders and housekeeping

3.1 WHEN the user switches to a session on another folder THEN that folder's tabs SHALL replace the current ones, and
the current ones, unsaved edits included, SHALL be back when the user returns to a session on their folder.
3.2 Sessions on the same folder SHALL share one set of tabs, as today.
3.3 WHEN a tab is closed, or its edit is saved or discarded, THEN what was stored for it SHALL be removed.
3.4 Stored tabs for a folder not opened in 30 days SHALL be removed at startup.
