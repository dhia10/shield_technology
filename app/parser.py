"""
Shield Technology - Telemetry Log Parser & Sanitizer
Weeks 1-3: Normalization of heterogeneous formats, IP classification, SHA-256 deduplication,
and recursive sensitive data masking (PII/Credentials).
"""

import copy
import hashlib
import ipaddress
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, Set, Tuple

from app.schemas import (
    EventTypeEnum,
    RawTelemetryEvent,
    SanitizedTelemetryEvent,
    SeverityEnum,
)


class MalformedLogException(Exception):
    """Raised when an incoming raw log cannot be normalized or validated."""
    pass


class LogParser:
    """Enterprise parser and sanitization engine for security event streams."""

    SENSITIVE_KEYS: Set[str] = {
        "password",
        "passwd",
        "pwd",
        "token",
        "access_token",
        "refresh_token",
        "secret",
        "api_key",
        "apikey",
        "auth",
        "authorization",
        "credential",
        "private_key",
        "credit_card",
        "card_number",
        "cvv",
        "pin",
    }

    JWT_PATTERN = re.compile(r"eyJ[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+")
    CREDIT_CARD_PATTERN = re.compile(r"\b(?:\d{4}[ -]?){3}\d{4}\b")
    REDACTED_STR = "***REDACTED***"

    @classmethod
    def sanitize_payload(cls, data: Any) -> Any:
        """
        Recursively scans and sanitizes payload dictionaries, lists, and strings.
        Replaces sensitive keys and embedded tokens with '***REDACTED***'.
        """
        if isinstance(data, dict):
            sanitized = {}
            for k, v in data.items():
                lower_key = str(k).lower().strip()
                if any(sensitive in lower_key for sensitive in cls.SENSITIVE_KEYS):
                    sanitized[k] = cls.REDACTED_STR
                else:
                    sanitized[k] = cls.sanitize_payload(v)
            return sanitized

        elif isinstance(data, list):
            return [cls.sanitize_payload(item) for item in data]

        elif isinstance(data, str):
            masked = cls.JWT_PATTERN.sub(cls.REDACTED_STR, data)
            masked = cls.CREDIT_CARD_PATTERN.sub(cls.REDACTED_STR, masked)
            return masked

        return data

    @classmethod
    def enrich_ip(cls, ip_str: str) -> Dict[str, Any]:
        """Classifies IP address metadata (scope, network tier, geographical heuristic)."""
        enrichment = {
            "is_private": False,
            "is_loopback": False,
            "network_class": "PUBLIC_INTERNET",
            "geo_country": "UNKNOWN",
        }
        try:
            ip_obj = ipaddress.ip_address(ip_str.strip())
            enrichment["is_private"] = ip_obj.is_private
            enrichment["is_loopback"] = ip_obj.is_loopback

            if ip_obj.is_private:
                enrichment["network_class"] = "INTERNAL_DEFENSE_SUBNET"
                enrichment["geo_country"] = "LOCAL"
            elif ip_obj.is_loopback:
                enrichment["network_class"] = "HOST_LOOPBACK"
                enrichment["geo_country"] = "LOCAL"
            else:
                enrichment["network_class"] = "EXTERNAL_WAN"
                # Deterministic heuristic for sample IP ranges
                if str(ip_obj).startswith("197.14.") or str(ip_obj).startswith("196.203."):
                    enrichment["geo_country"] = "TN"  # Tunisia (Shield local footprint)
                elif str(ip_obj).startswith("45.") or str(ip_obj).startswith("185."):
                    enrichment["geo_country"] = "EU"
                else:
                    enrichment["geo_country"] = "GLOBAL"
        except ValueError:
            enrichment["network_class"] = "INVALID_OR_HOST"

        return enrichment

    @classmethod
    def compute_event_hash(
        cls,
        agent_id: str,
        timestamp: datetime,
        event_type: str,
        source_ip: str,
        destination_ip: str | None,
        payload: Dict[str, Any],
    ) -> Tuple[str, str]:
        """
        Computes deterministic SHA-256 event hash (for dedup) and raw payload checksum.
        """
        # Canonical string for event identity
        iso_ts = timestamp.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        dest = destination_ip or ""
        identity_str = f"{agent_id}|{iso_ts}|{event_type}|{source_ip}|{dest}"
        event_hash = hashlib.sha256(identity_str.encode("utf-8")).hexdigest()

        # Checksum of raw payload content
        payload_canonical = json.dumps(payload, sort_keys=True, default=str)
        raw_checksum = hashlib.sha256(payload_canonical.encode("utf-8")).hexdigest()

        return event_hash, raw_checksum

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
        event_hash, raw_checksum = cls.compute_event_hash(
            agent_id=raw.agent_id,
            timestamp=ts,
            event_type=raw.event_type.value,
            source_ip=raw.source_ip,
            destination_ip=raw.destination_ip,
            payload=raw.payload,
        )

        return SanitizedTelemetryEvent(
            event_hash=event_hash,
            timestamp=ts,
            agent_id=raw.agent_id,
            tenant_id=getattr(raw, "tenant_id", "default_tenant") or "default_tenant",
            severity=raw.severity,
            event_type=raw.event_type,
            source_ip=raw.source_ip,
            destination_ip=raw.destination_ip,
            sanitized_payload=cleaned_payload,
            raw_checksum=raw_checksum,
            enrichment=ip_metadata,
            is_duplicate=False,
            created_at=datetime.now(timezone.utc),
        )
