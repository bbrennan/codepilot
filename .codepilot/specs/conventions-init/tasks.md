# Tasks: conventions-first `/init`

- [x] 1. Conventions prompt and token estimate
  - Test first: the prompt's content rules; the foundation prompt is unchanged; `token_estimate` uses `context.py`'s
    ratio; `info()` has tokens for always-on docs.
  - `steering.CONVENTIONS_PROMPT`, `steering.token_estimate`, `Doc.info()`.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 3.2_
- [x] 2. Serve the new prompt and the total
  - Test: `steering_list` returns `conventions_prompt` and `always_tokens`.
  - _Requirements: 3.1_
- [x] 3. `/init`, `/init foundation` and the Steering view
  - E2E first: `/init` sends the conventions prompt; `/init foundation` sends the foundation prompt; the Steering view
    shows the per-message estimate and per-doc tags; the button and menu labels.
  - `initCommand(arg)`, `renderSteering`, `newSteeringItems`, the help text.
  - _Requirements: 1.1, 2.1, 3.1_
- [ ] 4. Benchmark check and docs
  - `codepilot bench compare` before and after (expect no change); `/init` drafts from two of my repos in the PR
    description.
  - `docs/steering.md` (why conventions, not overviews, citing the study and its Python-only caveat), `docs/usage.md`
    (`/init`).
  - _Requirements: 1.2, 2.1_
