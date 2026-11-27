# Bug analysis: what the UI review of 2026-11-26 found broken

Roadmap 4, phase 1. Eight defects found by driving the real UI in a browser (scripted model, fresh profile, 1440×900,
light and dark). Each was reproduced and its cause read in the code. They are independent: one `fix/…` branch and one
PR each, in the order of `tasks.md`.

## Current behaviour

1. **Stop is off-screen while a turn runs.** Fresh profile (chat 440px wide), send any message. While it runs the row
   under the message box holds @, image, two switches, Steer, Queue and Stop: 471px of controls in a 396px row. Queue is
   cut ("Qu") and Stop sits at x=1479 in a 1440px window. There is no key for Stop.
2. **Edit loses your place.** Open a 1,125-line file and click **Edit**: the editor shows the last lines. Scroll the
   view to line 200 first: same. **Done** puts the view back at line 1.
3. **The active tab can be out of sight.** Open eight files: the tab of the file being shown is beyond the strip's
   right edge (x=1312 with the strip ending at 996), and so is the Review tab when it opens.
4. **A command that hasn't run reads "Ran".** "Ran `rm -rf build`" shows, with a spinner, while the command waits for
   approval. After **Deny** the row still says "Ran", now with a red error mark.
5. **A binary file opens as editable text.** `assets/data.bin` shows as 17 lines of symbols with an **Edit** button.
   You can type; Save is then refused (correctly). A Latin-1 text file behaves the same way.
6. **The Review tab's header breaks, and a change row shows prompt text.** (a) At default widths the "Open file" icon
   drops onto a row of its own under the path. (b) Expanding a change row in the chat shows
   `<steering name="python" source=… why='applies to *.py'> … </steering> Follow the steering above …`.
7. **Low-contrast text.** Dark: white on the accent buttons (Apply, Apply all, Run, Send) is 3.2:1. Light and dark:
   muted 11–12px text is 4.1–4.4:1 on the tinted surfaces; green and amber status text 3.7–4.4:1 in light; line numbers
   and key hints 2.3–2.8:1. (Light accent buttons pass at 4.5:1; the review said "both themes", which was wrong.)
8. **Small wording and layout slips.** A one-line file says "1 lines". Shortcuts are written three ways in one list
   (`⌘P`, `Alt+W`, `` Ctrl+` ``). In the status bar the "github off" icon touches its text. Search hits' line numbers
   don't line up (75… then 103…). A long path in Memory runs under the sidebar's edge. A stopped turn says "Stopped."
   live and "(stopped)" after a reload. **Add folder…** opens a dialog titled "Open folder".

## Expected behaviour

1.1 WHILE a turn runs, Stop, Steer and Queue SHALL each be wholly inside the message box, at every chat width from 300px
    (its minimum) and in windows from 1024×700 to 1440×900.
1.2 IF the row is too narrow for all its controls THEN it SHALL wrap; Send or Stop SHALL never be the control cut off.
1.3 WHEN the user presses ⌘. (Ctrl+. off macOS) while the shown session is working THEN the system SHALL stop it, as
    the Stop button does; Stop's tooltip SHALL name the key.
2.1 WHEN Edit is clicked THEN the editor SHALL show the line the view had at its top (within one line), with the caret
    on that line; a file viewed from its top SHALL open at line 1.
2.2 WHEN Done is clicked THEN the view SHALL show the line the editor had at its top.
2.3 WHEN the user returns to a file tab THEN it SHALL be scrolled where they left it, in the view and in the editor.
3.1 WHEN a tab becomes the active tab THEN it SHALL be wholly visible in the tab strip.
3.2 A mouse wheel over the tab strip SHALL scroll it sideways.
4.1 WHILE a call waits for approval its row SHALL read "Wants to run …" (or "Wants to run the tests", "Wants to open
    …"), with a waiting mark and no spinner.
4.2 WHEN it is approved THEN the row SHALL read as any running step ("Ran …" with a spinner, then its result).
4.3 WHEN it is denied THEN the row SHALL read "Didn't run …" with a neutral mark, not the red error mark; the same
    after a reload.
5.1 WHEN a file with a NUL byte in its first 8,000 bytes is opened THEN the tab SHALL say it's a binary file, with its
    size, and offer no Edit, Ask or text view; images open as images, as now.
5.2 WHEN a text file that isn't valid UTF-8 is opened THEN it SHALL be shown as now, with a line saying why it can't be
    edited here, and no Edit button.
6.1 The Review header's Apply, Reject (or Undo) and Open file SHALL stay together on one line wherever the diff pane can
    hold them, and in a narrower pane SHALL wrap among themselves rather than be cut off. (Corrected in task 6: the
    change list keeps 280px, so below an editor of about 460px the diff pane is narrower than the three buttons, 0px at
    a 280px editor; "one line at every editor width" can't hold there. small-windows covers the narrow Review tab.)
6.2 A change row's note SHALL show what the checks or the package guard found, and never a `<steering>` block.
7.1 Text on a solid accent button SHALL have a contrast of at least 4.5:1 in both themes.
7.2 `--muted`, `--ok`, `--warn`, `--err`, `--info` and `--accent`, used as text, SHALL reach 4.5:1 on `--bg-0` to
    `--bg-4`; `--faint` SHALL reach 3:1 on `--bg-0` to `--bg-3`. A test SHALL compute this from the stylesheet.
8.1 A one-line file SHALL say "1 line".
8.2 Shortcuts SHALL be written one way per platform everywhere (macOS `⌘P`, `⌥W`, `` ⌃` ``; elsewhere `Ctrl+P`,
    `Alt+W`).
8.3 The status bar's GitHub item SHALL be spaced like its neighbours; search hits' line numbers SHALL be right-aligned
    in one column per file; a long path in Memory SHALL wrap.
8.4 A stopped turn SHALL read "(stopped)" under the partial reply, live and after a reload alike.
8.5 The folder dialog opened to add a folder SHALL be titled "Add folder" and its button SHALL say "Add this folder".

## Root cause

1. `.composer-row` ([app.css:528](../../../codepilot/static/app.css)) is a flex row that doesn't wrap and whose children
   don't shrink. #f47344a added Steer and Queue to the busy state (`updateBusy`, app.js:1465) without making room, and
   Stop is last in the row, so it is the one pushed out. The tests pass because Playwright's `is_visible()` ignores
   clipping and `click()` scrolls first (test_auto_queue_ui.py:223).
2. `renderEditTab` (app.js:752–757) sets `ta.value` (caret at the end), then `ta.focus()` (scrolls to the caret), then
   `setSelectionRange(0, 0)`, which doesn't scroll back. `tab.scroll` is only written on blur, so the first Edit has
   nothing to restore. `renderFileTab` neither records nor restores a scroll position (only `renderDocTab` does).
3. `renderTabs` (app.js:511) rebuilds the strip and never scrolls the active tab into view.
4. `steps.js` words every step in the past tense when the call is announced, and nothing tells the row about the
   approval: `approval_needed` and `decideApproval` (app.js:893) only touch the "Waiting for your approval" line. Each
   awaiting tool carries its call id (`approval_view`, agent.py:646), which is the row's key in `state.toolEls`.
5. `files()` (server.py:775) returns `read_text(errors="replace")` for any file under 2 MB, and `openFile` special-cases
   only image extensions. The non-UTF-8 refusal (#63) happens at Save, after the typing.
6. (a) `.rv-main > .ed-bar` wraps on purpose (app.css:281, so a long path isn't cut), and the Open-file button is a
   flex child of its own after Apply and Reject, so it wraps alone. (b) `_run_tool` (agent.py:961–967) appends the
   steering docs to the tool's output for the model; `changeStepDone` (steps.js:60) keeps everything after the first
   line as the row's note.
7. Token values in `app.css`: dark `--accent` #5b8cff under `--accent-fg` #fff; `--muted` and the status colours chosen
   against `--bg-2` only; `--faint` used for text that has to be read (line numbers, key hints).
8. `lines.length + " lines"` (app.js:591); shortcut strings typed by hand in `welcomeHtml`, `pathMenu` and
   `fileMenuItems`; a `<span title>` inside `#sbGithub` that isn't a flex container (app.js:185); `.grep-hit b` has no
   width; no `overflow-wrap` on the notes path; the live notice "Stopped." (agent.py:949) against the stored
   `_(stopped)_` (agent.py:799); `fdHint` and the dialog's title are fixed text (app.js:2029, index.html).

## Unchanged behaviour

- Enter sends, or queues while working; ⌘Enter steers; Steer and Queue show whenever a turn runs.
- Save still refuses a file that isn't UTF-8: the server check stays, as the last line of defence.
- Steps that need no approval read as they do now; the raw tool output inside a step row is unchanged.
- The Review header still shows the whole path (it wraps rather than cuts).
- Font sizes and radii still come from the scale (`test_design_tokens_ui.py`); no new sizes.
