---
name: refactor-safely
description: Restructure code without changing behaviour - extract, rename, split modules, remove duplication, simplify. Use for "clean this up", "refactor", "reduce duplication", or architecture improvements.
---
# Refactor safely

1. Define the target shape and why (what gets simpler, what it unblocks). Keep scope tight.
2. Pin current behaviour first. Run the existing tests for the area. If coverage is thin, propose
   characterization tests that capture today's behaviour (including odd edge cases) before changing anything.
3. Find every use of what you will change (`search_code`, `explore` for wide sweeps): callers, imports,
   string references, config, docs, serialised names.
4. Change in small steps, each one behaviour-preserving and independently verifiable (rename, then move,
   then extract...). Run the tests after each applied step.
5. Never mix a refactor with a behaviour change in one step. If you find a bug, note it and fix it
   separately.
6. Finish with the full suite and a short summary of what moved where.
