# Tasks: package guard

- [x] 1. Parse install commands and manifest changes
  - Test first: every manager form, chains, exclusions and specifier stripping; manifest diffs for pyproject,
    requirements, package.json and Cargo.toml; a reformat with no additions.
  - `deps_guard.installs`, `deps_guard.added`, name normalisation.
  - _Requirements: 1.1, 1.4, 2.1_
- [x] 2. Registry lookups and verdicts
  - Tests with a fake `http`: found, not found, timeout and malformed JSON for each registry; verdict boundaries; cache
    expiry with an injected clock; parallel `check`.
  - `lookup`, `verdict`, `check`, the cache.
  - _Requirements: 1.2, 3.1, 3.2_
- [x] 3. The approval advisor
  - Tests in `test_approvals.py`: a rule is overridden for new or missing packages, with no rule offered; established
    packages pass; `CODEPILOT_DEPS_CHECK=0` makes no lookups.
  - `packages_advisor` in `approval_policy.ADVISORS`; `View.deps_check`; config.
  - _Requirements: 1.3, 3.3_
- [x] 4. Advice on proposals
  - Tests in `test_tools.py`: advice is stored and returned in `proposal_view`; the tool result warns about a missing
    package; it survives reopen.
  - The `proposals.advice` column and migration; the `propose_edit` wiring.
  - _Requirements: 2.3, 2.4_
- [x] 5. UI for proposals
  - E2E: the red line in the Review tab; ⚠ in the list and the chat card; the approval shows package lines with no rule.
  - `static/deps.js`; hooks in `renderReviewTab` and `renderProposalCard`.
  - _Requirements: 1.1, 2.2_
- [x] 6. Docs
  - `docs/security.md` (supply chain), `docs/configuration.md` (`CODEPILOT_DEPS_CHECK`).
  - _Requirements: 3.1, 3.3_
