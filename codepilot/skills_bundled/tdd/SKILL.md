---
name: tdd
description: Build a feature or fix a bug test-first with red-green-refactor, one small vertical slice at a time. Use when the user asks for TDD, test-first, or wants a change with strong test coverage.
---
# Test-driven development

1. Read the existing tests for the area and follow their framework, fixtures, naming and helpers.
2. Pick the seam: the highest-level interface you can test cheaply and deterministically (public function,
   API handler, CLI entry point). Prefer one seam. Tell the user which seam and why before writing tests.
3. List the behaviours as a short checklist (`update_plan`), smallest useful slice first.
4. Loop, one behaviour at a time:
   - Red: propose ONE failing test for the next behaviour. After the user applies it, run it and confirm it
     fails for the right reason (the assertion, not an import error).
   - Green: propose the minimum code to pass. Run the test, then the related suite.
   - Mark the item done in the plan.
5. Refactor only when green, in a separate step, with tests run after each change.

Avoid:
- tests coupled to implementation details (private helpers, call counts) instead of behaviour
- tautological tests whose expected value is computed with the same logic as the code
- writing all the tests up front ("horizontal slicing"); go one vertical slice at a time
- mocking what you own; mock at external boundaries (network, cloud, clock, randomness)
