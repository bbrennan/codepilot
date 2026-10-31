# Design: conventions-first `/init`

## Overview

This is mostly prompt text plus one number in the Steering view. Because it changes what the assistant is asked to
write, CONTRIBUTING asks for a benchmark before/after. The benchmark tasks have no steering, so the comparison only
guards against regressions. The real check is reading what `/init` drafts for a couple of my own repos.

## Architecture and changes

- **`steering.py`:**
  - Add `CONVENTIONS_PROMPT` next to `FOUNDATION_PROMPT`, which stays unchanged (2.1).
  - The new prompt says:
    - Investigate first (explore, README, build files, CI config, a few modules).
    - Propose `.codepilot/steering/conventions.md` with front matter `inclusion: always`.
    - Include only what an agent couldn't infer from the code and standard tooling. Each rule is one line ending with
      its evidence (`(see Makefile: e2e)`), at most about 25 lines.
    - Never include overviews of the product, the stack or the folder layout. The prompt says why: overviews cost tokens
      on every message without improving results.
    - If the file exists, propose additions only. If nothing qualifies, say so and propose nothing.
  - `token_estimate(text) -> int`: the same chars-per-token ratio `context.py` uses for its pre-calibration estimate,
    imported from there and not duplicated (3.2).
  - `Doc.info()` gains `"tokens"` for always-on docs.
- **`server.py`:**
  - `steering_list` returns `conventions_prompt` alongside `foundation_prompt`, and `always_tokens` (the sum over
    always-on docs, workspace and global).
- **Front end (`app.js` wiring; too small for its own script):**
  - `initCommand(arg)`: `arg === "foundation"` sends `foundation_prompt`, otherwise `conventions_prompt` (1.1, 2.1).
  - In the Steering view, the button **Generate foundation docs** becomes **Draft conventions**.
    `newSteeringItems()` gains a menu item **Draft Kiro foundation docs** (2.1).
  - `renderSteering` adds a line under the list: "Always-on steering adds ≈1.2k tokens to every message (estimate)."
    Each always-on row shows `≈340 tok` in the existing `.incl` tag style (3.1, 3.2).
  - The `/help` table and slash-command menu describe `/init` as "Draft non-obvious project conventions" and
    `/init foundation` as "Draft Kiro foundation docs".

## Error handling

- A workspace with no steering folder: unchanged. `propose_edit` creates the file when I apply it.
- A huge always-on doc: the number simply shows it. No warning, so the view doesn't nag.

## Testing strategy

- **`tests/test_steering.py`:**
  - `CONVENTIONS_PROMPT` names `conventions.md`, forbids overviews and asks for evidence and a line cap (1.1–1.4).
  - `FOUNDATION_PROMPT` is unchanged (2.1).
  - `token_estimate` matches `context.py`'s ratio.
  - `info()` includes tokens only for always-on docs.
- **`tests/test_server.py`:** `steering_list` returns `conventions_prompt` and `always_tokens`.
- **`tests/e2e/test_ui.py`:**
  - `/init` puts the conventions prompt in the chat; `/init foundation` puts the foundation prompt (1.1, 2.1).
  - The Steering view shows the per-message estimate, with a steering doc in the test repo (3.1).
- **Benchmark:** `codepilot bench compare` before and after, as CONTRIBUTING asks. Expect no change, because the
  benchmark tasks have no steering. Then a manual look at `/init`'s draft on two of my repos, recorded in the PR.

## Alternatives rejected

- **Removing the foundation docs.** I sometimes use Kiro on the same repos, and the Kiro-compatible format is a feature.
- **Changing existing docs from always-on to `auto`.** That changes my configuration behind my back. The token number
  lets me decide.
