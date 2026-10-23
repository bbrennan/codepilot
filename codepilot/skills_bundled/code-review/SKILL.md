---
name: code-review
description: Review a diff, branch, PR, file, or module for real defects, measured against the repo's own standards and the intended behaviour. Use for "review this", PR reviews, pre-merge checks, or "what's wrong with my changes".
---
# Code review

## 1. Pin the scope
- Uncommitted work: `git status`, `git diff`, `git diff --staged`.
- A branch: find the base (`git merge-base HEAD main`, or the branch the user names), then
  `git diff <base>...HEAD` and `git log --oneline <base>..HEAD`. Confirm the diff is not empty.
- A file or module: read it in full plus its callers (`search_code` for the public names).

## 2. Find the intent and the standards
- Intent: the user's description, commit messages, linked issue text, a spec or ADR in `docs/`, or ask.
- Standards: the project instruction files (AGENTS.md, CLAUDE.md, .cursorrules, CONTRIBUTING), linters and
  formatters configured in the repo, and the conventions visible in neighbouring code.

## 3. Review on two axes (keep them separate in the report)
**Correctness against intent:** does the change do what it claims, for all inputs?
- wrong conditions, inverted comparisons, off-by-one, wrong units, None/empty/zero cases
- error handling: swallowed exceptions, partial failure leaving bad state, retries without limits/backoff
- contracts: callers relying on behaviour that changed; schema/API/tool-definition vs. code mismatches
- concurrency, resource leaks, ordering and idempotency
- security: injection, authz gaps, secrets in logs, unsafe deserialisation, path traversal
- tests: does a test cover the changed behaviour, and would it have caught a bug here?

**Design against standards:** naming, duplication, leaky abstractions, feature envy, long parameter lists,
dead code, inconsistency with repo conventions. A documented repo standard overrides general taste.

For large changes, run `explore` on independent areas in one turn (e.g. "how is X validated before Y?").

## 4. Verify before reporting
Re-read the code for each suspected defect. Where a test or quick scratch script can confirm it, offer to
run it. Drop anything you cannot substantiate.

## 5. Report
Findings ranked by severity. Each one: `path:line`, what goes wrong and when (a concrete input or scenario),
and the fix. Then a short design section. No style nits unless asked. Offer to `propose_edit` the fixes.
