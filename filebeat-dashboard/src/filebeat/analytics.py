"""Descriptive observed data and causal-free robust latency detector v1."""

import math
from datetime import UTC, datetime
from statistics import median


def percentile(values, p):
    if not values:
        return None
    v = sorted(values)
    return v[max(0, math.ceil(len(v) * p) - 1)]


def anomaly(history, value):
    if len(history) < 20:
        return {"status": "insufficient_data", "version": "mad-v1"}
    baseline = median(history)
    mad = median([abs(x - baseline) for x in history])
    threshold = baseline + max(6 * 1.4826 * mad, 50)
    return {
        "status": "anomalie" if value > threshold else "normal",
        "baseline_ms": baseline,
        "threshold_ms": threshold,
        "version": "mad-v1",
    }


def summarize(events):
    finished = sorted(
        [e for e in events if e["event_type"].endswith(".completed")],
        key=lambda e: (e["timestamp"], e["event_id"]),
    )
    durations = [e["duration_ms"] for e in finished if "duration_ms" in e]
    groups = {}
    for e in events:
        key = (
            e["environment"],
            e["service"]["name"],
            e["service"]["version"],
            e["event_type"],
        )
        groups.setdefault(key, []).append(e)
    analyses = []
    for key, group in groups.items():
        ordered = sorted(
            [e for e in group if "duration_ms" in e], key=lambda e: e["timestamp"]
        )
        if ordered:
            last = ordered[-1]
            prior = [
                e["duration_ms"]
                for e in ordered[:-1]
                if e["timestamp"] < last["timestamp"]
            ][-100:]
            analyses.append(
                {
                    "service": key[1],
                    "environment": key[0],
                    "service_version": key[2],
                    "event_type": key[3],
                    **anomaly(prior, last["duration_ms"]),
                }
            )
    times = [datetime.fromisoformat(e["observed_timestamp"]) for e in events]
    lag = [
        max(
            0,
            (
                datetime.fromisoformat(e["observed_timestamp"])
                - datetime.fromisoformat(e["timestamp"])
            ).total_seconds(),
        )
        for e in events
    ]
    return {
        "events": len(events),
        "completed": len(finished),
        "errors": sum(e.get("outcome") == "error" for e in finished),
        "duration_coverage": len(durations) / len(finished) if finished else None,
        "latency_ms": {f"p{p}": percentile(durations, p / 100) for p in (50, 95, 99)},
        "processing_lag_p95_seconds": percentile(lag, 0.95),
        "freshness_seconds": (datetime.now(UTC) - max(times)).total_seconds()
        if times
        else None,
        "analyses": analyses,
        "confidence": "observed only; bounded retention, not total producer traffic",
    }


def reconstruct(events, trace_id):
    rows = sorted(
        [e for e in events if e.get("trace_id") == trace_id],
        key=lambda e: (e["timestamp"], e["event_id"]),
    )
    observed = [e["event_type"] for e in rows]
    missing = []
    for family in ("http", "job", "connector"):
        if family + ".completed" in observed and family + ".started" not in observed:
            missing.append(family + ".started")
        if family + ".started" in observed and family + ".completed" not in observed:
            missing.append(family + ".completed")
    return {
        "observed": rows,
        "missing": missing,
        "hypotheses": [],
        "confidence": "partial"
        if missing
        else ("observed pairs only" if rows else "no data"),
    }
