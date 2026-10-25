"""
Shield Technology Telemetry Ingestion Parser.
Coordinates validation, recursive secret scrubbing, network classification, and hashing.
"""

import copy
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from app.ingestion.enricher import EventHasher, IPEnricher
from app.ingestion.sanitizer import REDACTED_STR, SENSITIVE_KEYS, SensitiveDataSanitizer
from app.schemas.enums import EventTypeEnum, SeverityEnum
from app.schemas.telemetry import RawTelemetryEvent, SanitizedTelemetryEvent


class MalformedLogException(Exception):
    """Raised when an incoming raw log cannot be normalized or validated."""
    pass


class LogParser:
    """Enterprise parser and sanitization engine for security event streams."""

    SENSITIVE_KEYS = SENSITIVE_KEYS
    REDACTED_STR = REDACTED_STR

    @classmethod
    def sanitize_payload(cls, data: Any) -> Any:
        return SensitiveDataSanitizer.sanitize(data)

    @classmethod
    def enrich_ip(cls, ip_str: str) -> Dict[str, Any]:
        return IPEnricher.enrich(ip_str)

    @classmethod
    def compute_event_hash(
        cls,
        agent_id: str,
        timestamp: datetime,
        event_type: str,
        source_ip: str,
        destination_ip: Optional[str],
        payload: Dict[str, Any],
    ) -> Tuple[str, str]:
        return EventHasher.compute_hash(
            agent_id=agent_id,
            timestamp=timestamp,
            event_type=event_type,
            source_ip=source_ip,
            destination_ip=destination_ip,
            payload=payload,
        )

    @classmethod
    def parse_and_sanitize(cls, raw: RawTelemetryEvent) -> SanitizedTelemetryEvent:
        """
        Complete parsing pipeline: validation, sanitization, IP enrichment, and hash computation.
        """
        if not raw.agent_id or not raw.source_ip:
            raise MalformedLogException("Mandatory telemetry fields missing (agent_id, source_ip)")

        # Ensure UTC datetime
        ts = raw.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        else:
            ts = ts.astimezone(timezone.utc)

        # Sanitize sensitive fields in payload
        cleaned_payload = cls.sanitize_payload(copy.deepcopy(raw.payload))

        # Enrich IP
        ip_metadata = cls.enrich_ip(raw.source_ip)

        # Deterministic deduplication hash
        event_type_str = raw.event_type.value if hasattr(raw.event_type, "value") else str(raw.event_type)
        event_hash, _ = cls.compute_event_hash(
            agent_id=raw.agent_id,
            timestamp=ts,
            event_type=event_type_str,
            source_ip=raw.source_ip,
            destination_ip=raw.destination_ip,
            payload=raw.payload,
        )

        return SanitizedTelemetryEvent(
            event_hash=event_hash,
            timestamp=ts,
            agent_id=raw.agent_id,
            severity=raw.severity,
            event_type=raw.event_type,
            source_ip=raw.source_ip,
            destination_ip=raw.destination_ip,
            sanitized_payload=cleaned_payload,
            enrichment=ip_metadata,
            created_at=datetime.now(timezone.utc),
        )
