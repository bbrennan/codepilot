---
name: write-tests
description: Add or improve unit tests for a function, module, or bug fix, following the repo's existing test conventions.
---
# Write tests

1. Find existing tests for the area (`list_files` on the tests folder, `search_code` for the function name) and mirror their framework, fixtures, naming, and style.
2. Cover: the main behaviour, edge cases (empty, None, boundaries), error paths, and the specific bug being fixed (a test that fails before the fix).
3. Keep tests deterministic: no real network or cloud calls. Mock at the boundary the codebase already mocks (look for fixtures or fakes).
4. Propose the test file or edit with `propose_edit`, then after the user applies it, run just that test file, then the suite.
