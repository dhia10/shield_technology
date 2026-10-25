"""
Shield Technology Telemetry SQLAlchemy ORM Models.
Optimized for high-throughput append-only ingestion and temporal analytical queries.
"""

from datetime import datetime, timezone
import uuid
from sqlalchemy import Boolean, Column, DateTime, Index, JSON, String
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class TelemetryEventModel(Base):
    """
    Persistent security telemetry event table.
    Indexed for fast range filtering on timestamp, severity, and agent.
    """
    __tablename__ = "telemetry_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_hash = Column(String(64), unique=True, nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    agent_id = Column(String(64), nullable=False, index=True)
    severity = Column(String(16), nullable=False, index=True)
    event_type = Column(String(32), nullable=False, index=True)
    source_ip = Column(String(45), nullable=False, index=True)
    destination_ip = Column(String(45), nullable=True)
    sanitized_payload = Column(JSON, nullable=False, default=dict)
    raw_checksum = Column(String(64), nullable=False, default="")
    enrichment = Column(JSON, nullable=False, default=dict)
    is_archived = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Composite temporal indexes
    __table_args__ = (
        Index("ix_telemetry_ts_sev_type", "timestamp", "severity", "event_type"),
        Index("ix_telemetry_agent_ts", "agent_id", "timestamp"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "event_hash": self.event_hash,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "agent_id": self.agent_id,
            "severity": self.severity,
            "event_type": self.event_type,
            "source_ip": self.source_ip,
            "destination_ip": self.destination_ip,
            "sanitized_payload": self.sanitized_payload or {},
            "enrichment": self.enrichment or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
