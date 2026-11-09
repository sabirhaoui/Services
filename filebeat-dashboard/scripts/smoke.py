"""Local assertions; reads only newly generated service credentials. No secret output."""

import base64
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "demo"))
from emit import main as emit

secrets = dict(
    line.split("=", 1)
    for line in Path(".env").read_text().splitlines()
    if "=" in line and not line.startswith("#")
)
import os

os.environ["INGEST_TOKEN"] = secrets["INGEST_TOKEN"]
# Bypass machine proxies for loopback-only validation.
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def get(url, auth=None):
    req = urllib.request.Request(url, headers={"Authorization": auth} if auth else {})
    with opener.open(req, timeout=8) as response:
        return json.load(response)


auth = "Bearer " + secrets["INGEST_TOKEN"]
grafana = (
    "Basic "
    + base64.b64encode(("admin:" + secrets["GRAFANA_PASSWORD"]).encode()).decode()
)
for ready_attempt in range(30):
    try:
        if get("http://127.0.0.1:18088/health/ready")["status"] == "ready":
            break
    except OSError:
        time.sleep(1)
else:
    raise AssertionError("gateway not ready")
emit()
summary = get("http://127.0.0.1:18088/v1/summary", auth)
assert summary["events"] >= 26
assert any(a["status"] == "anomalie" for a in summary["analyses"]), summary
assert (
    get("http://127.0.0.1:13001/api/dashboards/uid/filebeat-health", grafana)[
        "dashboard"
    ]["uid"]
    == "filebeat-health"
)
# Loki is deliberately private. Query through Grafana's authenticated datasource proxy.
query = urllib.parse.quote('{service_name="demo",environment="test"}')
url = (
    "http://127.0.0.1:13001/api/datasources/proxy/uid/loki/loki/api/v1/query_range?query="
    + query
    + "&limit=100"
)
for attempt in range(12):
    data = get(url, grafana)["data"]["result"]
    alerts = get("http://127.0.0.1:19093/api/v2/alerts")
    active = any(a["labels"]["alertname"] == "FilebeatLatencyAnomaly" for a in alerts)
    if data and active:
        break
    time.sleep(5)
assert data, "No Loki data"
assert active, "No local latency alert"
event = json.loads(data[0]["values"][0][1])
assert event["trace_id"].startswith("k1:") and event["event_id"].startswith("k1:")
execution = get("http://127.0.0.1:18088/v1/executions/" + event["trace_id"], auth)
assert execution["observed"] and execution["hypotheses"] == []
print(
    json.dumps(
        {
            "status": "passed",
            "retained_events": summary["events"],
            "loki_streams": len(data),
            "dashboard": "filebeat-health",
            "local_alert": "FilebeatLatencyAnomaly",
            "reconstruction": "observed only",
        }
    )
)
