# Security and data handling

codepilot runs on your machine, reads your code, sends it to the model provider you choose, and (with your
approval) runs commands. This page says exactly what happens, so you can decide where it's appropriate to
use.

## Where your code goes

| Provider | What is sent | Where |
|---|---|---|
| Bedrock | The conversation: your messages, file contents and command output the assistant reads, tool results | Amazon Bedrock in your AWS account and region, under your AWS agreement |
| Anthropic API | Same | Anthropic, under your API account's terms |
| OpenAI API | Same | OpenAI, or the endpoint in `CODEPILOT_OPENAI_BASE_URL` |
| Ollama | Same | Nowhere: stays on your machine |

Only what the assistant reads goes to the model: files it opens or that you reference, search results,
command output. It doesn't upload your whole repository. Use the provider your organisation has approved
for the code you're working on.

GitHub calls go through your own `gh` login to GitHub. CloudWatch searches (if enabled) use your AWS
credentials.

## What's stored locally

Everything lives in `~/.codepilot/` (or `CODEPILOT_HOME`), unencrypted, readable by your user account:

- `codepilot.db`: sessions, full conversation history (including code excerpts and command output),
  proposals, token usage
- `notes/`: per-workspace notes
- `scratch/`: the assistant's throwaway scripts

Delete a session in the UI to remove its history, or delete the folder to remove everything. API keys are
never stored by codepilot; they stay in your `.env` (git-ignored) or environment.

## The local web server

- Binds to **127.0.0.1** only, by default. Don't change `CODEPILOT_HOST` to `0.0.0.0`: there's no login, so
  anyone who can reach the port could drive the agent on your machine.
- Rejects requests whose `Host` header isn't localhost (blocks DNS-rebinding attacks).
- The terminal endpoint has its own stricter checks (below).
- Every state-changing request must carry a custom header that browsers won't send cross-site without a CORS
  preflight, which codepilot never grants. So other web pages you visit can't drive it.
- Other software running as your user on the same machine is trusted; codepilot doesn't defend against it.

<a id="the-terminal"></a>
## The terminal

Each terminal is a real login shell running as you. Shells run in the codepilot server and keep running
while no page is attached, until you kill them, they exit, or codepilot stops (which ends them all). The
terminal endpoints (the WebSocket and `/api/terminals`) accept a request only when all of these hold:

- it comes to the localhost-bound server with a localhost `Host` header
- the browser's `Origin` is this server, so other websites can't open it
- it presents a random token generated each time codepilot starts and embedded in the page (`no-store`,
  never written to disk); the REST endpoints also need the CSRF header every write needs

So only the codepilot page you opened can attach a shell. As with any terminal, other software running as
your user is trusted. Set `CODEPILOT_TERMINAL=0` to turn the terminal off; the page then contains no token
and the endpoint refuses every connection. The assistant has no access to the terminal; its commands go
through `run_command` and your approval.

## "Always allow" for commands

When approving a command you can allow its prefix (e.g. `pytest`) for the rest of that session. Rules are
per session and only ever added by you approving a command; the API can remove rules but not add them.
A rule never matches a command that chains, pipes, redirects or substitutes (`;`, `&`, `|`, `` ` ``, `$`,
`<`, `>`), so `pytest; rm -rf ~` still asks. No rule is offered for destructive or outward-facing
programs (`rm`, `sudo`, `git`, `chmod`, `curl`, `ssh`, …).

## Your own file actions

New file, new folder, rename, delete and save from the Explorer and editor are your actions, so they don't
go through proposals. The server still checks every path:
- It must stay inside the open workspace (no `..`, `~` or absolute paths), and the workspace folder itself
  can't be renamed or deleted.
- Rename and delete act on a symlink itself, never on what it points to. Save follows a link only to a
  target inside the workspace.
- Delete moves items to `~/.codepilot/trash`, never removes them outright. Save refuses to overwrite a file
  that changed on disk since you opened it, unless you confirm.
- Like every write, these requests need the CSRF header that other websites can't send.

## Markdown previews

Documents are rendered with marked and sanitised with DOMPurify, which removes scripts, event handlers,
`javascript:` links, styles and forms. Images referenced from a document are served from the workspace only,
images only, with `Content-Security-Policy: sandbox` and `nosniff`, so even an SVG with script can't run in
codepilot's page. Mermaid runs in its strict security mode.

## Problem reports

**Help → Report a problem** builds its report locally, and it goes nowhere unless you send it.
- Every value passes through redaction: AWS keys, API keys and tokens, `password=`/`secret=` values, URLs
  with credentials, emails, JWTs, the actual values of key environment variables, the terminal token, and
  your home path.
- The GitHub button only opens a pre-filled public issue page with a short summary: no conversation, code
  or file contents. You submit it, or not, on GitHub.

## Web tools and images

- `library_docs` sends a library name and a question to Context7. `web_search` (only with `BRAVE_API_KEY`)
  sends a query to Brave. The model is told never to put secrets or proprietary code in them, but treat
  them as leaving the machine. `CODEPILOT_WEB=0` disables both, plus `web_fetch`.
- `web_fetch` asks before each site and pre-approves none. A URL can carry data out, as CVE-2026-54316 in
  another tool showed when a domain was pre-approved. Redirects to another site are refused, and
  link-local and cloud-metadata addresses are never fetched.
- Images you attach go to your model provider with the message, like text. Image links and paths you
  write are fetched or read by codepilot on your behalf. The model's `view_image` reads workspace files
  and http(s) URLs only.

## What the assistant can do

| Capability | Guard |
|---|---|
| Read files | Only inside the open workspace (plus configured trace folders); paths outside are refused |
| Change files | Only through proposals you Apply (unless you enable `CODEPILOT_AUTO_APPLY`); every change can be undone |
| Run commands | Every `run_command` needs your approval and shows the exact command. Tests and checks need approval unless you tick auto-run |
| Verify pending changes | Runs the workspace's test command and analysers on a temporary copy with the changes applied (as you, like `run_tests`). Needs approval or a click on **Verify**, unless you tick auto-run. The workspace is never written |
| git | The git tool only reads (`branch`, `stash`, `remote` and `reflog` only in their reading forms). Commits, pushes and branch changes happen only through `run_command`, which always asks |
| Commands | Run without a terminal: stdin is closed, editors, pagers and credential prompts are off (`GIT_EDITOR=:`, `GIT_TERMINAL_PROMPT=0`, `GH_PROMPT_DISABLED=1`), and a timeout stops the command's whole process group |
| GitHub | Reads freely; writes need approval; account, secret and admin commands are refused |
| Open another folder | Needs approval |
| Scratch files | Written only under `~/.codepilot/scratch/<session>/` |
| Sub-agent (`explore`) | Read-only; can't make any call that needs approval |

Approved commands run **as you, on your machine**, with your network access and credentials. There is no
container sandbox. Read commands before approving them, especially when the conversation has included
content from outside (issues, web pages, third-party code, logs), which could contain prompt-injection
attempts.

## Prompt injection

Anything the assistant reads (code comments, READMEs, issue text, trace contents, tool output) could
contain instructions aimed at the model. Mitigations:
- The approval gates above: nothing irreversible happens without you.
- Diffs are shown before they're written, and undo is available after.
- Skills, steering docs and instruction files are trusted input, so install third-party skills only after
  reading them. A steering doc's `#[[file:...]]` references can include only files inside the workspace.

**External content.** An injection needs a way to act and a way out. So once a session has read content from outside
the machine (`web_fetch`, `web_search`, `library_docs`, CloudWatch logs, GitHub reads, an image by URL), the chat
header shows an **external content** chip and, for the rest of the session:
- "always allow" rules are paused, and no new ones are offered;
- every command, GitHub write and fetch asks, saying why;
- `web_search`, `library_docs`, `gh search`, `gh api` and images by URL, which normally don't ask, now do, because the
  query or URL itself can carry data out. The `explore` sub-agent can't ask, so it is refused them;
- the assistant is told, with the content itself, to treat it as data and not to follow instructions in it.

The workspace's own test command and analysers still run under the auto-run switch, because the model doesn't choose
what they run. If it passes arguments to the tests, that asks too: pytest runs whatever file it's pointed at.
Compaction doesn't end this: the content may still steer the model. A new session does, and so does
**Clear…** on the chip, which is for when you've checked what was read.

This limits what an injection can do without you. It doesn't detect injections, and it doesn't cover content already
in the workspace, such as a README in a repo you cloned: counting that would mark every session, and the mark would
mean nothing. Approved commands still run as you.

**Destructive commands** (recursive `rm`, `git push --force`, `git reset --hard`, `terraform destroy`, `kubectl delete`,
a download piped to a shell, and so on) get a red warning naming what they do, in every part of a chained command.
"Always allow" never covers them, even with a rule saved earlier. The check reads the command text, so it can't see
what a script does.

## Packages

Code models recommend packages that don't exist, and repeat the same invented names, so attackers register them
("slopsquatting"). Before you approve an install, or review a change that adds a dependency, codepilot looks the name up
on PyPI, npm or crates.io:
- **not found** (red): possibly an invented name, or a private package;
- **new** (amber): first published under 90 days ago, or with 2 releases or fewer;
- anything else is a quiet line, such as "on PyPI since 2014 · 213 releases".

A package that's missing or new always asks, even under an "always allow" rule. If a proposed change adds a package
that doesn't exist, the assistant is told at once, so it can correct the name. It covers install commands (`pip`, `uv`,
`poetry`, `pipx`, `npm`, `pnpm`, `yarn`, `bun`, `cargo`) and `pyproject.toml`, `requirements*.txt`, `package.json` and
`Cargo.toml`.

Only the package name leaves your machine. Lookups time out after 5 seconds, and a failed one never blocks anything.
Nothing is refused: a private package is "not found" too, and that's your call. It doesn't check for known
vulnerabilities (`run_checks` and scanners do) or for typos of popular names. `CODEPILOT_DEPS_CHECK=0` turns it off.

## Benchmark runs

`codepilot bench` auto-approves tests and a short allowlist of read/test commands, and auto-applies edits,
inside temporary copies of the task projects. Commands still run on your machine.
See [benchmark.md](benchmark.md#how-a-task-runs).

## Secrets

- Put keys in `.env` (git-ignored), never in `.env.example`, code or chat.
- Skills tell the assistant to write `<REDACTED>` instead of secret values in repros and logs, and
  `remember` is instructed never to store secrets. Neither is a guarantee: avoid pasting secrets into chat.
- Install `gitleaks` so `run_checks` can scan for committed secrets.

## Reporting a vulnerability

Please open a private security advisory on the GitHub repository rather than a public issue.
