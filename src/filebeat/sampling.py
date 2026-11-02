"""Deterministic trace sampling; errors retained, default 100 percent."""
import hashlib

def keep(event, rate=1.0):
    if event.get('outcome')=='error' or event['level'] in ('ERROR','CRITICAL'): return True
    bucket=int(hashlib.sha256(event['trace_id'].encode()).hexdigest()[:16],16)/2**64
    return bucket < rate
