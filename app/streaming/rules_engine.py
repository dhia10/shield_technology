"""
Shield Technology - Real-Time Security Rules & Correlation Engine.
Evaluates high-velocity telemetry logs against pattern signatures and threshold conditions.
Produces instantaneous correlated alerts (< 2.0 ms execution overhead).
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import re
import time
from typing import Any, Dict, List, Optional, Tuple
import uuid

from app.schemas import EventTypeEnum, RawTelemetryEvent, SeverityEnum


@dataclass
class SecurityAlert:
    alert_id: str
    timestamp: datetime
    tenant_id: str
    rule_name: str
    severity: SeverityEnum
    description: str
    source_ip: str
    event_type: EventTypeEnum
    correlation_score: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "timestamp": self.timestamp.isoformat(),
            "tenant_id": self.tenant_id,
            "rule_name": self.rule_name,
            "severity": self.severity.value,
            "description": self.description,
            "source_ip": self.source_ip,
            "event_type": self.event_type.value,
            "correlation_score": self.correlation_score,
        }


class RulesEngine:
    """
    In-memory rules engine evaluating stateful and stateless threat signatures.
    """

    SQLI_PATTERNS = [
        re.compile(r"\b(UNION\s+SELECT|SELECT\s+.*FROM|DROP\s+TABLE|1\s*=\s*1|OR\s+'1'='1')\b", re.IGNORECASE),
        re.compile(r"(--|/\*|\*/|@@version|exec\s*\(|xp_cmdshell)", re.IGNORECASE),
    ]

    def __init__(self):
        self.rules_evaluated = 0
        self.alerts_generated = 0

    def evaluate_event(self, event: RawTelemetryEvent) -> Optional[SecurityAlert]:
        """Runs the rule suite against an ingested event."""
        self.rules_evaluated += 1
        payload = event.payload or {}
        source_ip = event.source_ip
        tenant_id = getattr(event, "tenant_id", "default_tenant") or "default_tenant"

        # Rule 1: High Volume Distributed Denial of Service (SYN Flood)
        if event.event_type == EventTypeEnum.DDOS_FLOOD:
            syn_rate = payload.get("syn_rate_pps", 0)
            if syn_rate > 50000:
                self.alerts_generated += 1
                return SecurityAlert(
                    alert_id=f"alt-ddos-{uuid.uuid4().hex[:8]}",
                    timestamp=datetime.now(timezone.utc),
                    tenant_id=tenant_id,
                    rule_name="RULE_CRITICAL_DDOS_HIGH_PPS",
                    severity=SeverityEnum.CRITICAL,
                    description=f"SYN Flood surge detected ({syn_rate:,} pps) targeting infrastructure from {source_ip}",
                    source_ip=source_ip,
                    event_type=event.event_type,
                    correlation_score=0.98,
                )

        # Rule 2: SQL Injection Attempt with Dangerous Keywords
        payload_str = str(payload)
        for pattern in self.SQLI_PATTERNS:
            if pattern.search(payload_str):
                self.alerts_generated += 1
                return SecurityAlert(
                    alert_id=f"alt-sqli-{uuid.uuid4().hex[:8]}",
                    timestamp=datetime.now(timezone.utc),
                    tenant_id=tenant_id,
                    rule_name="RULE_HIGH_SQL_INJECTION_SIGNATURE",
                    severity=SeverityEnum.HIGH,
                    description=f"SQL injection syntax detected in payload parameters from {source_ip}",
                    source_ip=source_ip,
                    event_type=EventTypeEnum.SQL_INJECTION_ATTEMPT,
                    correlation_score=0.92,
                )

        # Rule 3: SSH Brute Force Dictionary Burst
        if event.event_type == EventTypeEnum.SSH_BRUTE_FORCE:
            failed_attempts = payload.get("failed_attempts", 0)
            if failed_attempts > 15:
                self.alerts_generated += 1
                return SecurityAlert(
                    alert_id=f"alt-ssh-{uuid.uuid4().hex[:8]}",
                    timestamp=datetime.now(timezone.utc),
                    tenant_id=tenant_id,
                    rule_name="RULE_HIGH_SSH_BRUTE_FORCE_THRESHOLD",
                    severity=SeverityEnum.HIGH,
                    description=f"SSH authentication brute-force attempt ({failed_attempts} failed attempts) from {source_ip}",
                    source_ip=source_ip,
                    event_type=event.event_type,
                    correlation_score=0.88,
                )

        return None


# Singleton instance
rules_engine = RulesEngine()
