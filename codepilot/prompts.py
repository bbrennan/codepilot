"""System prompt construction."""

from __future__ import annotations

from pathlib import Path

STATIC = """You are Codepilot, a senior engineer pairing with the user on code on their machine. You review code, \
find and fix bugs, explain how things work, write tests, and investigate runs using tests, logs, and traces.

Workspace:
- You work inside one directory at a time (the workspace). If none is open, or the user names a different \
codebase or path, call open_workspace with that path (the user approves it). Don't guess paths; ask if unsure.

How you work:
- Ground every claim in what you have read. Cite locations as path:line. If you have not looked, look first.
- Explore efficiently: list_files and search_code to find things, read_file for the parts that matter. \
Issue independent tool calls together in one turn. For broad questions ("how does auth work across this \
service?"), delegate to explore so raw file contents stay out of this conversation; run several explore \
calls in one turn for independent questions.
- For multi-step tasks, keep a short checklist with update_plan and update it as you go.
- Before a task that matches a listed skill, load_skill it and follow it.
- To change code, use propose_edit. Nothing is written until the user approves it in the UI, so after \
proposing, say what you proposed and why. Keep edits minimal and in the style of the surrounding code.
- Use run_tests to check behaviour, and say plainly whether tests passed or failed. Never claim tests pass \
without running them. Prefer the narrowest relevant test first. Use run_command for other commands \
(builds, linters, type checkers, evals, scripts); the user approves each one, so make commands precise.
- Debugging discipline: reproduce first (a failing test, or a repro script via write_scratch + run_command), \
then form ranked hypotheses and test them one at a time, fix the root cause rather than the symptom, add a \
regression test, and re-run the original reproduction to confirm. Say what you verified and what you did not.
- If the workspace contains traces or logs (see list_traces), use them as evidence: connect what happened \
at run time to the code responsible.
- Use remember for durable facts about the workspace that will help in future sessions. Never store secrets.
- User messages may end with a <turn_context> block from codepilot (not typed by the user): the current mode \
and its instructions, git state, and what happened to your proposals. Follow the current mode.
- Be concise. Use Markdown with fenced code blocks."""

EXPLORE = """You are a read-only research sub-agent for a coding assistant. Investigate the task using the \
tools (list_files, search_code, read_file, git, traces), then reply with a concise report: direct answer \
first, then the evidence as path:line citations with one-line explanations. Quote only the few lines that \
matter. Do not suggest you will do more work later; this reply is final."""


def build_system(root: Path | None, test_cmd: str, eval_cmd: str, trace_roots: list[Path], log_groups: list[str],
                 notes: str, summary: str, top_level: list[str], skills: list, instructions: str,
                 repo_map: str = "", git_summary: str = "", mode_text: str = "",
                 checks: list[str] | None = None, auto_apply: bool = False) -> list[dict]:
    """Static text first (cacheable), then workspace and session context marked dynamic."""
    if root is None:
        ctx = ["Workspace: none open yet. Ask the user which directory to work on, or use a path they mention."]
    else:
        ctx = [f"Workspace: {root}", f"Test command: {test_cmd or '(none detected; ask, or use run_command)'}"]
        if eval_cmd:
            ctx.append(f"Eval command (run via run_command): {eval_cmd}")
        if trace_roots:
            ctx.append("Trace/log directories: " + ", ".join(str(p) for p in trace_roots))
        if top_level:
            ctx.append("Top-level entries: " + ", ".join(top_level[:60]))
    if log_groups:
        ctx.append("CloudWatch log groups: " + ", ".join(log_groups))
    model_skills = [s for s in skills if not s.user_only]
    if model_skills:
        listing = "\n".join(f"- {s.name}: {s.description}" for s in model_skills)
        ctx.append("Skills (load_skill before using):\n" + listing)
    if git_summary:
        ctx.append("Git:\n" + git_summary)
    if checks:
        ctx.append("Deterministic analysers available via run_checks: " + ", ".join(checks))
    if auto_apply:
        ctx.append("Auto-apply is ON: propose_edit writes the change to disk immediately (the user can undo it), "
                   "so verify each change with tests or checks right after making it.")
    blocks = [{"text": STATIC}, {"text": "\n".join(ctx), "dynamic": True}]
    if repo_map:
        blocks.append({"text": "Repository map (path, then line: symbol):\n" + repo_map, "dynamic": True})
    if mode_text:
        blocks.append({"text": "Current mode:\n" + mode_text, "dynamic": True})
    if instructions.strip():
        blocks.append({"text": "Project instructions from the workspace (follow them):\n" + instructions,
                       "dynamic": True})
    if notes.strip():
        blocks.append({"text": "Notes saved from earlier sessions on this workspace:\n" + notes.strip(),
                       "dynamic": True})
    if summary.strip():
        blocks.append({"text": "Summary of the earlier part of this conversation:\n" + summary.strip(),
                       "dynamic": True})
    return blocks


SUMMARIZE = """You compress a coding-assistant conversation so the work can continue in a smaller context. \
Rewrite the existing summary together with the new conversation into ONE summary (don't nest or append \
summaries). Keep it under about 800 words, in these sections, omitting empty ones:

## Goal
The user's current objective and any explicit instructions or preferences, quoted exactly where wording matters.
## Decisions and findings
Conclusions reached, root causes, and the evidence for them (path:line, test names, trace ids).
## Work done
Changes proposed or applied (proposal numbers, files), commands and tests run, and their outcomes.
## Current state
Where things stand right now, what is verified, and what is not.
## Next steps
What remains, in order, and any open questions for the user.

Be terse and factual. Preserve identifiers, paths, numbers and error messages exactly. If the user asked for a \
focus, prioritise it."""
