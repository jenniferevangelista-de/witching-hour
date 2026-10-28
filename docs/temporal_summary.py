"""Summarize Temporal histories: which activities needed retries, and why (python docs/temporal_summary.py out)."""
import json
import sys
from pathlib import Path


def attrs(ev: dict, key: str) -> dict:
    return ev.get(key) or {}


out_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "out")
summary = []
for p in sorted(out_dir.glob("history-*.json")):
    night = p.stem.replace("history-", "")
    events = json.loads(p.read_text(encoding="utf-8")).get("events", [])
    scheduled = {}
    rows = []
    status = None
    for ev in events:
        et = ev.get("eventType", "")
        if et.endswith("ACTIVITY_TASK_SCHEDULED"):
            a = attrs(ev, "activityTaskScheduledEventAttributes")
            scheduled[ev["eventId"]] = a.get("activityType", {}).get("name")
        elif et.endswith("ACTIVITY_TASK_STARTED"):
            a = attrs(ev, "activityTaskStartedEventAttributes")
            lf = a.get("lastFailure") or {}
            rows.append({
                "activity": scheduled.get(a.get("scheduledEventId")),
                "attempt": int(a.get("attempt", 1)),
                "last_failure": (lf.get("message") or "")[:160],
                "started": ev.get("eventTime"),
            })
        elif "WORKFLOW_EXECUTION_COMPLETED" in et or "WORKFLOW_EXECUTION_FAILED" in et:
            status = et.replace("EVENT_TYPE_WORKFLOW_EXECUTION_", "").lower()
    summary.append({
        "night": night, "status": status, "events": len(events),
        "activities": rows, "retried": [r for r in rows if r["attempt"] > 1],
    })
print(json.dumps(summary, indent=1))
