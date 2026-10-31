# Tasks: quick specs, length budgets and task reminders

- [x] 1. Profile rules
  - Test first: `may_write`, `may_approve` and `can_switch_to_full` tables; `instructions` for every combination of
    profile, kind and phase includes the budgets.
  - `codepilot/spec_profiles.py`; move `PHASE_INSTRUCTIONS` there and add the budget sentence.
  - _Requirements: 1.2, 1.3, 2.1, 2.3_
- [x] 2. Specs carry a profile
  - Tests: create quick; old `spec.json` loads as full; quick approval jumps to implement; switching to full only before
    approval; `write_spec` permissions by profile.
  - `Spec.profile`; `create`, `approve` and `set_profile`; `info()`; `tools.write_spec` uses `may_write`.
  - _Requirements: 1.5, 1.6, 1.7_
- [x] 3. Endpoints and starting quick specs
  - Tests: `POST /specs` with a profile; `profile` action and its 409s; `/spec quick …` and Spec mode start a quick spec
    of the detected kind.
  - Server changes; `agent._spec_for_message` parsing.
  - _Requirements: 1.1, 1.6_
- [x] 4. Task reminders
  - Tests: `criteria` parsing; length cap; none when no task is in progress; a 12-step FakeLLM turn gets two reminders in
    tool results and none in the system prompt; the event is emitted.
  - `codepilot/spec_reminder.py`; the hook in `_loop_steps`.
  - _Requirements: 3.1, 3.2, 3.4_
- [x] 5. UI: Quick spec, the Plan step, the length hint and Activity
  - E2E first: Quick spec → three sub-tabs → Approve plan → Implement; Switch to full review; a long document shows the
    hint; the reminder row appears in Activity only.
  - `static/specs-quick.js`; hooks in `renderSpecs`, `renderSpecTab` and `render()`; extend ScriptedLLM for quick.
  - _Requirements: 1.1, 1.4, 2.2, 3.3_
- [x] 6. Docs
  - `docs/specs.md` (Quick specs, budgets, reminders), `docs/usage.md` (Specs, `/spec quick`).
  - _Requirements: 1.1, 2.1, 3.1_
