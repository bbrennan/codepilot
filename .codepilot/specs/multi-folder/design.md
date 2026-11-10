# Design

## The model

- `sessions.folders` (new column, JSON list of absolute paths): the added folders. `repo` stays the main folder, so
  nothing that reads it changes meaning. `Session.public()` includes `folders`.
- `ToolContext.folders`: the added folders, resolved. `resolve(rel)` accepts a path inside the main folder (relative,
  as now) or inside any added folder (absolute or `~/…`); anything else is refused as now. `rel(path)` gives a path in
  the main folder relative, and one in an added folder absolute. Everything that goes through `resolve`/`rel` (file
  tools, the file, fs, raw and upload endpoints, proposals) reaches added folders with no further change.
- A change in an added folder is stored with its absolute path; `root / path` is that path, so apply, undo, review and
  checkpoints work as they are. Their "inside the workspace" checks take the folders too.
- `folders.py` (new): checking a folder to add (exists, a directory, not already in or under the session's folders),
  making one main, describing the folders for the system prompt (2.1).

## Where it lives

- `store.py`: the column, `update_session(folders=…)`.
- `server.py` (wiring): `PATCH /api/sessions/{sid}` takes `folders` (validated by `folders.py`) and `make_main`;
  `ctx_for` passes the folders. `agent.py` (wiring): `_ctx` passes them; the system prompt lists them.
- Walks of the whole workspace (search_code, list_files, find, mentions, the grep endpoint, steering, git view) loop
  over the folders (task 3).
- `static/folders.js` (new): the folder menu, the Explorer's roots and their context menu, the missing-folder state.
  `app.js` only wires it in.

## Decisions

- Absolute paths for added folders, not `name/…` prefixes: unambiguous (two `src/` folders, a folder named like a
  subdirectory), and what models handle best (Codex and Claude Code do the same). The UI shows them with `~`.
- The main folder stays where tests run, the terminal starts, and specs live, as today; Make main folder changes that.
- A folder inside another session folder is refused: it would show twice and its files would have two names.

## Tests

Unit: store round trip; resolve/rel in an added folder, outside refused; adding a folder that is missing, a file, a
duplicate or nested is refused; read_file, propose_edit + apply + undo in an added folder; the system prompt lists
folders; search_code, list_files, find and mentions reach the second folder; steering from it. E2E: the folder menu
adds a folder; it shows in the Explorer and survives a reload; open, edit and save a file there; Remove and Make main;
a missing folder; ⌘P and @ find a file in it; Changes shows its git tree.
