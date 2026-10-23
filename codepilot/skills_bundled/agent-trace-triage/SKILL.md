---
name: agent-trace-triage
description: Diagnose LLM-agent runs (AgentCore, Strands, LangGraph, etc.) from trace/log files: which journeys failed, which step went wrong, and what code is responsible.
---
# Agent trace triage

1. `list_traces` to see what exists (newest first). If several runs are present, compare the latest against an earlier passing one.
2. `trace_outline` each relevant trace before reading it in full. Note error spans, slow spans, and the trace/session ids.
3. For a failing journey, walk the span timeline: user input -> model call(s) -> tool calls (inputs and outputs) -> final answer. Find the first step where the behaviour diverges from what the user asked for. Typical causes:
   - the model picked the wrong tool, or passed wrong or missing arguments (check the tool schema and description in code)
   - the tool returned wrong or empty data (check the tool's implementation)
   - the prompt or system instructions don't cover the case
   - parsing or formatting of the model output failed
   - timeouts, throttling, retries
4. Map the failing step to code: search_code for the span/tool name, and read the tool implementation and its schema.
5. Report: which journeys failed, the failing step with evidence (`trace file:line` or span name and attributes), the responsible code (`path:line`), and a fix. Distinguish code bugs from prompt or model-behaviour issues.
6. To reproduce cheaply, replay the failing journey's input against the code with a scratch harness (`write_scratch` + `run_command`) instead of the full eval. Then follow `diagnose-bug` for the fix.
7. To confirm a fix end to end, suggest re-running the eval (run_command with the eval command), then compare the new traces with the old ones.
