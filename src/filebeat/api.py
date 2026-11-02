import asyncio
import contextlib
from contextlib import asynccontextmanager
from datetime import datetime, UTC
import hmac
import json
import os
from pathlib import Path
import re
import sqlite3
import shutil
import httpx
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import Response
from jsonschema import Draft202012Validator, FormatChecker
from prometheus_client import CollectorRegistry, Counter, Gauge, generate_latest
from .storage import Store, Full, Conflict
from .protection import protect
from .sampling import keep
from .analytics import summarize, reconstruct

SCHEMA=json.loads((Path(__file__).resolve().parents[2]/'contracts/event-1.0.0.schema.json').read_text())
VALIDATOR=Draft202012Validator(SCHEMA,format_checker=FormatChecker())

def create_app(path=None, transport=None, worker=True):
    token=os.getenv('INGEST_TOKEN',''); key=os.getenv('PRIVACY_KEY',''); key_id=os.getenv('PRIVACY_KEY_ID','k1')
    limit=int(os.getenv('QUEUE_LIMIT','10000'))
    sample_rate=float(os.getenv('SAMPLE_RATE','1'))
    if not 0 <= sample_rate <= 1: raise ValueError('SAMPLE_RATE outside [0,1]')
    registry=CollectorRegistry()
    outcomes=Counter('filebeat_ingest_total','Ingest outcomes',['outcome'],registry=registry)
    delivery=Counter('filebeat_delivery_total','Delivery attempts',['outcome'],registry=registry)
    depth=Gauge('filebeat_queue_depth','Pending events',registry=registry)
    quarantine=Gauge('filebeat_quarantine_depth','Quarantined events',registry=registry)
    retained=Gauge('filebeat_retained_events','Retained events',registry=registry)
    oldest=Gauge('filebeat_queue_oldest_seconds','Oldest pending receive age',registry=registry)
    anomalies=Gauge('filebeat_latency_anomaly','Latest adequately sampled latency anomaly',registry=registry)
    coverage=Gauge('filebeat_duration_coverage_ratio','Fraction completed events with duration',registry=registry)
    fresh=Gauge('filebeat_freshness_seconds','Age of most recent receive',registry=registry)
    @asynccontextmanager
    async def lifespan(app):
        if len(token)<24 or len(key)<32 or token==key or not re.fullmatch('[a-zA-Z0-9-]{1,16}',key_id):
            raise RuntimeError('Provide distinct INGEST_TOKEN >=24, PRIVACY_KEY >=32 and safe key id')
        store=Store(path or os.getenv('DB_PATH','.data/events.db'),limit)
        app.state.store=store
        async with httpx.AsyncClient(timeout=3,transport=transport) as client:
            async def run():
                while True:
                    try:
                        result=await store.deliver(client,os.getenv('LOKI_URL','http://loki:3100'))
                        if result!='idle': delivery.labels(result).inc()
                        store.purge()
                    except sqlite3.Error:
                        delivery.labels('storage_error').inc()
                    await asyncio.sleep(.25)
            task=asyncio.create_task(run()) if worker else None
            try: yield
            finally:
                if task:
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError): await task
                store.db.close()
    app=FastAPI(title='Independent filebeat',version='0.1.0',lifespan=lifespan)
    def auth(request:Request):
        if not hmac.compare_digest(request.headers.get('authorization',''), 'Bearer '+token): raise HTTPException(401,'unauthorized')
    @app.get('/health/live')
    async def live(): return {'status':'alive'}
    @app.get('/health/ready')
    async def ready():
        try:
            s=app.state.store
            s.db.execute('BEGIN IMMEDIATE'); s.db.rollback()
            if s.count()>=limit or shutil.disk_usage(Path(path or os.getenv('DB_PATH','.data/events.db')).parent).free<10*1024*1024: raise HTTPException(503,'capacity exhausted')
        except sqlite3.Error: raise HTTPException(503,'storage unavailable') from None
        return {'status':'ready'}
    @app.post('/v1/events',status_code=202,dependencies=[Depends(auth)])
    async def ingest(request:Request):
        body=bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body)>65536:
                outcomes.labels('too_large').inc(); raise HTTPException(413,'body too large')
        try:
            event=json.loads(body)
            if not VALIDATOR.is_valid(event): raise ValueError()
            age=(datetime.now(UTC)-datetime.fromisoformat(event['timestamp'])).total_seconds()
            if age>6*86400 or age< -300: raise ValueError()
        except (ValueError,TypeError,RecursionError,OverflowError):
            # Invalid payloads never reach disk, quarantine, logs or error details.
            outcomes.labels('invalid').inc(); raise HTTPException(422,'invalid telemetry contract') from None
        event=protect(event,key,key_id)
        if not keep(event,sample_rate):
            outcomes.labels('sampled_out').inc()
            return {'accepted':False,'reason':'sampled_out','trace_id':event['trace_id']}
        event['observed_timestamp']=datetime.now(UTC).isoformat().replace('+00:00','Z')
        try: accepted=app.state.store.accept(event)
        except Full:
            outcomes.labels('full').inc(); raise HTTPException(429,'capacity exhausted',headers={'Retry-After':'5'}) from None
        except Conflict:
            outcomes.labels('conflict').inc(); raise HTTPException(409,'identity conflict') from None
        except sqlite3.Error:
            outcomes.labels('storage_error').inc(); raise HTTPException(503,'storage unavailable') from None
        outcomes.labels('accepted' if accepted else 'duplicate').inc()
        return {'accepted':accepted,'trace_id':event['trace_id']}
    @app.get('/v1/summary',dependencies=[Depends(auth)])
    async def summary(): return summarize(app.state.store.events())
    @app.get('/v1/executions/{trace_id}',dependencies=[Depends(auth)])
    async def execution(trace_id:str): return reconstruct(app.state.store.events(),trace_id)
    @app.post('/v1/quarantine/replay',dependencies=[Depends(auth)])
    async def replay(): return {'requeued':app.state.store.replay()}
    @app.get('/metrics')
    async def metrics():
        s=app.state.store
        depth.set(s.count('pending')); quarantine.set(s.count('quarantine')); retained.set(s.count())
        row=s.db.execute("SELECT min(created) FROM events WHERE state='pending'").fetchone()[0]
        import time
        oldest.set(time.time()-row if row else 0)
        data=summarize(s.events())
        coverage.set(data['duration_coverage'] if data['duration_coverage'] is not None else float('nan'))
        fresh.set(data['freshness_seconds'] if data['freshness_seconds'] is not None else float('nan'))
        known=[a for a in data['analyses'] if a['status']!='insufficient_data']
        anomalies.set(int(any(a['status']=='anomalie' for a in known)) if known else float('nan'))
        return Response(generate_latest(registry),media_type='text/plain; version=0.0.4')
    return app

app=create_app()
