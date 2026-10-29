# CodePilot: rules for every change

Read [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/architecture.md](docs/architecture.md) first. These rules are not optional.

## Git workflow
- Never commit or push to `main` or `develop`. Branch from `develop` as `feature/<topic>` or `fix/<topic>`;
  `hotfix/<topic>` branches from `main`. One issue per branch, one focused PR into `develop`.
- `develop` -> `main` happens only as a release merge. Never force-push a shared branch.
- Stage files by name (no `git add -A`): untracked work from other branches ends up in the wrong commit.
- Commit messages: one imperative line stating what the user gets, then the attribution line.

## Test-first (TDD)
- Write the failing test first and watch it fail for the right reason, then make it pass, then refactor.
- Bug fix = regression test that fails on the old code. UI behaviour = Playwright test in `tests/e2e/`
  (reproduce timing bugs deterministically, e.g. with `page.route`, never with retries or sleeps).
- Before opening a PR: `make test`, `make e2e`, `uvx ruff check codepilot tests`, `node --check codepilot/static/app.js`.
- Look at the real UI (the Playwright MCP in `.mcp.json`, or `make e2e` headed) before calling a UI change done.

## Design (SOLID)
- Single responsibility: do not grow `server.py`, `agent.py`, `tools.py` or `static/app.js`. New behaviour goes in a
  new small module with one reason to change; touch the big files only to wire it in.
- Depend on abstractions: inject collaborators (model client, clock, filesystem root) so tests use fakes
  (`tests/fakes.py::FakeLLM`) instead of patching internals.
- Extend by adding (a tool, a provider, a slash command), not by adding branches to existing functions.
- Keep the system prompt stable within a session; tools raise `ToolError` rather than crash the loop.

## Hygiene
- Match surrounding style and comment density; line length 120. Comments explain why.
- No secrets or company-specific values (this repo is public). No mock/fixture data for real or internal projects.
- Update `docs/` with behaviour or configuration changes; every env var appears in `docs/configuration.md`.
- Do not widen scope: note unrelated problems in the PR instead of fixing them in the same branch.
