"""
Pydantic v2 Telemetry Schemas and Validators.
Strict contracts for raw probe logs, sanitized events, batch ingestion, and analytical queries.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.enums import EventTypeEnum, SeverityEnum


class RawTelemetryEvent(BaseModel):
    """Raw telemetry event as emitted by edge security probes."""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    agent_id: str = Field(..., min_length=2, max_length=64)
    tenant_id: Optional[str] = "default_tenant"
    severity: SeverityEnum = Field(default=SeverityEnum.MEDIUM)
    event_type: EventTypeEnum = Field(default=EventTypeEnum.ANOMALOUS_PAYLOAD)
    source_ip: str = Field(..., min_length=3, max_length=45)
    destination_ip: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore")


class SanitizedTelemetryEvent(BaseModel):
    """Enriched, sanitized, and ML-scored telemetry event."""
    id: Optional[Union[str, int]] = None
    event_hash: str = Field(..., description="Deterministic SHA-256 fingerprint")
    timestamp: datetime
    agent_id: str
    tenant_id: Optional[str] = "default_tenant"
    severity: SeverityEnum
    event_type: EventTypeEnum
    source_ip: str
    destination_ip: Optional[str] = None
    sanitized_payload: Dict[str, Any] = Field(default_factory=dict)
    raw_checksum: Optional[str] = ""
    enrichment: Dict[str, Any] = Field(default_factory=dict)
    entropy_score: Optional[float] = Field(None, description="Shannon entropy H(X)")
    anomaly_score: Optional[float] = Field(None, description="Isolation Forest threat score")
    escalated_by_ml: bool = Field(default=False)
    is_duplicate: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(from_attributes=True, extra="ignore")


class TelemetryIngestRequest(BaseModel):
    """Batch ingestion payload from authorized probes."""
    events: List[RawTelemetryEvent] = Field(..., min_length=1, max_length=5000)


class TelemetryIngestResponse(BaseModel):
    """Fast non-blocking acknowledgment returned upon queue dispatch."""
    status: str = "accepted"
    accepted_count: int
    queue_name: str = "telemetry.raw"
    ingest_latency_ms: Optional[float] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TelemetryHistoryResponse(BaseModel):
    """Cursor-paginated telemetry history."""
    items: List[SanitizedTelemetryEvent]
    next_cursor: Optional[str] = None
    has_more: bool = False
    total_count: Optional[int] = None


class TelemetryStatsResponse(BaseModel):
    """Real-time aggregated platform statistics."""
    total_events: int = 0
    events_per_second: float = 0.0
    critical_events_count: int = 0
    severity_distribution: Dict[str, int] = Field(default_factory=dict)
    top_threat_event_types: Dict[str, int] = Field(default_factory=dict)
    window_minutes: int = 60
    cached: bool = False
    window_hours: Optional[int] = None
    by_severity: Optional[Dict[str, int]] = None
    by_event_type: Optional[Dict[str, int]] = None
    top_source_ips: Optional[List[Dict[str, Any]]] = None
    cache_hit: Optional[bool] = None
    generated_at: Optional[datetime] = None
