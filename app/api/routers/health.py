"""
Shield Technology System Health & Prometheus Observability Router.
"""

from fastapi import APIRouter, Response, status
from prometheus_client import CONTENT_TYPE_LATEST

from app.metrics import QUEUE_DEPTH_GAUGE, get_prometheus_metrics
from app.storage.database import async_session_factory
from app.workers.broker import message_broker
from app.workers.worker import telemetry_worker

router = APIRouter(tags=["Health & Metrics"])


@router.get("/api/v1/health", summary="Platform & Component Health Status")
async def health_check():
    """Returns real-time health telemetry across database, worker, and broker."""
    queue_depth = await message_broker.get_queue_depth("telemetry.raw")
    dlq_depth = await message_broker.get_dlq_depth()

    db_healthy = True
    try:
        async with async_session_factory() as session:
            await session.connection()
    except Exception:
        db_healthy = False

    return {
        "status": "healthy" if db_healthy else "degraded",
        "worker_active": telemetry_worker._running,
        "queue_depth": queue_depth,
        "dlq_depth": dlq_depth,
        "worker_processed_events": telemetry_worker.processed_count,
        "db_status": "connected" if db_healthy else "error",
    }


@router.get("/health", include_in_schema=False)
async def root_health_alias():
    return await health_check()


@router.get("/metrics", summary="Prometheus Exposition Endpoint")
def prometheus_metrics():
    """Scraped by Prometheus server every 5 seconds."""
    return Response(
        content=get_prometheus_metrics(),
        media_type=CONTENT_TYPE_LATEST,
    )
