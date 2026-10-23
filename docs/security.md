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
| git | Read-only subcommands only; never commits, pushes, or changes branches |
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
