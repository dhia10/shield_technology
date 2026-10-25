"""
Shield Technology Telemetry API Router.
Handles batch log ingestion, cursor-paginated history, stats aggregations, DLQ, and cold archiving.
"""

from datetime import datetime, timezone
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.metrics import EVENTS_INGESTED_TOTAL, INGEST_LATENCY_SECONDS
from app.schemas.enums import EventTypeEnum, SeverityEnum
from app.schemas.telemetry import (
    RawTelemetryEvent,
    TelemetryHistoryResponse,
    TelemetryIngestRequest,
    TelemetryIngestResponse,
)
from app.security.auth import verify_probe_auth
from app.security.rate_limiter import check_rate_limit
from app.storage.archiver import log_archiver
from app.storage.cache import cache_service
from app.storage.database import async_session_factory
from app.storage.repository import TelemetryRepository
from app.workers.broker import message_broker

router = APIRouter(prefix="/api/v1/telemetry", tags=["Telemetry Pipeline"])


@router.post(
    "/ingest",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=TelemetryIngestResponse,
    summary="Ingest Telemetry Logs from Security Probes",
    dependencies=[Depends(verify_probe_auth), Depends(check_rate_limit)],
)
async def ingest_telemetry_batch(batch: TelemetryIngestRequest):
    """
    Asynchronously accepts batches of telemetry events from authorized probes.
    Returns HTTP 202 Accepted within <1 ms by dispatching into message broker.
    """
    t0 = time.perf_counter()

    for event in batch.events:
        sev_str = event.severity.value if hasattr(event.severity, "value") else str(event.severity)
        type_str = event.event_type.value if hasattr(event.event_type, "value") else str(event.event_type)

        try:
            EVENTS_INGESTED_TOTAL.labels(severity=sev_str, event_type=type_str).inc()
        except Exception:
            pass

        # Publish to asynchronous queue for decoupled worker consumption
        await message_broker.publish(
            queue="telemetry.raw",
            message=event.model_dump(mode="json"),
        )

    latency_ms = round((time.perf_counter() - t0) * 1000.0, 3)
    try:
        INGEST_LATENCY_SECONDS.observe(latency_ms / 1000.0)
    except Exception:
        pass

    return TelemetryIngestResponse(
        status="accepted",
        accepted_count=len(batch.events),
        queue_name="telemetry.raw",
        ingest_latency_ms=latency_ms,
        timestamp=datetime.now(timezone.utc),
    )


@router.get(
    "/history",
    summary="Cursor-paginated historical telemetry logs",
)
async def get_telemetry_history(
    cursor: Optional[str] = Query(None, description="Cursor for pagination"),
    limit: int = Query(50, ge=1, le=500),
    agent_id: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
):
    """Retrieves immutable telemetry logs with O(1) cursor pagination."""
    async with async_session_factory() as session:
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

    dict_items = [item.to_dict() if hasattr(item, "to_dict") else item for item in items]
    return {
        "items": dict_items,
        "records": dict_items,
        "total_returned": len(dict_items),
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


@router.get(
    "/stats",
    summary="Cached Security Statistics & Threat Aggregations",
)
async def get_telemetry_stats(window_hours: int = Query(24, ge=1, le=168)):
    """Computes hourly/daily aggregations with transparent Redis/memory caching."""
    cache_key = f"stats:telemetry:{window_hours}h"
    cached_data = await cache_service.get(cache_key)

    if cached_data:
        cached_data["cached"] = True
        cached_data["cache_hit"] = True
        return cached_data

    async with async_session_factory() as session:
        repo = TelemetryRepository(session)
        stats = await repo.get_stats(window_hours=window_hours)

    stats["cached"] = False
    stats["cache_hit"] = False
    await cache_service.set(cache_key, stats, ttl_seconds=300)
    return stats


@router.get(
    "/dlq",
    summary="Dead Letter Queue Poison Message Inspector",
)
async def get_dlq_messages():
    """Inspects failed messages routed to Dead Letter Queue for forensic analysis."""
    recent_dlq = message_broker.dlq[-50:]
    return {
        "dlq_depth": len(message_broker.dlq),
        "records": recent_dlq,
        "messages": recent_dlq,
    }


@router.post(
    "/archive",
    summary="Rotate and compress cold telemetry logs into Gzip NDJSON",
)
async def trigger_archive_rotation(cutoff_date: Optional[datetime] = None):
    """Archives events prior to cutoff date and generates SHA-256 integrity digest."""
    if cutoff_date is None:
        cutoff_date = datetime.now(timezone.utc)

    async with async_session_factory() as session:
        res = await log_archiver.archive_events(session, cutoff_date=cutoff_date, compress=True)
    return res
