# Tasks

- [x] 1. Folders in a session, and codepilot's tools in them
  - Test first (unit): store; `folders.py` checks; resolve/rel; read, propose, apply and undo in an added folder; the
    system prompt. (E2E): the folder menu adds a folder, the Explorer shows it after a reload, a file there opens and
    saves; Remove and Make main; a missing folder.
  - `store.py`, `folders.py`, `tools.py`, `checkpoints.py`, `server.py`, `agent.py`; `static/folders.js`, `index.html`,
    `app.css`, `app.js` wiring; docs.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4_
  - _Tests: tests/test_folders.py, tests/test_server.py (folders added, files saved), tests/e2e/test_multi_folder_ui.py_
- [ ] 2. Finding things in every folder
  - Test first: search_code, list_files, find (⌘P), mentions (@) and the Search view reach the second folder; steering
    from it; the Changes view lists its git tree.
  - `tools.py`, `mentions.py`, `steering.py`, `server.py`; `static/folders.js`; docs.
  - _Requirements: 3.1, 3.2, 3.3_
