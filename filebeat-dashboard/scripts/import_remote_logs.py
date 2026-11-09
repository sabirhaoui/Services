"""Import a bounded slice of the SSH collector's local JSONL output."""

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

SERVICE_ROOT = Path(__file__).resolve().parents[1]
SERVICES = ("backend", "celery-worker", "celery-beat", "postgres", "redis", "connector")
LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
PREFIX = re.compile(r"\b(DEBUG|INFO|WARNING|WARN|ERROR|CRITICAL|FATAL|PANIC|LOG):")
MAX_LINE = 1024 * 1024


def normalize(record):
    if not isinstance(record, dict) or record.get("schema_version") != 1:
        raise ValueError("unsupported collector envelope")
    service = record["service"]
    if not isinstance(service, str):
        raise TypeError("invalid service")
    service = re.sub(r"-[0-9]+$", "", service)
    if service not in SERVICES:
        raise ValueError("unsupported service")
    timestamp = datetime.fromisoformat(record["timestamp"])
    if timestamp.tzinfo is None:
        raise ValueError("timezone required")
    message = record.get("message")
    match = PREFIX.search(message[:512]) if isinstance(message, str) else None
    level = record.get("level")
    if not isinstance(level, str) or level not in LEVELS:
        level = match.group(1) if match else "UNKNOWN"
    level = {
        "WARN": "WARNING",
        "FATAL": "CRITICAL",
        "PANIC": "CRITICAL",
        "LOG": "INFO",
    }.get(level, level)
    identity = json.dumps(
        [record["service"], record["timestamp"], record.get("raw", message)],
        ensure_ascii=False,
    )
    return {
        "schema_version": "1.0.0",
        "event_id": str(uuid5(NAMESPACE_URL, identity)),
        "event_type": "log.received",
        "timestamp": timestamp.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "service": {"name": service, "version": "0.0.0"},
        "environment": "production",
        "level": level,
        "message": "log.received",
        "attributes": {},
    }


def send(event, token, opener):
    request = urllib.request.Request(
        "http://127.0.0.1:18088/v1/events",
        data=json.dumps(event).encode(),
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
        },
    )
    with opener.open(request, timeout=10) as response:
        result = json.load(response)
    if result["accepted"]:
        return "accepted"
    return "sampled_out" if result.get("reason") == "sampled_out" else "duplicate"


def consume(lines, offset, args, token, opener):
    outcomes = Counter()
    blocked = None
    for line in lines:
        if len(line) > MAX_LINE:
            blocked = "oversize_line"
            break
        if not line.endswith(b"\n"):
            break
        try:
            event = normalize(json.loads(line))
        except (KeyError, TypeError, ValueError, RecursionError):
            outcomes["invalid_or_unsupported"] += 1
        else:
            if (args.service and event["service"]["name"] != args.service) or (
                args.since and datetime.fromisoformat(event["timestamp"]) < args.since
            ):
                outcomes["filtered"] += 1
            else:
                try:
                    outcome = send(event, token, opener)
                except urllib.error.HTTPError as exc:
                    blocked = f"http_{exc.code}"
                    break
                except OSError:
                    blocked = "gateway_unreachable"
                    break
                outcomes[outcome] += 1
        offset += len(line)
        if (
            sum(outcomes[x] for x in ("accepted", "duplicate", "sampled_out"))
            >= args.limit
        ):
            break
    return outcomes, offset, blocked


def follow(args, token, opener):
    checkpoint = args.follow
    configuration = {
        "source": str(args.file.resolve()),
        "since": args.since.isoformat() if args.since else None,
        "service": args.service,
    }
    state = (
        json.loads(checkpoint.read_text())
        if checkpoint.exists()
        else {
            "configuration": configuration,
            "offsets": {},
        }
    )
    if state["configuration"] != configuration:
        raise ValueError("Use another checkpoint when changing the source or filters")
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    offsets = state["offsets"]
    while True:
        progressed = False
        archives = sorted(args.file.glob("events.*.jsonl"))
        for path in [*archives, args.file / "events.jsonl"]:
            try:
                with path.open("rb") as stream:
                    stat = os.fstat(stream.fileno())
                    identity = f"{stat.st_dev}:{stat.st_ino}"
                    offset = offsets.get(identity, 0)
                    if stat.st_size < offset:
                        offset = 0
                    stream.seek(offset)
                    lines = []
                    size = 0
                    while size < 2 * MAX_LINE:
                        line = stream.readline(MAX_LINE + 1)
                        if not line:
                            break
                        lines.append(line)
                        size += len(line)
            except (FileNotFoundError, PermissionError):
                # The collector can rotate the active file during enumeration.
                continue
            outcomes, next_offset, blocked = consume(lines, offset, args, token, opener)
            if next_offset != offset:
                offsets[identity] = next_offset
                temporary = checkpoint.with_suffix(".tmp")
                temporary.write_text(json.dumps(state), encoding="utf-8")
                temporary.replace(checkpoint)
                progressed = True
            if blocked or any(
                outcomes[k] for k in ("accepted", "duplicate", "sampled_out")
            ):
                report(outcomes, next_offset, blocked)
            if blocked:
                if blocked not in ("gateway_unreachable", "http_429", "http_503"):
                    return 1
                time.sleep(5)
                break
        if not progressed:
            time.sleep(2)


def report(outcomes, offset, blocked):
    print(
        json.dumps(
            {"outcomes": dict(outcomes), "next_offset": offset, "blocked": blocked}
        ),
        flush=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "file", type=Path, help="JSONL segment, or collector directory with --follow"
    )
    parser.add_argument(
        "--limit", type=int, default=100, help="Maximum submissions per batch"
    )
    parser.add_argument(
        "--offset", type=int, default=0, help="Resume at a byte offset in the same file"
    )
    parser.add_argument("--service", choices=SERVICES)
    parser.add_argument(
        "--since",
        type=datetime.fromisoformat,
        help="Earliest original timestamp, with timezone",
    )
    parser.add_argument(
        "--follow",
        type=Path,
        metavar="CHECKPOINT",
        help="Follow all segments and persist offsets",
    )
    args = parser.parse_args()
    if args.since and args.since.tzinfo is None:
        parser.error("--since requires a timezone")
    if args.limit < 1 or args.offset < 0:
        parser.error("limit must be positive and offset nonnegative")
    if args.follow and (not args.file.is_dir() or args.offset):
        parser.error(
            "--follow requires a collector directory and manages its own offsets"
        )
    token = next(
        line.partition("=")[2]
        for line in (SERVICE_ROOT / ".env").read_text().splitlines()
        if line.startswith("INGEST_TOKEN=")
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    if args.follow:
        try:
            return follow(args, token, opener)
        except KeyboardInterrupt:
            return 0
    with args.file.open("rb") as stream:
        if args.offset:
            stream.seek(args.offset - 1)
            if stream.read(1) != b"\n":
                parser.error("offset must follow a complete line in this segment")
        lines = iter(lambda: stream.readline(MAX_LINE + 1), b"")
        outcomes, offset, blocked = consume(lines, args.offset, args, token, opener)
    report(outcomes, offset, blocked)
    return int(blocked is not None)


if __name__ == "__main__":
    raise SystemExit(main())
