"""Format-agnostic parsing of trace and log files (JSON / JSONL / OTEL-style spans).

Traces vary by exporter (OpenTelemetry, AgentCore, Strands, LangGraph, custom JSON), so this finds span-like
objects heuristically: any dict with a name-ish key and a start-time-ish key. It powers both the model's
`trace_outline` tool and the UI's timeline view.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

NAME_KEYS = ("name", "span_name", "spanName", "operation", "operationName", "tool_name", "event", "type")
START_KEYS = ("startTimeUnixNano", "start_time_unix_nano", "startTime", "start_time", "start", "timestamp",
              "ts", "time")
END_KEYS = ("endTimeUnixNano", "end_time_unix_nano", "endTime", "end_time", "end")
DURATION_KEYS = ("duration_ms", "durationMs", "latency_ms", "latencyMs", "elapsed_ms", "duration")
ID_KEYS = ("traceId", "trace_id", "sessionId", "session_id", "journey_id", "journeyId", "request_id",
           "requestId", "conversation_id")
MAX_RECORDS = 20_000


def load_records(path: Path) -> list[Any]:
    """Parse a .json file (object or array) or a JSON-lines file into a list of records."""
    text = path.read_text(errors="replace")
    stripped = text.lstrip()
    if path.suffix.lower() == ".json" or stripped[:1] in "[{":
        try:
            data = json.loads(text)
            return data if isinstance(data, list) else [data]
        except json.JSONDecodeError:
            pass
    records = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            records.append({"_raw": line})
        if len(records) >= MAX_RECORDS:
            break
    return records


def to_ms(value: Any) -> float | None:
    """Normalise epoch s/ms/us/ns numbers or ISO-8601 strings to epoch milliseconds."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, str):
        v = value.strip()
        if v.isdigit():
            value = int(v)
        else:
            try:
                return datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp() * 1000
            except ValueError:
                return None
    if isinstance(value, (int, float)):
        if value > 1e17:
            return value / 1e6
        if value > 1e14:
            return value / 1e3
        if value > 1e11:
            return float(value)
        if value > 1e8:
            return value * 1000.0
    return None


def _first(d: dict, keys: tuple[str, ...]) -> tuple[str | None, Any]:
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return k, d[k]
    return None, None


def _status(d: dict) -> str:
    status = d.get("status")
    if isinstance(status, dict):
        code = status.get("code") or status.get("status_code") or status.get("statusCode")
        msg = status.get("message") or status.get("description")
        text = str(code) if code is not None else ""
        return f"{text}: {msg}" if msg else text
    if status not in (None, ""):
        return str(status)
    for k in ("error", "exception", "level", "severity"):
        if d.get(k) not in (None, "", False):
            v = d[k]
            return f"{k}: {v if not isinstance(v, (dict, list)) else json.dumps(v)[:200]}"
    return ""


def _is_error(d: dict, status: str) -> bool:
    s = status.lower().strip()
    # OTEL status codes: 0 UNSET, 1 OK, 2 ERROR.
    if s == "2" or s.startswith("2:") or s.startswith("status_code_error"):
        return True
    if s.startswith(("level:", "severity:")):
        return any(w in s for w in ("error", "critical", "fatal"))
    return any(w in s for w in ("error", "exception", "fail", "timeout"))


def _walk(obj: Any, depth: int = 0) -> Iterator[dict]:
    if depth > 12:
        return
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            if isinstance(v, (dict, list)):
                yield from _walk(v, depth + 1)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v, depth + 1)


def find_spans(records: list[Any], limit: int = 2000) -> list[dict]:
    spans = []
    for rec in records:
        for d in _walk(rec):
            name_key, name = _first(d, NAME_KEYS)
            start_key, start = _first(d, START_KEYS)
            if name_key is None or start_key is None or isinstance(name, (dict, list)):
                continue
            start_ms = to_ms(start)
            if start_ms is None:
                continue
            _, end = _first(d, END_KEYS)
            end_ms = to_ms(end)
            dur_key, dur = _first(d, DURATION_KEYS)
            duration = None
            if end_ms is not None:
                duration = max(0.0, end_ms - start_ms)
            elif isinstance(dur, (int, float)):
                duration = dur * 1000 if dur_key == "duration" and dur < 1000 and isinstance(dur, float) else dur
            status = _status(d)
            span_id = d.get("spanId") or d.get("span_id") or d.get("id")
            parent = d.get("parentSpanId") or d.get("parent_span_id") or d.get("parentId") or d.get("parent_id")
            spans.append({
                "name": str(name)[:200], "start_ms": start_ms, "duration_ms": duration, "status": status,
                "error": _is_error(d, status) if status else False,
                "span_id": _scalar(span_id),
                "parent_id": _scalar(parent),
                "attrs": _brief_attrs(d),
            })
            if len(spans) >= limit:
                break
        if len(spans) >= limit:
            break
    spans.sort(key=lambda s: s["start_ms"])
    return spans


def _scalar(value: Any) -> str | None:
    if value in (None, "") or isinstance(value, (dict, list)):
        return None
    return str(value)


def _brief_attrs(d: dict) -> dict:
    out = {}
    attrs = d.get("attributes") if isinstance(d.get("attributes"), dict) else d
    for k, v in attrs.items():
        if isinstance(v, (str, int, float, bool)) and k not in NAME_KEYS + START_KEYS + END_KEYS:
            out[k] = v if not isinstance(v, str) else v[:300]
        if len(out) >= 12:
            break
    return out


def find_ids(records: list[Any]) -> dict[str, list[str]]:
    ids: dict[str, set[str]] = {}
    for rec in records:
        for d in _walk(rec):
            for k in ID_KEYS:
                v = d.get(k)
                if isinstance(v, (str, int)) and v != "":
                    ids.setdefault(k, set()).add(str(v))
    return {k: sorted(v)[:20] for k, v in ids.items()}


def shape(obj: Any, depth: int = 0, max_depth: int = 3) -> Any:
    """A compact structural sketch of a JSON value: keys and types, lists summarised by length."""
    if isinstance(obj, dict):
        if depth >= max_depth:
            return f"{{{len(obj)} keys}}"
        return {k: shape(v, depth + 1, max_depth) for k, v in list(obj.items())[:40]}
    if isinstance(obj, list):
        if not obj:
            return "[]"
        return [f"{len(obj)} items, first:", shape(obj[0], depth + 1, max_depth)]
    if isinstance(obj, str):
        return f"str({len(obj)})" if len(obj) > 60 else obj
    return obj


def outline(path: Path) -> dict:
    records = load_records(path)
    spans = find_spans(records)
    t0 = spans[0]["start_ms"] if spans else None
    return {
        "records": len(records),
        "ids": find_ids(records),
        "shape": shape(records[0]) if records else None,
        "spans": spans,
        "t0_ms": t0,
        "errors": sum(1 for s in spans if s["error"]),
    }


def outline_text(path: Path, max_spans: int = 150) -> str:
    o = outline(path)
    lines = [f"records: {o['records']}  spans detected: {len(o['spans'])}  error spans: {o['errors']}"]
    if o["ids"]:
        lines.append("ids: " + "; ".join(f"{k}={', '.join(v[:5])}" for k, v in o["ids"].items()))
    if o["spans"]:
        lines.append("\n  +offset_ms   dur_ms  name  [status]")
        t0 = o["t0_ms"]
        for s in o["spans"][:max_spans]:
            dur = f"{s['duration_ms']:.0f}" if isinstance(s["duration_ms"], (int, float)) else "?"
            flag = " !!" if s["error"] else ""
            status = f"  [{s['status']}]" if s["status"] else ""
            lines.append(f"  {s['start_ms'] - t0:>10.0f} {dur:>8}  {s['name']}{status}{flag}")
        if len(o["spans"]) > max_spans:
            lines.append(f"  [... {len(o['spans']) - max_spans} more spans]")
    else:
        lines.append("\nNo span-like objects found. Structure of first record:")
        lines.append(json.dumps(o["shape"], indent=1, default=str)[:6000])
    return "\n".join(lines)
