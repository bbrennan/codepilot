"""Mock journey runner: replays canned user requests through the agent and writes OTEL-style traces."""

import json
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from demo_agent.agent import handle  # noqa: E402

# journey -> (user message, price ceiling the answer must respect)
JOURNEYS = {"cheap_red_shoes": ("find red shoes under $100", 100), "running_shoes": ("find running shoes", None)}

for name, (message, ceiling) in JOURNEYS.items():
    trace_id = uuid.uuid4().hex
    t0 = time.time_ns()
    result = handle(message)
    t1 = time.time_ns()
    ok = bool(result["results"]) and all(ceiling is None or p["price"] <= ceiling for p in result["results"])
    spans = [
        {"traceId": trace_id, "spanId": "root", "name": "invoke_agent", "startTimeUnixNano": t0,
         "endTimeUnixNano": t1, "status": {"code": "OK" if ok else "ERROR",
                                            "message": "" if ok else "journey expectation failed: results missing or over budget"},
         "attributes": {"journey": name, "user_message": message, "answer": result["answer"]}},
        {"traceId": trace_id, "spanId": "tool", "parentSpanId": "root", "name": "tool.search_products",
         "startTimeUnixNano": t0 + 1000, "endTimeUnixNano": t1 - 1000, "status": {"code": "OK"},
         "attributes": {"result_count": len(result["results"]),
                        "prices": [p["price"] for p in result["results"]]}},
    ]
    out = Path(__file__).parent / "traces" / f"{name}.json"
    out.write_text(json.dumps({"journey": name, "spans": spans}, indent=1))
    print(f"{name}: {'PASS' if ok else 'FAIL'} -> {out.name}")
