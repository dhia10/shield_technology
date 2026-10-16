"""
Shield Technology - Master Telemetry & Ingestion FastAPI Application
Weeks 5-11: Full ingestion pipeline, broker dispatch, cursor history, Redis caching,
Prometheus observability, and probe security.
"""

import asyncio
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST

from app.broker import message_broker
from app.cache import cache_service
from app.database import async_session_factory, get_db_session, init_db
from app.metrics import (
    EVENTS_INGESTED_TOTAL,
    INGEST_LATENCY_SECONDS,
    QUEUE_DEPTH_GAUGE,
    get_prometheus_metrics,
)
from app.rate_limiter import check_rate_limit
from app.repository import TelemetryRepository
from app.schemas import (
    TelemetryHistoryResponse,
    TelemetryIngestRequest,
    TelemetryIngestResponse,
    TelemetryStatsResponse,
)
from app.security import verify_probe_auth
from app.worker import telemetry_worker
from app.archiver import log_archiver


# Webhook Alert Callback when queue reaches threshold (Semaine 9-11)
async def trigger_queue_alert_webhook(alert_message: str):
    # In production, dispatches to Slack/PagerDuty or SIEM webhook
    print(f"[SECURITY ALERT WEBHOOK DISPATCHED] -> {alert_message}")


message_broker.webhook_alert_callback = trigger_queue_alert_webhook


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup & background worker lifecycle hooks."""
    # 1. Initialize DB Schema
    await init_db()
    # 2. Connect Cache
    await cache_service.connect()
    # 3. Start Background Worker Loop
    worker_task = asyncio.create_task(telemetry_worker.start())
    yield
    # Shutdown
    telemetry_worker.stop()
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="Shield Technology - Telemetry & Security Intelligence API",
    version="2.4.0",
    description=(
        "Industrial-grade backend for probe ingestion, threat parsing, "
        "asynchronous queuing, dead letter routing, and temporal telemetry analytics."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── INGESTION ENDPOINT (Semaines 5-6) ──────────────────────────────────────────

@app.post(
    "/api/v1/telemetry/ingest",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=TelemetryIngestResponse,
    summary="Ingest Telemetry Logs from Security Probes",
    dependencies=[Depends(verify_probe_auth), Depends(check_rate_limit)],
    tags=["Ingestion Pipeline"],
)
async def ingest_telemetry_events(
    request: TelemetryIngestRequest,
) -> TelemetryIngestResponse:
    start_time = time.perf_counter()

    events_to_queue = request.events
    accepted_count = 0

    for ev in events_to_queue:
        # Enqueue raw dict for worker ingestion
        item_dict = ev.model_dump()
        # Track metrics
        EVENTS_INGESTED_TOTAL.labels(
            severity=ev.severity.value,
            event_type=ev.event_type.value,
        ).inc()

        await message_broker.publish("telemetry.raw", item_dict)
        accepted_count += 1

    depth = await message_broker.get_queue_depth("telemetry.raw")
    QUEUE_DEPTH_GAUGE.labels(queue_name="telemetry.raw").set(depth)

    elapsed_ms = (time.perf_counter() - start_time) * 1000
    INGEST_LATENCY_SECONDS.observe(elapsed_ms / 1000.0)

    # Invalidate cached stats on new ingestion
    await cache_service.invalidate("stats:")

    return TelemetryIngestResponse(
        status="accepted",
        accepted_count=accepted_count,
        queue_name="telemetry.raw",
        dropped_count=0,
        ingest_latency_ms=round(elapsed_ms, 3),
        timestamp=datetime.now(timezone.utc),
    )


# ─── HISTORY & CURSOR PAGINATION (Semaine 7) ──────────────────────────────────

@app.get(
    "/api/v1/telemetry/history",
    response_model=TelemetryHistoryResponse,
    summary="Query Telemetry Event History (Cursor-based Pagination)",
    tags=["Analytical Telemetry"],
)
async def get_telemetry_history(
    cursor: Optional[str] = Query(None, description="Opaque cursor token for next page"),
    limit: int = Query(50, ge=1, le=500, description="Items per page"),
    agent_id: Optional[str] = Query(None, description="Filter by probe/agent ID"),
    severity: Optional[str] = Query(None, description="Filter by severity level (LOW, MEDIUM, HIGH, CRITICAL)"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    start_time: Optional[datetime] = Query(None, description="Start date (ISO 8601)"),
    end_time: Optional[datetime] = Query(None, description="End date (ISO 8601)"),
    session=Depends(get_db_session),
) -> TelemetryHistoryResponse:
    repo = TelemetryRepository(session)
    items, next_cursor, has_more = await repo.get_history(
        cursor=cursor,
        limit=limit,
        agent_id=agent_id,
        severity=severity,
        event_type=event_type,
        start_time=start_time,
        end_time=end_time,
    )

    return TelemetryHistoryResponse(
        items=items,
        next_cursor=next_cursor,
        has_more=has_more,
        total_returned=len(items),
    )


# ─── AGGREGATED STATS & CACHE (Semaine 8) ─────────────────────────────────────

@app.get(
    "/api/v1/telemetry/stats",
    response_model=TelemetryStatsResponse,
    summary="Get Aggregated Threat & Telemetry Stats (Redis Cached)",
    tags=["Analytical Telemetry"],
)
async def get_telemetry_stats(
    window_hours: int = Query(24, ge=1, le=720, description="Analytical time window in hours"),
    session=Depends(get_db_session),
) -> TelemetryStatsResponse:
    cache_key = f"stats:{window_hours}"
    cached = await cache_service.get(cache_key)

    if cached:
        cached_resp = TelemetryStatsResponse(**cached)
        cached_resp.cache_hit = True
        return cached_resp

    repo = TelemetryRepository(session)
    stats = await repo.get_stats(window_hours=window_hours)

    # Store in Redis / Cache for 300 seconds (5 min)
    await cache_service.set(cache_key, stats.model_dump(), ttl_seconds=300)
    return stats


# ─── OBSERVABILITY & HEALTH (Semaine 9-11) ─────────────────────────────────────

@app.get("/api/v1/health", summary="Health Check & System Observability", tags=["System Observability"])
async def health_check():
    q_depth = await message_broker.get_queue_depth("telemetry.raw")
    dlq_depth = await message_broker.get_dlq_depth()

    return {
        "status": "healthy",
        "service": "Shield Technology Telemetry Pipeline",
        "version": "2.4.0",
        "environment": "production",
        "queue_depth": q_depth,
        "dlq_depth": dlq_depth,
        "worker_active": telemetry_worker._running,
        "worker_processed_events": telemetry_worker.processed_count,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/metrics", summary="Prometheus Metrics Scrape Endpoint", tags=["System Observability"])
async def metrics_endpoint():
    """Prometheus exposition format."""
    metrics_data = get_prometheus_metrics()
    return Response(content=metrics_data, media_type=CONTENT_TYPE_LATEST)


# ─── DEAD LETTER QUEUE (DLQ) INSPECTION ────────────────────────────────────────

@app.get("/api/v1/telemetry/dlq", summary="Inspect Dead Letter Queue", tags=["Ingestion Pipeline"])
async def get_dlq_records():
    return {
        "dlq_depth": await message_broker.get_dlq_depth(),
        "records": message_broker.dlq[-50:],  # last 50 poison messages
    }


# ─── ARCHIVING & INTEGRITY (Semaine 8) ─────────────────────────────────────────

@app.post("/api/v1/telemetry/archive", summary="Trigger Batch Archiving & Cryptographic Checksum", tags=["Analytical Telemetry"])
async def trigger_archive(
    days_back: int = Query(30, ge=1, description="Archive logs older than N days"),
    session=Depends(get_db_session),
):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    result = await log_archiver.archive_events(session=session, cutoff_date=cutoff)
    return result
