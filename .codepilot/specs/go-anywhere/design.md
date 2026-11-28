# Design

## Module: `static/palette.js` (new, loaded straight after `app.js`)

The palette's code moves out of `app.js` (`pal`, `openPalette`, `palSearch`, `renderPalette`, `closePalette` and their
listeners, the "palette & dialog & toast" block) into this script, unchanged, in the first commit; `app.js` gets
shorter. A function declared in a later script doesn't exist yet while `app.js` runs, so a handler `app.js` assigns as
a value goes through a wrapper: the welcome page's `#wFind` (`() => openPalette()`); `#paletteBtn`'s moves with the
block. `app.js`'s keys, the File menu's Go to File… and `a11y.js` (`closePalette`, `#palette` in its dialogs) call it
by name when they run, which is after every script has loaded. Then:

- **Modes**, chosen by the text's first character, as a table so a mode is added by a row:
  `{ prefix: ">", items: commandItems }`, `{ prefix: ":", items: lineItems }`, and the default `fileItems`. Each returns
  rows: an option `{ icon, title, dir?, detail?, kbd?, heading?, run }` (`heading` on the first of a group) or a hint
  `{ hint }`, which isn't an option. One `renderPalette` draws any of them. A late answer to text typed since is
  dropped (a sequence number), opening clears the last list, and Enter on text the list hasn't answered yet waits for
  that answer, so Enter never takes a row for other text.
- **The list is a combobox**, as the session switcher (`sessions.js`) and the @, / and # lists (#131) are: the box is
  `role=combobox` with `aria-controls`, the list a `listbox`, each option has an id and `aria-selected`, and the
  current one is the box's `aria-activedescendant`. A heading is the label of a `role=group` around its options, not
  an option. Options have `tabindex=-1` (the keyboard audit, #128, asks that anything clickable be focusable) and a
  mousedown on the list is cancelled, so focus stays in the box. `a11y.js` names the dialog "Go to file or command".
- **Files.** Empty text: `recentFiles()`, under "Recently opened"; a folder with none yet lists the `/find` answer to
  "" as before. Otherwise the existing `/find` request, under "Files"; a trailing `:<n>` is stripped before the request
  and passed on Enter to `palGoTo(path, n)`. Then `sessionItems(text)`: up to five of `state.sessionList` matching by
  `sessionMatches` (`sessions.js`: the title or the folder's name contains the text), newest first, heading
  "Sessions", `run: openSession(id)` (nothing for the session you're in). Without a folder the files' hint comes
  first and sessions are still found. A title keeps its one line; a row's path or description gives way first.
- **Recent files.** `noteRecent(tab)` keeps the 30 most recently shown paths per folder in
  `localStorage["cp-recent:<folder>"]` as `{ v: 1, at, paths }`, and is called once, at the end of `renderEditor`;
  it notes a file, image or binary tab of the folder's (`id` is `file:<path>`). The folder is `tabStore.folder`
  (`tabstate.js`: whose tabs are on screen, `null` while they're reopened), not `state.workspace`, which `openSession`
  has already moved on (#125 hit this). `renderEditor` runs often: the same folder and file as last time writes
  nothing. Folders are forgotten by `pruneTabRecords`' rule (not opened for 30 days, or not among the 20 most recent),
  which takes the key prefix as a second argument; `noteRecent` runs it once a page, after its first write.
  `recentFiles()` lists the paths but the active tab's, leaving out any that `/stat` says are gone (one request for
  the list). A file in an added folder (#102) is kept by its full path: it opens while the folder is in the session,
  and `/stat` answers `null` for it once the folder is removed, so it's left out with no error.
- **`:<n>` alone**: one item, "Go to line n in <file>", `run: palGoTo(activePath, n)`; listed only with a folder's
  file tab active (not a steering doc shown as a file), else a hint.
- **`palGoTo(path, n)`.** The read view: `openFile(path, n)` (the line flashed, a few lines of context above it). In
  Edit mode `openFile` only sets the tab's top line and redraws, which mounts a new editor and loses its undo history,
  and the handle (`editor.js`, from code-editor) had no way to go to a line (the editor's own Ctrl+G opens
  CodeMirror's prompt). So the handle gains `goToLine(n)`: the caret to the start of line n, clamped, and that line
  scrolled into view. For the file being edited, `palGoTo` calls it on the editor that's there, then focuses it; for
  another file being edited, it does so once `openFile` has shown it.
- **Commands.** `registerCommand({ id, title, keys, when, run, icon, detail })` adds to a `Map`;
  `registerCommands(id, rows)` adds a table read each time the list is drawn. `commandItems(text)` lists those whose
  `when()` is absent or true and whose title matches every typed word (case-insensitive, any order), in the order
  registered. `keys` is a `keys.js` combo (`"mod+b"`), shown with `keyLabel`; a menu row's `kbd` is already
  `keyLabel`'s. Where the app keeps a table, commands come from it, so each has one definition:
  - the activity bar's buttons: "Show <view>" for each one shown, `setView`;
  - `fileMenuItems()` (New File…, New Folder…, Open Folder…, Save while editing, Edit File, Rename File…, Close Tab;
    not Go to File…, which is the palette) and `terminalMenuItems()` (New Terminal and the rest), as they are when
    the menus open;
  - the modes and model tiers the pickers are built from (`state.wsInfo.modes`, `["auto", ...cfg.tiers]`), through
    `modeCommand` and `modelCommand` (`setMode` only redraws the picker; the session is told by its change handler,
    which `modeCommand` fires), so a custom mode appears by itself;
  - the slash commands that take no text (`slashCommands()`: new session, help, retry, undo, export, report, restart),
    titled by their description, but `/terminal`, `/usage` and `/steering`, which a menu row or a view above already
    is, and `/bug`, which is `/report`. (The Help menu's rows are written inline in its click handler, so Report a
    problem and Restart come from here.)

  The rest are one-liners at the bottom of the file calling what exists: `toggleSidebar`, `toggle("no-panel")`,
  `toggle("no-chat")`, a click on `#themeBtn` (the theme has no function of its own), Focus chat (as ⌘L does it),
  `addFolder` (`folders.js`, which loads later: wrapped), `runCmd("tests")`, `runCmd("checks")`, a click on
  `#stopBtn`, `openReview`, `bulkProposals("apply")`, `compactNow`, and Close Tab for a tab that isn't a file's (the
  File menu's is for a file). **Close other tabs** had no function: `closeOtherTabs()` closes each other tab with
  `closeTab`, so a tab with unsaved edits asks first and stays if you keep it.
- **Running one.** Enter's default is prevented (no `keypress`, so a command that puts focus in a text box doesn't
  type the Enter there), the palette closes, then the option runs. Since #131 a closing dialog gives focus back to
  what opened it, a tick later and only if nothing has taken it since; closing first means a command that moves focus
  itself (New File…'s prompt, Focus chat, New Terminal) ends with focus where it put it, and Enter in that prompt
  can't land on the button that opened the palette.
- `openPalette(prefix = "")` no longer needs a folder; `fileItems` returns one hint row without one.
- Keys: `app.js`'s `mod+p` branch matched ⇧⌘P too (it lowercases the key); `mod+shift+p` goes before it with
  `openPalette(">")`. In the editor, `EDITOR_APP_KEYS`' `"Mod-p"` already leaves both to the app (Shift doesn't count
  there), and so does the find panel. The terminal would send Ctrl+Shift+P to the shell as Ctrl+P on Linux and
  Windows: `termView` gives xterm.js a key handler that leaves ⇧⌘P to the app.
- The placeholder becomes `Go to file…   > commands   : line`; the title-bar button keeps "Search files ⌘P".

## Decisions

- **One box, prefixes, like VS Code.** Mixed results without prefixes would rank a command against a file name; the
  prefix says which you mean. Sessions are the exception: there are few, and their titles rarely look like file names.
- **No ⌘E for recent files.** An empty ⌘P is the recent list, which is one key fewer and nothing new to learn.
- **Commands call existing functions.** No new behaviour hides in the palette; if a command exists, a button does too.
  (One exception, asked for by 2.3: Close other tabs, which has no button yet.)
- **Filtering is word matching, not fuzzy scoring.** "tog side" finds "Toggle sidebar"; a scorer isn't worth its tests
  for about forty commands.

## Tests

`tests/e2e/test_palette_ui.py` (new). The existing Go-to-file tests keep passing unchanged, which checks the move:
they're in `test_multi_folder_ui.py`, `test_keyboard_access_ui.py`, `test_code_editor_ui.py`,
`test_design_tokens_ui.py` and `test_chat_input_ui.py` (none are in `test_ui.py` or `test_files_ui.py` any more). One
of them, the dialog's name in `test_keyboard_access_ui.py`, changes with task 3, when the name covers commands.
- open `agent/core.py`, `tests/test_core.py`, then `Makefile`; ⌘P lists `test_core.py`, `core.py`; Enter opens it;
  ⌘P again shows `Makefile` first (1.1). A recent file deleted on disk isn't listed; the list survives a reload; each
  folder has its own; redrawing the same file writes nothing; old folders are forgotten; a file in an added folder
  opens, and is left out once the folder is removed.
- `long.py:40` Enter: the file opens with line 40 flashed; `:60` with a file open goes to line 60; `:5` with no file
  open lists nothing; in Edit mode with unsaved text, `:50` and `long.py:20` move the caret there and keep the draft
  (1.2). (`agent/core.py` has two lines, too few to see a jump.)
- a session with no folder: ⌘P opens, `>` lists commands, the files section shows the hint (1.3).
- `>tog side` lists "Toggle sidebar" with its key label; Enter hides the sidebar; ⇧⌘P opens with `>`, also from the
  editor, its find panel and the terminal (2.1, 2.2).
- "Save" is absent with no file being edited and present in Edit mode; "Stop" only while a slow turn runs (2.2).
- the listed titles include every command named in 2.3, none twice; a custom mode's file in `.codepilot/modes/` adds
  its command.
- `registerCommand` called from the page adds a row that runs (2.4).
- `>new file`, Enter, a name, Enter: one file, and the palette stays shut; Focus chat and New Terminal end with focus
  where they put it; Close other tabs asks about an unsaved tab.
- two sessions titled "export bug" and "hello": typing "export" lists the first under "Sessions"; Enter opens it (3.x).
- `test_keyboard_access_ui.py`: the audit passes with the palette open in each mode.
