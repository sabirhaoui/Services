"""Single process durable bounded outbox. Payloads must already be minimized."""

import hashlib
import json
import sqlite3
import time
from pathlib import Path


class Full(Exception):
    pass


class Conflict(Exception):
    pass


class Store:
    def __init__(self, path, limit=10000, retention=86400):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, digest TEXT, payload TEXT, created REAL, state TEXT, attempts INTEGER DEFAULT 0, due REAL DEFAULT 0)"
        )
        self.db.commit()
        self.limit, self.retention = limit, retention

    def count(self, state=None):
        return self.db.execute(
            "SELECT count(*) FROM events" + (" WHERE state=?" if state else ""),
            (state,) if state else (),
        ).fetchone()[0]

    def purge(self):
        with self.db:
            self.db.execute(
                "DELETE FROM events WHERE state='sent' AND created<?",
                (time.time() - self.retention,),
            )

    def accept(self, event):
        identity = ":".join(
            (event["environment"], event["service"]["name"], event["event_id"])
        )
        stable = {k: v for k, v in event.items() if k != "observed_timestamp"}
        digest = hashlib.sha256(json.dumps(stable, sort_keys=True).encode()).hexdigest()
        old = self.db.execute(
            "SELECT digest FROM events WHERE id=?", (identity,)
        ).fetchone()
        if old:
            if old[0] != digest:
                raise Conflict()
            return False
        self.purge()
        if self.count() >= self.limit:
            raise Full()
        with self.db:
            self.db.execute(
                "INSERT INTO events(id,digest,payload,created,state) VALUES (?,?,?,?,?)",
                (identity, digest, json.dumps(event), time.time(), "pending"),
            )
        return True

    def events(self):
        return [
            json.loads(r[0])
            for r in self.db.execute("SELECT payload FROM events ORDER BY created")
        ]

    def replay(self):
        with self.db:
            cur = self.db.execute(
                "UPDATE events SET state='pending', attempts=0, due=0 WHERE state='quarantine'"
            )
        return cur.rowcount

    async def deliver(self, client, url):
        row = self.db.execute(
            "SELECT id,payload,attempts FROM events WHERE state='pending' AND due<=? ORDER BY created LIMIT 1",
            (time.time(),),
        ).fetchone()
        if not row:
            return "idle"
        event = json.loads(row[1])
        # Use receive time for Loki ordering; original event time remains in JSON.
        from datetime import datetime

        ns = str(
            int(datetime.fromisoformat(event["observed_timestamp"]).timestamp() * 1e9)
        )
        labels = {
            "service_name": event["service"]["name"],
            "environment": event["environment"],
            "level": event["level"],
        }
        try:
            response = await client.post(
                url + "/loki/api/v1/push",
                json={"streams": [{"stream": labels, "values": [[ns, row[1]]]}]},
            )
            status = response.status_code
        except __import__("httpx").HTTPError:
            status = 503
        state = (
            "sent"
            if 200 <= status < 300
            else (
                "quarantine"
                if 400 <= status < 500 and status not in (408, 429)
                else "pending"
            )
        )
        attempts = row[2] + 1
        with self.db:
            self.db.execute(
                "UPDATE events SET state=?,attempts=?,due=? WHERE id=?",
                (state, attempts, time.time() + min(2 ** min(attempts, 5), 30), row[0]),
            )
        return state
