"""Minimize before persistence. Input has already passed the strict allowlist."""

import hashlib
import hmac


def protect(event, key, key_id):
    result = {**event, "attributes": dict(event["attributes"])}
    for field in ("event_id", "trace_id", "span_id", "request_id", "job_id"):
        if field in result:
            value = (field + ":" + result[field]).encode()
            result[field] = (
                key_id + ":" + hmac.new(key.encode(), value, hashlib.sha256).hexdigest()
            )
    result["privacy_key_id"] = key_id
    return result
