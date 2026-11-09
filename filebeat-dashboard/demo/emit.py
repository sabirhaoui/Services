"""Only synthetic data; stdlib emitter with bounded attempts and stable retry IDs."""

import json
import os
import time
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime, timedelta


def event(i=0, family="http", duration=100, trace=None):
    return {
        "schema_version": "1.0.0",
        "event_id": str(uuid.uuid4()),
        "event_type": family + ".completed",
        "timestamp": (datetime.now(UTC) - timedelta(seconds=30 - i))
        .isoformat()
        .replace("+00:00", "Z"),
        "service": {"name": "demo", "version": "0.1.0"},
        "environment": "test",
        "level": "INFO",
        "message": "operation.completed",
        "trace_id": trace or "1" * 32,
        "span_id": format(i + 1, "016x"),
        "request_id": str(uuid.uuid4()),
        "duration_ms": duration,
        "outcome": "success",
        "attributes": {"operation": "ingestion"},
    }


def main():
    token = os.environ["INGEST_TOKEN"]
    base = os.getenv("FILEBEAT_URL", "http://127.0.0.1:18088")
    result = None
    trace = uuid.uuid4().hex
    for i in range(26):
        e = event(i, duration=2500 if i == 25 else 100 + (i % 5) * 5, trace=trace)
        payload = json.dumps(e).encode()
        for attempt in range(3):
            try:
                req = urllib.request.Request(
                    base + "/v1/events",
                    data=payload,
                    headers={
                        "Authorization": "Bearer " + token,
                        "Content-Type": "application/json",
                    },
                )
                result = json.load(urllib.request.urlopen(req, timeout=5))
                break
            except urllib.error.HTTPError as exc:
                if exc.code not in (429, 503):
                    raise
                if attempt == 2:
                    raise
                time.sleep(2**attempt)
    print(
        json.dumps(
            {"events": 26, "injected_latency_ms": 2500, "trace_id": result["trace_id"]}
        )
    )


if __name__ == "__main__":
    main()
