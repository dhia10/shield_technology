"""
Shield Technology - Telemetry Schemas (Pydantic v2)
Weeks 1-3: Validation, Normalization, and Serialization schemas for the telemetry pipeline.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class SeverityEnum(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class EventTypeEnum(str, Enum):
    AUTH_ATTEMPT = "AUTH_ATTEMPT"
    SSH_BRUTE_FORCE = "SSH_BRUTE_FORCE"
    PORT_SCAN = "PORT_SCAN"
    MALWARE_DETECTED = "MALWARE_DETECTED"
    DDOS_FLOOD = "DDOS_FLOOD"
    SYSTEM_HEARTBEAT = "SYSTEM_HEARTBEAT"
    FIREWALL_DROP = "FIREWALL_DROP"
    SQL_INJECTION_ATTEMPT = "SQL_INJECTION_ATTEMPT"


class RawTelemetryEvent(BaseModel):
    """Raw incoming telemetry event from monitoring probes / agents."""
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Event creation timestamp (ISO 8601 UTC)"
    )
    agent_id: str = Field(..., min_length=3, max_length=64, description="Unique probe/agent identifier")
    tenant_id: Optional[str] = Field(default="default_tenant", max_length=64, description="Tenant identifier for multi-tenant isolation")
    severity: SeverityEnum = Field(default=SeverityEnum.LOW, description="Alert severity level")
    event_type: EventTypeEnum = Field(..., description="Categorized security event type")
    source_ip: str = Field(..., min_length=7, max_length=45, description="Source IP address or hostname")
    destination_ip: Optional[str] = Field(default=None, max_length=45, description="Target IP address")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary context data (headers, params, etc.)")

    @field_validator("agent_id")
    @classmethod
    def validate_agent_id(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("agent_id cannot be blank")
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "timestamp": "2026-06-15T10:30:00Z",
                "agent_id": "probe-tunis-dc-01",
                "severity": "CRITICAL",
                "event_type": "SQL_INJECTION_ATTEMPT",
                "source_ip": "197.14.88.22",
                "destination_ip": "10.0.0.5",
                "payload": {
                    "uri": "/api/v1/auth/login",
                    "method": "POST",
                    "username": "admin' OR '1'='1",
                    "password": "ClearTextPassword123!",
                    "user_agent": "sqlmap/1.7"
                }
            }
        }
    }


class SanitizedTelemetryEvent(BaseModel):
    """Normalized, sanitized, and deduplicated telemetry event ready for persistence."""
    id: Optional[str] = None
    event_hash: str = Field(..., description="Deterministic SHA-256 hash for deduplication")
    timestamp: datetime
    agent_id: str
    tenant_id: Optional[str] = "default_tenant"
    severity: SeverityEnum
    event_type: EventTypeEnum
    source_ip: str
    destination_ip: Optional[str] = None
    sanitized_payload: Dict[str, Any] = Field(default_factory=dict)
    raw_checksum: str
    enrichment: Dict[str, Any] = Field(default_factory=dict)
    is_duplicate: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TelemetryIngestRequest(BaseModel):
    """Payload accepted by POST /api/v1/telemetry/ingest (single event or batch)."""
    events: List[RawTelemetryEvent] = Field(..., min_length=1, max_length=5000)


class TelemetryIngestResponse(BaseModel):
    status: str = "accepted"
    accepted_count: int
    queue_name: str
    dropped_count: int = 0
    ingest_latency_ms: float
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TelemetryHistoryItem(BaseModel):
    id: str
    event_hash: str
    timestamp: datetime
    agent_id: str
    severity: str
    event_type: str
    source_ip: str
    destination_ip: Optional[str] = None
    sanitized_payload: Dict[str, Any]
    enrichment: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class TelemetryHistoryResponse(BaseModel):
    items: List[TelemetryHistoryItem]
    next_cursor: Optional[str] = None
    has_more: bool = False
    total_returned: int


class TelemetryStatsResponse(BaseModel):
    window_hours: int
    total_events: int
    by_severity: Dict[str, int]
    by_event_type: Dict[str, int]
    top_source_ips: List[Dict[str, Any]]
    cache_hit: bool = False
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
