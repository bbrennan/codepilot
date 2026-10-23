---
name: security-review
description: Review code or a diff for security vulnerabilities, including LLM-agent risks like prompt injection and unsafe tool use. Use for "security review", "is this safe", handling of untrusted input, auth, secrets, or before exposing a service.
---
# Security review

1. Map the trust boundaries: where untrusted data enters (HTTP, queues, files, LLM output, tool results,
   environment) and what privileged actions exist (DB writes, shell, file system, cloud APIs, payments).
2. Trace each untrusted input to each sink. Check for:
   - injection: SQL/NoSQL, shell, template, LDAP, log injection; unsafe `eval`/`exec`/deserialisation
   - authn/authz: missing checks, IDOR (object ids from the client), privilege escalation, confused deputy
   - secrets: hard-coded keys, secrets in logs/errors/traces, overly broad IAM policies
   - files and network: path traversal, SSRF, unrestricted uploads, open redirects
   - web: XSS, CSRF, CORS misconfiguration, missing security headers
   - crypto: home-grown crypto, weak hashing for passwords, missing TLS verification
   - LLM agents: prompt injection via retrieved/tool content, tools that act without validation, model output
     used directly in SQL/shell/HTML, unbounded tool loops or spend, sensitive data sent to models or traces
3. Check dependencies if tooling exists (`pip-audit`, `npm audit`, `govulncheck` via run_command).
4. Report each finding with `path:line`, a concrete exploit scenario, severity, and the fix. Separate
   confirmed issues from hardening suggestions. Do not include working exploit payloads beyond what is
   needed to show the issue.
