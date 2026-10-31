# Requirements: package guard

## Introduction

Code models recommend packages that don't exist: 19.7% of recommendations across 16 models, and 43% of those
invented names recur across runs (USENIX Security 2025). That repetition is what makes "slopsquatting" work: an
attacker registers the invented name. A new, little-used package that suddenly appears in a proposal deserves a look
before I approve the install.

This spec checks every package that a command would install, or that a proposal adds to a dependency manifest, against
its public registry. It shows the result where I decide. It plugs into the approval advice hook from
[taint-aware-approvals](../taint-aware-approvals/design.md).

**In scope:** PyPI, npm and crates.io.

**Out of scope:** other ecosystems (gem, go get, maven); vulnerability databases (`run_checks` and the scanners
cover those); typo-distance checks against popular names (would need a bundled popularity list; a later item);
private registries beyond "not found publicly".

## 1. Check install commands

**User story:** As the developer, I want to see whether a package exists and how established it is before I approve
installing it, so that I don't install a squatted or invented name.

1.1 WHEN a `run_command` needing approval installs packages THEN the approval SHALL show one line per package, with its
registry status. Supported forms: `pip`/`pip3`/`python -m pip install`, `uv add`, `uv pip install`, `poetry add`,
`pipx install`, `npm install|i|add`, `pnpm add`, `yarn add`, `bun add` and `cargo add`, including inside chained
commands.
1.2 The status SHALL be one of:
- **not found** (danger): "not on PyPI — possibly an invented name, or a private package";
- **new** (caution): first published under 90 days ago, or 2 releases or fewer;
- **established** (info): "on PyPI since 2014 · 213 releases";
- **unknown** (info): "couldn't reach PyPI".
1.3 WHEN any package is not found or new THEN the system SHALL ask even if an "always allow" rule covers the command, and
SHALL NOT offer "always allow" for it.
1.4 The system SHALL ignore local paths, URLs, `-r`/`-e` arguments and flags, and SHALL strip version specifiers and
extras (`requests[socks]>=2`) before looking a name up.

## 2. Check new dependencies in proposals

**User story:** As the developer, I want the same check when CodePilot adds a dependency by editing a manifest, so that
a later `uv sync` or `npm install` can't slip it in unseen.

2.1 WHEN a proposal adds names to `pyproject.toml` (`project.dependencies`, optional dependencies, dependency groups,
Poetry dependencies), `requirements*.txt`, `package.json` (`dependencies`, `devDependencies`, `peerDependencies`,
`optionalDependencies`) or `Cargo.toml` (`[dependencies]`, `[dev-dependencies]`) THEN the system SHALL check each
added name as in 1.2.
2.2 The results SHALL appear in the Review tab above that proposal's diff, and as a warning mark on its row in the file
list and on its line in the chat.
2.3 WHEN a proposal adds a package that is not found THEN the `propose_edit` result SHALL tell the agent, so that it can
correct the name in the same turn.
2.4 The results SHALL be stored with the proposal and survive a reload.

## 3. Behaviour and privacy

3.1 Lookups SHALL send only the package name to the registry's public API, SHALL time out after 5 seconds, and SHALL be
cached for an hour.
3.2 A failed lookup SHALL never block or fail a tool call. It shows as unknown.
3.3 `CODEPILOT_DEPS_CHECK=0` SHALL turn all lookups off.
