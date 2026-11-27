# Requirements: a real editor in Edit mode

## Introduction

Roadmap 4, item 5. From the UI review of 2026-11-26: clicking **Edit** swaps the highlighted view for a plain
`<textarea>` (`renderEditTab`, app.js:739). While editing there is no syntax highlighting, no line numbers, no
auto-indent, no bracket matching, and no find or replace beyond the browser's own. For the changes codepilot proposes
that doesn't matter; for the small edits you make yourself between turns it is the weakest part of the IDE.

Decided 2026-11-26: vendor **CodeMirror 6** (MIT), built once into a single file in `static/vendor/`, as xterm.js and
Mermaid are. The app keeps its rule: no build step to run it, no framework, classic scripts.

What stays: the read view (highlight.js, with the gutter you click to reference lines) and the Edit / Done switch;
Save, the unsaved mark, the check for changes on disk, line endings and the non-UTF-8 refusal, all as they are.

Out of scope: completion popups, a language server, a minimap, split editors, soft wrap, and using CodeMirror for the
read view (see design.md, Decisions).

## 1. Editing code

**User story:** As the developer, I want Edit mode to behave like a code editor, so that a ten-line fix by hand is
comfortable.

1.1 The editor SHALL highlight the languages the read view highlights today, and show plain text for any other file.
1.2 The editor SHALL show line numbers and highlight the caret's line.
1.3 WHEN Enter is pressed THEN the new line SHALL keep the current indentation, and indent further after a line that
opens a block (a Python `:`; an opening bracket).
1.4 Tab SHALL indent and Shift+Tab SHALL dedent the selected lines, with the file's own unit (a tab if the file uses
tabs, else four spaces), as `indentUnit` decides today.
1.5 The editor SHALL match brackets, keep its own undo and redo history (⌘Z, ⇧⌘Z), and support several cursors.

## 2. Finding your way in a file

2.1 ⌘F SHALL open find and replace inside the editor, with match case, whole word and regular expression; Enter and
⇧Enter SHALL go to the next and previous match; Escape SHALL close it and return to the text.
2.2 Replace and Replace all SHALL change the text as one undoable step each.
2.3 Ctrl+G SHALL ask for a line number and go to it.
2.4 The same keys SHALL NOT trigger the browser's own find while the editor has focus.

## 3. What Edit mode already does keeps working

3.1 ⌘S SHALL save; the tab SHALL show the unsaved mark exactly while the text differs from the file; Done SHALL ask
before discarding unsaved edits.
3.2 A file changed on disk while being edited SHALL be handled as today: unsaved edits are kept, and Save asks before
overwriting.
3.3 The file's line endings SHALL be kept on Save, and a file that isn't UTF-8 SHALL still be refused.
3.4 WHILE the session's folders are changing THEN the editor SHALL be read-only, as the textarea is today.
3.5 Markdown files SHALL keep Preview of the draft, and steering docs outside the workspace SHALL still be editable.

## 4. It fits the app

4.1 The editor SHALL follow the app's theme (dark, light, and the toggle while it is open), using the app's colour
tokens for text, selection, gutter and syntax.
4.2 Edit, Done and tab switches SHALL keep your place (the top line and caret), as specified in ui-review-fixes 2.1–2.3.
4.3 Unsaved edits and the place SHALL be stored and restored as in spec restore-tabs.
4.4 A 2 MB file (the largest the app opens) SHALL open in the editor in under a second and scroll smoothly.
4.5 IF the editor's file fails to load THEN Edit SHALL say so in a toast and leave the read view in place.

## 5. Vendored, not built

5.1 The editor SHALL be one file, `static/vendor/codemirror.min.js`, loaded only when Edit is first used; the app
SHALL work offline and SHALL need no build step to run or to test.
5.2 The recipe that produced the file (pinned versions, entry file, one command) SHALL be in the repo, outside the
Python package, and `THIRD_PARTY_NOTICES.md` SHALL list CodeMirror with its version and licence text.
5.3 No file under `codepilot/` other than that bundle SHALL import from a package manager, and `tests/test_no_mcp.py`
SHALL stay green.
