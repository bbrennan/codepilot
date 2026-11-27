# Design

Eight small fixes. Each is a regression test that fails on today's code, then the smallest change that passes it.
`app.js` gets wiring only (a call, a changed line); anything with logic goes in a small new script, loaded after
`app.js` and listed in `index.html`, `docs/architecture.md` and CI's `node --check` loop (which already globs
`static/*.js`).

## 1. The busy row (fix/stop-visible)

- `index.html`: group the row's children: `.composer-opts` (the two switches) and `.composer-acts` (Steer, Queue, Send,
  Stop). @ and image stay first.
- `app.css`: `.composer-row { flex-wrap: wrap; row-gap: 4px; }`, `.composer-acts { display: flex; gap: 8px; flex: none;
  margin-left: auto; }`, `.composer-opts { display: flex; gap: 8px; flex: 0 1 auto; min-width: 0; }`. When the row is
  short, `.composer-acts` moves to a second line as a whole, right-aligned. The box grows by one line only when needed;
  the composer's existing `max-height: 78%` and `test_layout_ui.py` keep the box on screen.
- Shorter busy placeholder so it isn't cut at 440px: `Working… Enter queues · ⌘Enter steers`.
- Stop by key: in the document `keydown` handler, `mod + "."` while `state.streams.has(state.sid)` clicks `#stopBtn`.
  `#stopBtn.title = "Stop (⌘.)"` through the key-label helper once task 8 lands; plain text until then.
- Rejected: hiding the switches while busy (they'd jump in and out each turn); an Esc shortcut (Esc already closes
  popups, and a stray Esc would end a long turn).

## 2. One place per file tab (fix/edit-keeps-place)

`static/place.js` (new, ~25 lines): `LINE = 20` (the px line height of `.code-view` and `.code-edit`),
`topLine(scrollEl)` → `Math.floor(scrollEl.scrollTop / LINE) + 1`, `showLine(scrollEl, n)`, `lineStart(text, n)` → the
character offset of line `n`. A tab keeps one `tab.topLine`, shared by the view and the editor.

- `renderFileTab`: after rendering, `showLine($("#edScroll"), tab.topLine)` unless `tab.flash` is set (a jump to a line
  wins and then becomes `topLine`); `#edScroll.onscroll` records `tab.topLine`.
- `renderEditTab`: set the value, `setSelectionRange` **before** focusing, `ta.focus({ preventScroll: true })`, then
  `showLine(ta, tab.topLine)`. The caret is the saved `tab.caret`, else `lineStart(value, tab.topLine)`. `ta.onscroll`
  records `tab.topLine`; drop `tab.scroll` for file tabs (the Markdown preview keeps its own pixel scroll).
- `checkDisk`'s reload-in-place (app.js:367) uses the same helper instead of its own scrollTop copy.

## 3. The active tab (fix/active-tab-in-view)

End of `renderTabs`: `$("#editorTabs .tab.on")?.scrollIntoView({ block: "nearest", inline: "nearest" })`. A `wheel`
listener on `#editorTabs` adds `deltaY` to `scrollLeft` when `deltaX` is 0. The strip element isn't replaced by a
render, so its scroll position already survives one.

## 4. Steps that wait (fix/step-wording)

`steps.js` gets `WAITING_TEXT` beside `STEP_TEXT` (run_command, run_tests, run_checks, github, open_workspace; default
`["Wants to use", name]`) and three functions: `stepWaiting(el, ev)`, `stepApproved(el)`, `stepDenied(el)`. They change
the row's `.tverb` and `.st` only. A waiting row gets class `waiting` and the alert icon; a denied row class `denied`,
the ✕ icon in `--muted`, verb "Didn't run".

- `render()` `approval_needed`: for each `ev.tools[i].id`, `stepWaiting(state.toolEls.get(id), tool)`.
- `decideApproval(approve)`: `stepApproved` or `stepDenied` for the same ids (kept in `state.approval.tools`).
- Reload: a denied call's stored result starts "The user declined this tool call" (agent.py:611). In `tool_result`,
  when `ev.is_error` and the output starts with that text, call `stepDenied(el)` instead of drawing the error mark.

## 5. What kind of file (fix/binary-files)

- `textfile.py`: `kind(path) -> "text" | "binary" | "not-utf8"`: binary when the first 8,000 bytes contain `\0` (git's
  rule); else not-utf8 when `read()` raises `NotUTF8`; else text.
- `server.py` `files()`: for binary, `{"path", "binary": true, "size", "mtime"}` and no content; for not-utf8, the
  content as now plus `"encoding": "not-utf8"`.
- `static/filekinds.js` (new): `renderBinaryTab(tab)` (name, size, "Binary file: not shown as text", Copy path) and
  `encodingNote(tab)` (one line under the bar). `openFile` opens a binary answer as `kind: "binary"`; `renderEditor`
  dispatches it; `renderFileTab` leaves out Edit when `tab.encoding` is set and adds the note.

## 6. Review header and change notes (fix/review-header)

- `renderReviewTab`: wrap `propActions(p)` and `#rvOpen` in `<span class="rv-acts">`; CSS `display: inline-flex; gap:
  6px; flex: none`. They wrap together under the path when it is long. (Task 6 added `flex-wrap: wrap; max-width:
  100%`, so a diff pane narrower than the three wraps them among themselves instead of cutting them off.)
- `steps.js`: `readerNote(text)` removes `<steering …>…</steering>` blocks and the line "Follow the steering above when
  working on these files."; `changeStepDone` stores `readerNote(m[2])`. The "steering: …" chip already says which docs
  loaded. The agent is untouched: the model still gets the steering.

## 7. Contrast (fix/contrast)

Token values only, both themes (dark `:root`, light in the media query and under `[data-theme="light"]`: the two light
blocks must stay identical).

- New `--accent-fill` and `--accent-fill-2` for solid buttons (`.btn.primary`, `.send`, `.badge`), separate from
  `--accent`, which stays the colour of links, focus rings and selection. Starting points to check with the test: dark
  #3e6fe6 / #325fd0, light #3a68de / #2f5dd4.
- Darken or lighten `--muted`, `--ok`, `--warn`, `--accent` (as text) and `--faint` until the test passes. Starting
  points: dark `--muted` #8a92a1, `--faint` #6b7383; light `--muted` #5c6474, `--faint` #7f8795, `--ok` #17764a,
  `--warn` #8f5e06. Keep hues; change lightness only.
- The xterm theme reads these tokens (`termTheme`): check the terminal in both themes afterwards.

## 8. Wording (fix/copy-pass-2)

- `static/keys.js` (new): `keyLabel("mod+p")` → `⌘P` / `Ctrl+P`; `alt+w` → `⌥W` / `Alt+W`; ``ctrl+` `` → `` ⌃` `` /
  `` Ctrl+` ``; `mod+backspace` → `⌘⌫` / `Ctrl+Backspace`. Used by `welcomeHtml`, `pathMenu`, `fileMenuItems`, the
  terminal menu and button titles. Later specs use it too.
- `lines.length === 1 ? "1 line" : …`; the GitHub title moves to `#sbGithub` itself; `.grep-hit b { display:
  inline-block; text-align: right; min-width: var(--ln-w) }` with `--ln-w` set per file group to the digits of its
  largest line; `overflow-wrap: anywhere` on the notes path and the prices hint.
- The live "Stopped." notice renders as the same italic "(stopped)" line the stored message shows on reload.
- `browseFolder(start, { title, action })`: `addFolder` passes "Add folder" and "Add this folder"; `fdHint` uses them.

## Tests

One e2e test per criterion group, in the file that owns the area; all fail before their fix.

| Fix | Test |
|---|---|
| 1 | `test_chat_input_ui.py`: Stop, Steer and Queue inside `#composerBox` (rect containment and `elementFromPoint` at each centre) at chat widths 300, 380, 440 and windows 1024×700, 1440×900; ⌘. stops a slow turn |
| 2 | `test_files_ui.py`: a 300-line file: Edit from the top, Edit from line 120, Done, and switching tabs keep the line |
| 3 | `test_files_ui.py`: twelve open files at 1024 wide: the active tab's rect is inside the strip's; wheel scrolls it |
| 4 | `test_commands_ui.py`: "delete build" reads "Wants to run", Deny reads "Didn't run" with no `.st.err`, also after reload; approve reads "Ran" |
| 5 | `tests/test_files.py` (`textfile.kind`), `tests/test_server.py` (the two answers), `test_files_ui.py` (binary tab has no Edit; Latin-1 file has the note and no Edit) |
| 6 | `test_review_ui.py` (the three buttons share one line at editor widths 460–660, and stay inside the bar at 400: see 6.1); `test_steering_ui.py` (the note has no `<steering`) |
| 7 | `test_design_tokens_ui.py`: every text token against every surface, both themes |
| 8 | `test_copy_ui.py`: "1 line"; one notation per platform in the welcome list and menus; "(stopped)" live and reloaded; "Add folder" |

Widths in tests are set through the saved pane sizes (`localStorage["cp--chat-w"]`, as `test_window_fit_ui.py` does),
never by assuming a font: CI runs on Linux, where text is a different width.
