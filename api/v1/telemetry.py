"""
Shield Technology Telemetry API Controller.
High-throughput ingestion endpoints for user behavioral interactions.
"""

from typing import Union
from fastapi import APIRouter, BackgroundTasks, Request, status
from domain.schemas import (
    TelemetryBatchCreate,
    TelemetryEventCreate,
    TelemetryIngestResponse,
    TelemetryMetricsResponse,
)
from services.telemetry_service import telemetry_service

router = APIRouter(prefix="/telemetry", tags=["Telemetry & Ingestion"])


@router.post(
    "/events",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=TelemetryIngestResponse,
    summary="Ingest Client Telemetry Events (Non-blocking)",
    description="Accepts single event or batch from navigator.sendBeacon or fetch.",
)
async def ingest_telemetry_events(
    payload: Union[TelemetryBatchCreate, TelemetryEventCreate],
    request: Request,
    background_tasks: BackgroundTasks,
) -> TelemetryIngestResponse:
    client_ip = request.client.host if request.client else None

    if isinstance(payload, TelemetryBatchCreate):
        accepted_count = telemetry_service.ingest_batch(payload, ip_address=client_ip)
    else:
        accepted = telemetry_service.ingest_event(payload, ip_address=client_ip)
        accepted_count = 1 if accepted else 0

    return TelemetryIngestResponse(
        status="accepted",
        count=accepted_count,
        buffer_utilization_pct=telemetry_service.get_buffer_utilization(),
    )


@router.get(
    "/metrics",
    response_model=TelemetryMetricsResponse,
    summary="Telemetry Pipeline Metrics & Integrity Observability",
)
async def get_telemetry_metrics() -> TelemetryMetricsResponse:
    return telemetry_service.get_metrics()
