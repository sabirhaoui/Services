import asyncio
import json
import runpy
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker

from filebeat.analytics import anomaly, reconstruct, summarize
from filebeat.api import SCHEMA, create_app
from filebeat.protection import protect
from filebeat.storage import Full, Store

fixture = runpy.run_path("demo/emit.py")["event"]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("INGEST_TOKEN", "t" * 32)
    monkeypatch.setenv("PRIVACY_KEY", "p" * 32)
    with TestClient(create_app(str(tmp_path / "events.db"), worker=False)) as c:
        yield c


def post(c, e):
    return c.post("/v1/events", json=e, headers={"Authorization": "Bearer " + "t" * 32})


def test_contract_examples():
    v = Draft202012Validator(SCHEMA, format_checker=FormatChecker())
    for family in ("http", "job", "connector"):
        v.validate(
            json.loads(Path("contracts/examples/" + family + ".json").read_text())
        )
    assert not v.is_valid(
        json.loads(Path("contracts/examples/invalid-nested.json").read_text())
    )


def test_privacy_recursive_rejection_and_no_raw_disk(client):
    for attribute in (
        {"nested": {"password": "SYNTHETIC_SECRET"}},
        {"operation": ["synthetic@example.invalid"]},
        {"token": "SYNTHETIC_SECRET"},
    ):
        e = fixture()
        e["attributes"] = attribute
        r = post(client, e)
        assert r.status_code == 422
        assert "SYNTHETIC_SECRET" not in r.text
    e = fixture()
    e["message"] = "Bearer SYNTHETIC_SECRET"
    assert post(client, e).status_code == 422
    e = fixture()
    e["service"]["name"] = "synthetic@example.invalid"
    assert post(client, e).status_code == 422
    e = fixture()
    raw = e["request_id"]
    assert post(client, e).status_code == 202
    payload = client.portal.call(
        lambda: client.app.state.store.db.execute(
            "SELECT payload FROM events"
        ).fetchone()[0]
    )
    assert raw not in payload and e["trace_id"] not in payload
    assert "SYNTHETIC_SECRET" not in payload


def test_duplicates_conflict_and_auth(client):
    e = fixture()
    assert client.post("/v1/events", json=e).status_code == 401
    assert post(client, e).json()["accepted"]
    assert post(client, e).json()["accepted"] is False
    e["duration_ms"] = 900
    assert post(client, e).status_code == 409
    assert client.get("/v1/summary").status_code == 401


def test_saturation_storage_unavailable_and_size(client):
    client.app.state.store.limit = 1
    assert post(client, fixture()).status_code == 202
    assert post(client, fixture()).status_code == 429
    r = client.post(
        "/v1/events",
        content="x" * 65537,
        headers={"Authorization": "Bearer " + "t" * 32},
    )
    assert r.status_code == 413
    client.portal.call(
        lambda: client.app.state.store.db.execute("PRAGMA query_only=ON").fetchone()
    )
    client.app.state.store.limit = 10
    assert post(client, fixture()).status_code == 503
    client.portal.call(
        lambda: client.app.state.store.db.execute("PRAGMA query_only=OFF").fetchone()
    )


def test_out_of_order_reconstruction_and_partial(client):
    e = fixture()
    trace = post(client, e).json()["trace_id"]
    start = fixture(0)
    start["timestamp"] = (
        __import__("datetime")
        .datetime.fromisoformat(e["timestamp"])
        .__sub__(__import__("datetime").timedelta(seconds=1))
        .isoformat()
        .replace("+00:00", "Z")
    )
    start["event_type"] = "http.started"
    start["message"] = "operation.started"
    assert post(client, start).status_code == 202
    result = reconstruct(client.portal.call(client.app.state.store.events), trace)
    assert result["observed"][0]["event_type"] == "http.started"
    assert not result["missing"] and result["hypotheses"] == []
    assert reconstruct([protect(e, "p" * 32, "k1")], trace)["missing"] == [
        "http.started"
    ]


def test_retry_quarantine_replay_and_restart(tmp_path):
    path = str(tmp_path / "spool.db")
    s = Store(path)
    e = protect(fixture(), "p" * 32, "k1")
    e["observed_timestamp"] = e["timestamp"]
    s.accept(e)
    states = iter([503, 400, 204])
    received = []

    def handle(request):
        received.append(json.loads(request.content))
        return httpx.Response(next(states))

    async def attempt():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as c:
            return await s.deliver(c, "http://loki")

    assert asyncio.run(attempt()) == "pending"
    assert s.db.execute("SELECT attempts,due FROM events").fetchone()[0] == 1
    s.db.close()
    s = Store(path)
    s.db.execute("UPDATE events SET due=0")
    s.db.commit()
    assert asyncio.run(attempt()) == "quarantine"
    assert s.replay() == 1
    assert asyncio.run(attempt()) == "sent"
    assert s.count("sent") == 1
    assert set(received[0]["streams"][0]["stream"]) == {
        "service_name",
        "environment",
        "level",
    }
    s.db.close()


def test_crash_after_commit(tmp_path):
    path = str(tmp_path / "crash.db")
    code = (
        "from filebeat.storage import Store; import os; s=Store("
        + repr(path)
        + "); s.accept("
        + repr(
            {
                "event_id": "protected",
                "environment": "test",
                "service": {"name": "demo"},
            }
        )
        + "); os._exit(7)"
    )
    assert subprocess.run([sys.executable, "-c", code], check=False).returncode == 7
    s = Store(path)
    assert s.count("pending") == 1
    s.db.close()


def test_retention_and_total_bound(tmp_path):
    s = Store(str(tmp_path / "r.db"), limit=1, retention=1)
    e = protect(fixture(), "p" * 32, "k1")
    e["observed_timestamp"] = e["timestamp"]
    s.accept(e)
    with pytest.raises(Full):
        s.accept({**e, "event_id": "another"})
    s.db.execute("UPDATE events SET state='sent',created=0")
    s.db.commit()
    s.purge()
    assert s.count() == 0
    s.db.close()


def test_temporal_anomaly_injected_and_no_leakage():
    assert anomaly([100] * 19, 2500)["status"] == "insufficient_data"
    assert anomaly([100] * 25, 2500)["status"] == "anomalie"
    assert anomaly([100] * 25, 100)["status"] == "normal"
    events = []
    for i in range(26):
        e = fixture(i, duration=2500 if i == 25 else 100)
        e["observed_timestamp"] = e["timestamp"]
        events.append(e)
    assert summarize(list(reversed(events)))["analyses"][0]["status"] == "anomalie"
    assert summarize([])["latency_ms"]["p95"] is None


def test_key_rotation_scope():
    e = fixture()
    assert (
        protect(e, "a" * 32, "k1")["trace_id"] == protect(e, "a" * 32, "k1")["trace_id"]
    )
    assert (
        protect(e, "a" * 32, "k1")["trace_id"] != protect(e, "b" * 32, "k2")["trace_id"]
    )


def test_sampling_trace_consistency():
    from filebeat.sampling import keep

    e = protect(fixture(), "p" * 32, "k1")
    assert keep(e, 1) and not keep(e, 0)
    assert keep(e, 0.5) == keep({**e, "event_type": "job.completed"}, 0.5)
    assert keep({**e, "outcome": "error"}, 0)


def test_nonfinite_invalid_future_and_metrics(client):
    e = fixture()
    e["duration_ms"] = float("nan")
    r = client.post(
        "/v1/events",
        content=json.dumps(e),
        headers={"Authorization": "Bearer " + "t" * 32},
    )
    assert r.status_code == 422
    e = fixture()
    e["timestamp"] = "2999-01-01T00:00:00Z"
    assert post(client, e).status_code == 422
    e = fixture()
    e["schema_version"] = "2.0.0"
    assert post(client, e).status_code == 422
    assert client.get("/health/ready").status_code == 200
    metrics = client.get("/metrics").text
    assert "filebeat_queue_depth 0.0" in metrics
    assert "filebeat_latency_anomaly NaN" in metrics


def test_collector_import_preserves_timestamp_without_raw_fields(client):
    normalize = runpy.run_path("scripts/import_remote_logs.py")["normalize"]
    source = {
        "schema_version": 1,
        "service": "postgres-1",
        "timestamp": "2026-01-01T10:00:00.123456789Z",
        "message": "ERROR: confidential-example",
        "raw": "another-confidential-example",
        "host": "internal.example",
    }
    event = normalize(source)
    assert event["timestamp"] == "2026-01-01T10:00:00.123456Z"
    assert event["service"]["name"] == "postgres"
    assert event["level"] == "ERROR"
    assert "confidential" not in json.dumps(event)
    assert "trace_id" not in event
    assert post(client, event).json() == {"accepted": True, "trace_id": None}
    assert (
        post(
            client, normalize({**source, "received_at": "2026-01-02T00:00:00Z"})
        ).json()["accepted"]
        is False
    )
    event["event_type"] = "http.completed"
    event["message"] = "operation.completed"
    assert post(client, event).status_code == 422
