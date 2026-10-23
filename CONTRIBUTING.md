# Contributing

## Dev setup

```bash
git clone https://github.com/bbrennan/codepilot.git && cd codepilot
make install          # uv sync --all-extras
make test             # all unit tests; no cloud access or API keys needed
make e2e-setup        # once: download the Chromium the browser tests drive
make e2e              # browser tests against the real UI
```

To try the app without any account, use Ollama: `make ollama && make demo`.

## Tests

- `make test` runs the unit suite (pytest). Model calls use a scripted fake (`tests/fakes.py::FakeLLM`)
  and provider SDKs are faked, so tests are fast and free.
- `make e2e` runs the browser tests in `tests/e2e/` with Playwright. Each test starts a real server on a free
  port, with a fresh database and a scripted model (`tests/e2e/conftest.py::ScriptedLLM`). It drives the
  UI the way a user does: clicks, typing, context menus, reloads, the clipboard. A test fails if the page
  logs any JavaScript error. `CODEPILOT_E2E_HEADED=1` shows the browser; `CODEPILOT_E2E_SLOWMO=250` slows it
  down.
- When a UI bug depends on timing, reproduce it deterministically instead of retrying: hold back a response
  with `page.route` (see `_slow_first_listing` in `tests/e2e/test_ui.py`).
- `make bench-validate` checks every benchmark task fails unfixed and passes with its reference solution.
- `node --check codepilot/static/app.js` catches syntax errors.

Add tests with every change: tools in `tests/test_tools.py`, agent behaviour in `tests/test_agent.py`,
server endpoints in `tests/test_server.py`, terminals in `tests/test_terminal.py`, the background server
and launcher in `tests/test_service.py`, providers in `tests/test_providers.py` and
`tests/test_direct_providers.py`, and anything a user clicks in `tests/e2e/`.

## Conventions

- Python 3.11+, max line length 120, `ruff` clean (`uvx ruff check codepilot tests`).
- Match the surrounding code's style and comment density. Docstrings explain *why*, not what.
- Tools raise `ToolError` for errors the model should see; never let a tool crash the loop.
- Keep the system prompt stable within a session: put per-turn facts in the turn context
  (see [docs/architecture.md](docs/architecture.md#messages-and-providers)).
- Never commit secrets or company-specific values. `.env` is git-ignored; `.env.example` uses placeholders.
- Update the docs in `docs/` alongside behaviour or configuration changes. Every environment variable must
  appear in `docs/configuration.md`.

## Pull requests

Keep them focused, describe the user-visible change, and include test output. If a change affects
assistant quality (prompts, tools, modes), include a before/after `codepilot bench compare`.
