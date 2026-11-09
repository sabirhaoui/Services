"""Isolated fault exercise on this Compose project only; always restores Loki."""

import base64
import json
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "demo"))
from emit import event

secrets = dict(
    x.split("=", 1) for x in Path(".env").read_text().splitlines() if "=" in x
)
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
auth = "Bearer " + secrets["INGEST_TOKEN"]


def get(path):
    return json.load(
        opener.open(
            urllib.request.Request(
                "http://127.0.0.1:18088" + path, headers={"Authorization": auth}
            ),
            timeout=5,
        )
    )


def compose(*args):
    subprocess.run(["podman", "compose", *args], check=True, stdout=subprocess.DEVNULL)


def wait_ready():
    for i in range(30):
        try:
            if get("/health/ready")["status"] == "ready":
                return
        except (OSError, ValueError):
            time.sleep(0.1)
        time.sleep(1)
    raise AssertionError("gateway not ready")


try:
    compose("stop", "loki")
    import uuid

    e = event(trace=uuid.uuid4().hex)
    req = urllib.request.Request(
        "http://127.0.0.1:18088/v1/events",
        data=json.dumps(e).encode(),
        headers={"Authorization": auth, "Content-Type": "application/json"},
    )
    result = json.load(opener.open(req, timeout=5))
    assert result["accepted"]
    trace = result["trace_id"]
    compose("restart", "gateway")
    wait_ready()
    rows = get("/v1/executions/" + trace)["observed"]
    assert len(rows) == 1
    compose("start", "loki")
    query = urllib.parse.quote('{service_name="demo"} |= "' + trace + '"')
    url = (
        "http://127.0.0.1:13001/api/datasources/proxy/uid/loki/loki/api/v1/query_range?query="
        + query
    )
    basic = (
        "Basic "
        + base64.b64encode(("admin:" + secrets["GRAFANA_PASSWORD"]).encode()).decode()
    )
    found = False
    for attempt in range(30):
        try:
            data = json.load(
                opener.open(
                    urllib.request.Request(url, headers={"Authorization": basic}),
                    timeout=5,
                )
            )
            found = bool(data["data"]["result"])
            if found:
                break
        except (OSError, ValueError):
            time.sleep(0.1)
        time.sleep(2)
    assert found, "protected event not delivered after restart"
    print(
        json.dumps(
            {
                "fault_probe": "passed",
                "accepted_during_outage": True,
                "survived_restart": True,
                "loki_recovery": True,
            }
        )
    )
finally:
    compose("start", "loki")
