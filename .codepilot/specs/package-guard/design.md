# Design: package guard

## Overview

There are three pure parts and one network part:
- `installs(command)` finds what a command would install.
- `added(path, before, after)` finds what a manifest edit adds.
- `verdict(info, now)` grades a package.
- `lookup(eco, name)` asks the registry, through an injected HTTP getter.

The approval path uses them through a third advisor in `approval_policy.ADVISORS` (requirement 1). The proposal path
uses them in `propose_edit`, storing the result on the proposal (requirement 2).

## Architecture

```
run_command approval ─► approval_policy.advise ─► packages_advisor ─► deps_guard.installs + check ─► Advice.warnings
propose_edit (tools.py) ─────────────────────────────────────────────► deps_guard.added + check  ─► proposal.advice
                                                                         └─ lookup(eco, name, http) ─ cache (1 h)
```

### New: `codepilot/deps_guard.py`

Its one reason to change is judging packages before they're installed.

```python
@dataclass
class Info:
    eco: str              # pypi | npm | crates
    name: str
    found: bool | None    # None = couldn't check
    created: float | None # first release (epoch)
    releases: int | None

def installs(command: str) -> list[tuple[str, str]]                       # (eco, name), 1.1 and 1.4
def added(path: str, before: str, after: str) -> list[tuple[str, str]]    # 2.1
def lookup(eco: str, name: str, http=_urllib_get, now=time.time) -> Info  # 3.1 and 3.2
def verdict(info: Info, now: float) -> tuple[str, str]                    # (level, text), 1.2
def check(pairs, http=..., now=...) -> list[dict]                         # [{eco, name, level, text}], lookups in parallel
```

- **Registries** (only the name is sent; 3.1):
  - PyPI: `GET https://pypi.org/pypi/{name}/json`. 404 means not found. `created` is the earliest upload time across
    `releases`; `releases` is the count of non-empty releases.
  - npm: `GET https://registry.npmjs.org/{name}`. `time.created`; `len(versions)`. Scoped names are URL-encoded.
  - crates.io: `GET https://crates.io/api/v1/crates/{name}` with a `User-Agent`, which crates.io requires.
    `crate.created_at`; `crate.num_versions` if present, else `len(versions)`.
- **Names** are normalised before lookup and caching. For PyPI that is PEP 503 (lowercase, runs of `-_.` become `-`).
- **Parsing install commands:**
  - `shellparse.simple_commands` gives every command in the line, through chains and wrappers. It is the parser the
    destructive check uses, moved to its own module so there is only one.
  - Recognise the manager and sub-command, then take the following words that aren't flags.
  - Drop anything containing `/`, `:` or `@` followed by a URL. An npm `name@version` keeps its name.
  - Drop `.` and `-r`/`-e`/`--requirement`/`--editable` with their values.
- **Manifest diffs:** `tomllib` or `json` parses before and after; the result is the set difference of names. Parse
  errors give `[]`, because the post-apply check already reports bad TOML or JSON. For `requirements*.txt`, a line diff
  stripped of specifiers and comments.
- **Cache:** a module-level dict `{(eco, name): (Info, expires)}`, guarded by a lock (tools run in worker threads).
  Answers last an hour; failed lookups last a minute, so a network blip doesn't stick.
- **Timeouts and failures:** 5 s timeout. Any error gives `found=None`, so the verdict is unknown (3.2).
- **Parallel lookups:** a small `ThreadPoolExecutor` (at most 4) when a command names several packages.
- **Tests never reach the network:** an autouse fixture replaces `deps_guard._get`. The real registries were checked by
  hand once: PyPI, npm (including scoped names) and crates.io, found and not found.

### Changes to existing modules (wiring)

- **`approval_policy.py`:** add `packages_advisor`. For `run_command`, if `cfg.deps_check` is on and `installs()` finds
  anything, it returns one warning per package. It adds `force_ask=True, offer_rule=False` when any package is not
  found or new (1.3). `View` gains `deps_check: bool`, set by the agent from config.
- **`tools.py`, `propose_edit`:**
  - For files whose name matches a known manifest, it calls `added()`, then `check()`.
  - It stores the result in the new proposal column `advice`.
  - When something is not found, it appends to the tool result: "Note: `reqeusts` is not on PyPI; check the name."
    (2.3)
  - `proposal_view` includes `advice`.
- **`store.py`:** additive column `proposals.advice TEXT` (JSON) and a setter. `get_proposal` reads it (2.4).
- **`config.py`:** `deps_check: bool` from `CODEPILOT_DEPS_CHECK`, default on (3.3). It goes in
  `docs/configuration.md`.

### Front end

- **Approval card:** no new code. The warnings arrive through `approval_needed.tools[i].warnings` and render through
  `static/policy.js`'s `warningLines`. Info-level lines render muted, so the established-package line doesn't shout.
- **New `static/deps.js`:**
  - `adviceBlock(p)` renders the package lines in `renderReviewTab` above `diffHtml`, and in the chat proposal card under
    `.reason`.
  - `adviceMark(p)` adds a ⚠ next to `diffStat` in the review list and the proposal card when any line is danger or
    caution (2.2).
  - About 40 lines in total.

### Hardening from code review (PR #42)

- **Option tables are per ecosystem:** `--optional` takes a value in uv but not in cargo or npm, and `-f` and `-r` mean
  different things across installers. Taking a package name as a flag's value would hide it from the check.
- **The install subcommand is found, not assumed to be the second word,** so global options don't hide it
  (`pip --isolated install x`, `uv --directory sub add x`, `npm --prefix web install x`).
- **npm aliases are unwrapped,** on the command line and in `package.json`: `react@npm:other@1` installs `other`, and
  changing an alias's target counts as adding a package even though the key stays the same.
- **Everything a lookup can raise stays inside it:** a truncated body or malformed JSON is "couldn't check".
- **`approval_view` runs in a worker thread** from the session endpoint, because it can wait on the network.

## Error handling

| Situation | Behaviour |
|---|---|
| Registry down or offline | unknown; the tool call proceeds (3.2) |
| Private package | "not found", and the wording says it may be private (1.2); I can still approve it |
| A huge `pip install` line (50 names) | checked in parallel; lines capped at 20, then "+30 more not checked" |
| Lookups disabled | no lines, no forced asking |

## Testing strategy

- **`tests/test_deps_guard.py`** (new):
  - `installs` across every supported form and chains, and the exclusions (1.1, 1.4).
  - `added` for each manifest kind, including a no-op reformat that adds nothing (2.1).
  - `verdict` at the boundaries: 89 vs 91 days; 2 vs 3 releases (1.2).
  - `lookup`, with a fake `http` returning recorded PyPI, npm and crates JSON, 404 and a timeout (3.1, 3.2).
  - Name normalisation.
  - Cache expiry, using an injected `now`.
- **`tests/test_approvals.py`:**
  - A saved `uv add` rule still asks when the package is new, and offers no rule (1.3).
  - It doesn't ask for an established package.
  - Disabled by config means no lookups (3.3).
- **`tests/test_tools.py`:**
  - A manifest proposal stores advice.
  - The tool result names a missing package (2.3).
  - Advice survives `Store` reopen (2.4).
- **`tests/e2e/test_ui.py`:**
  - The scripted model proposes a `pyproject.toml` change adding `reqeusts`, with the registry faked server-side through
    an injected `http`. The Review tab shows the red line and the list shows ⚠ (2.2).
  - The approval for `uv add reqeusts` shows the line and no "always allow" (1.1, 1.3).
- **No real network in tests.** Every test injects `http`.

## Alternatives rejected

- **Refusing installs of unknown packages outright.** That blocks private packages, and the decision belongs to me.
- **Running `pip download --dry-run` to check.** It is slow, it touches the network through the package manager, and it
  can execute build hooks.
- **pypistats or npm download counts as a popularity signal.** That means a second API per ecosystem and stricter rate
  limits. Release count and age are enough to flag the slopsquatting pattern (new, few releases).
