# Requirements: everything by keyboard

## Introduction

Roadmap 4, item 4. From the UI review of 2026-11-26. Focus rings are in place (#74) and native controls work, but much
of the app is `div`s with click handlers:

- The file tree can't be reached with Tab, and arrow keys do nothing in it. F2 and Delete work only after a mouse click
  (`treeFocused` in `app.js` is set on `mousedown`).
- Editor tabs, session rows, search hits, changed-file rows, the Review list, the welcome links and `path:line` links in
  replies are not focusable. A message's Edit, Retry and Undo exist only while the mouse hovers.
- Menus (File, Terminal, folder, help, right-click) are unlabelled `div`s: opening one leaves focus where it was, and
  arrow keys don't move in it. Dialogs have no dialog role, don't keep Tab inside, and don't give focus back.
- Nothing is announced: a finished turn, a waiting approval and every toast are silent to a screen reader.
- It takes about 40 Tab presses to get from the title bar to the message box.

(The review also listed step rows and change rows; those are `<summary>` elements and already work by keyboard.)

Also here, from Roadmap 3's follow-ups: the Changes icon's count badge replaces its accessible name.

Out of scope: a full screen-reader review of the transcript's reading order; remappable shortcuts; the terminal's own
keyboard handling (xterm.js) and the code editor's (CodeMirror, spec `code-editor`).

## 1. The file tree

**User story:** As the developer, I want to move through the Explorer with the arrow keys, so that I can open, rename
and delete files without the mouse.

1.1 The tree SHALL be one Tab stop; Up and Down SHALL move between visible rows, Home and End to the first and last.
1.2 Right SHALL open a closed folder, or move to its first child; Left SHALL close an open folder, or move to the
    parent.
1.3 Enter or Space SHALL open a file, or open or close a folder; typing letters SHALL move to the next row starting
with them.
1.4 F2, Delete (⌘⌫) and ⌘C SHALL act on the focused row; Shift+F10 or the menu key SHALL open its context menu.
1.5 WHEN the tree redraws (a file added, a folder opened) THEN focus SHALL stay on the same path.

## 2. Tabs and views

2.1 The editor's tab strip SHALL be one Tab stop: Left and Right move to and show the neighbouring tab, Home and End
the first and last, Delete closes the focused tab (asking first if it has unsaved edits).
2.2 Each tab's close button SHALL be named "Close <title>".
2.3 The bottom panel's tabs SHALL work the same way, and both strips and the activity bar SHALL say which item is
current to assistive technology.
2.4 Activity-bar buttons SHALL keep their names when they show a count ("Changes, 2 waiting for review").
2.5 F6 SHALL move focus to the next of sidebar, editor, bottom panel and chat (those shown), and Shift+F6 to the
    previous.

## 3. Menus and dialogs

3.1 WHEN a menu opens THEN focus SHALL move to its first item; Up, Down, Home, End and letters SHALL move in it; Enter
or Space SHALL run the item.
3.2 WHEN a menu closes by Escape or by running an item THEN focus SHALL return to what opened it.
3.3 WHEN a dialog opens (prompt, confirm, folder, report, Go to file) THEN focus SHALL move into it, Tab and Shift+Tab
SHALL stay inside it, and Escape SHALL close it.
3.4 WHEN a dialog closes THEN focus SHALL return to what opened it.
3.5 WHEN a confirmation is for something that can't be undone THEN Cancel SHALL have focus, not the confirming button.

## 4. Everything you can click

4.1 Every row that does something on click (sessions, search hits, changed files, Review list, specs, steering,
traces, welcome links, the context meter) SHALL be focusable and SHALL act on Enter or Space.
4.2 `path:line` links in replies SHALL be focusable and open the file on Enter.
4.3 A message's Edit, Retry and Undo SHALL be reachable with Tab and visible while focus is on them.
4.4 The @, / and # suggestion lists SHALL say which option is current to assistive technology.
4.5 A test SHALL fail when a visible element that responds to a click is not focusable.

## 5. Being told

5.1 WHEN a turn finishes, or needs an approval, or stops with an error THEN the system SHALL announce it once.
5.2 Every toast SHALL be announced: errors at once, the rest politely.
5.3 Streamed reply text SHALL NOT be announced word by word.
