# Design

## Module: `static/palette.js` (new, loaded straight after `app.js`)

The palette's code moves out of `app.js` (`pal`, `openPalette`, `palSearch`, `renderPalette`, `closePalette` and their
four listeners, app.js:2606–2630) into this script, unchanged, in the first commit; `app.js` gets shorter. Then:

- **Modes**, chosen by the text's first character, as a table so a mode is added by a row:
  `{ prefix: ">", items: commandItems }`, `{ prefix: ":", items: lineItems }`, and the default `fileItems`. Each returns
  `[{ icon, title, detail, heading?, run }]`; one `renderPalette` draws any of them, with headings between groups.
- **Files.** Empty text: `recentFiles()`. Otherwise the existing `/find` request; a trailing `:<n>` is stripped before
  the request and passed to `openFile(path, n)` on Enter. Then `sessionItems(text)`: up to five of
  `state.sessionList` whose title or folder's name contains the text, heading "Sessions", `run: openSession(id)`.
- **Recent files.** `noteRecent(path)` keeps the 30 most recent paths per folder in `localStorage["cp-recent:<folder>"]`
  and is called once, at the end of `renderEditor`, for an active file tab. `recentFiles()` lists them, leaving out
  the active file and any that `/stat` says are gone (one request for the list).
- **`:<n>` alone**: one item, "Go to line n in <file>", `run: openFile(activePath, n)`; listed only with a file tab
  active. In Edit mode it calls the editor's go-to-line through the handle (`code-editor`).
- **Commands.** `registerCommand({ id, title, keys, when, run })` adds to a `Map`; `commandItems(text)` lists those
  whose `when()` is absent or true and whose title matches every typed word (case-insensitive, any order), in the order
  registered. `keys` is a `keys.js` spec (`"mod+b"`), shown with `keyLabel`. `palette.js` registers the built-in
  commands at the bottom of the file, each a one-liner calling a function that already exists (`toggle`, `setView`,
  `newSession`, `newItem`, `addFolder`, `newTerminal`, `saveFile`, `closeTab`, `runCmd`, `bulkProposals`, `openReview`,
  `compactNow`, `setMode`, `modelCommand`, `openReport`, `restartServer`, and a click on `#stopBtn`). Modes and model
  tiers are registered from the lists the selects are built from, so a custom mode appears by itself.
- `openPalette(prefix = "")` no longer needs a folder; `fileItems` returns one hint row without one.
- Keys: the `mod+p` branch stays in `app.js`'s handler (it calls `openPalette()`); `mod+shift+p` is added beside it
  with `openPalette(">")`. Enter runs `pal.items[pal.idx].run()`.
- The placeholder becomes `Go to file…   > commands   : line`; the title-bar button keeps "Search files ⌘P".

## Decisions

- **One box, prefixes, like VS Code.** Mixed results without prefixes would rank a command against a file name; the
  prefix says which you mean. Sessions are the exception: there are few, and their titles rarely look like file names.
- **No ⌘E for recent files.** An empty ⌘P is the recent list, which is one key fewer and nothing new to learn.
- **Commands call existing functions.** No new behaviour hides in the palette; if a command exists, a button does too.
- **Filtering is word matching, not fuzzy scoring.** "tog side" finds "Toggle sidebar"; a scorer isn't worth its tests
  for about forty commands.

## Tests

`tests/e2e/test_palette_ui.py` (new; the existing Go-to-file tests in `test_ui.py` and `test_files_ui.py` keep
passing unchanged, which checks the move):
- open `agent/core.py` then `Makefile`; ⌘P shows `agent/core.py` first; Enter opens it; ⌘P again shows `Makefile`
  first (1.1). A recent file deleted on disk isn't listed.
- `core.py:2` Enter: the file opens with line 2 flashed; `:1` with a file open goes to line 1; `:5` with no file open
  lists nothing (1.2).
- a session with no folder: ⌘P opens, `>` lists commands, the files section shows the hint (1.3).
- `>tog side` lists "Toggle sidebar" with its key label; Enter hides the sidebar; ⇧⌘P opens with `>` (2.1, 2.2).
- "Save" is absent with no file being edited and present in Edit mode; "Stop" only while a slow turn runs (2.2).
- the listed titles include every command named in 2.3; a custom mode's file in `.codepilot/modes/` adds its command.
- `registerCommand` called from the page adds a row that runs (2.4).
- two sessions titled "export bug" and "hello": typing "export" lists the first under "Sessions"; Enter opens it (3.x).
