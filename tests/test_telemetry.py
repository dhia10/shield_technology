"""
Unit tests for Shield Technology Ingestion & Telemetry Service.
Verifies memory buffer dynamics, batching thresholds, zero-PII hashing, and metrics.
"""

import sqlite3
import pytest
from pydantic import ValidationError

from domain.enums import EventType
from domain.schemas import TelemetryBatchCreate, TelemetryEventCreate


def test_ingest_single_event(isolated_telemetry_service):
    """Verifies that an incoming event enters the buffer and increments metrics."""
    svc = isolated_telemetry_service
    event = TelemetryEventCreate(
        event_type=EventType.CTA_CLICK,
        session_id="test_sess_1234",
        page_path="/produits/cameras",
        element_id="btn_devis_pro",
    )

    result = svc.ingest_event(event, ip_address="196.203.45.10")
    assert result is True

    metrics = svc.get_metrics()
    assert metrics.total_events_received == 1
    assert metrics.events_by_type[EventType.CTA_CLICK.value] == 1


def test_ip_pseudonymization_zero_pii(isolated_telemetry_service):
    """Guarantees that raw client IPs are never stored in plaintext."""
    svc = isolated_telemetry_service
    raw_ip = "197.14.32.88"
    event = TelemetryEventCreate(
        event_type=EventType.PAGE_VIEW,
        session_id="test_sess_pii",
        page_path="/services",
    )

    svc.ingest_event(event, ip_address=raw_ip)
    svc.flush()

    with sqlite3.connect(svc.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT ip_hash FROM telemetry_events WHERE session_id = ?", ("test_sess_pii",))
        row = cursor.fetchone()
        assert row is not None
        stored_hash = row[0]

        # Stored value must be a hash, never the raw IP
        assert stored_hash is not None
        assert raw_ip not in stored_hash
        assert len(stored_hash) == 16


def test_batch_ingestion_and_auto_flush(isolated_telemetry_service):
    """Verifies that reaching batch_flush_size (5) triggers automatic flush to SQLite."""
    svc = isolated_telemetry_service
    events = [
        TelemetryEventCreate(
            event_type=EventType.FUNNEL_STEP,
            session_id=f"sess_{i}",
            page_path="/contact",
            element_id=f"step_{i}",
        )
        for i in range(5)
    ]
    batch = TelemetryBatchCreate(events=events)

    accepted = svc.ingest_batch(batch)
    assert accepted == 5

    # Buffer should have auto-flushed because batch_size is 5
    metrics = svc.get_metrics()
    assert metrics.total_events_received == 5
    assert metrics.total_batches_flushed >= 5

    # Verify rows persisted in SQLite
    with sqlite3.connect(svc.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM telemetry_events")
        count = cursor.fetchone()[0]
        assert count == 5


def test_telemetry_payload_validation():
    """Ensures Pydantic blocks malformed telemetry packets."""
    # Invalid event_type
    with pytest.raises(ValidationError):
        TelemetryEventCreate(
            event_type="INVALID_NON_EXISTENT_TYPE",
            session_id="sess_123",
            page_path="/",
        )

    # Session ID too short
    with pytest.raises(ValidationError):
        TelemetryEventCreate(
            event_type=EventType.CTA_CLICK,
            session_id="a",
            page_path="/",
        )

    # Duration negative
    with pytest.raises(ValidationError):
        TelemetryEventCreate(
            event_type=EventType.TIME_SPENT,
            session_id="sess_valid",
            page_path="/",
            duration_seconds=-10.0,
        )


def test_buffer_utilization_calculation(isolated_telemetry_service):
    """Verifies queue occupancy percentage calculation."""
    svc = isolated_telemetry_service
    assert svc.get_buffer_utilization() == 0.0

    for i in range(3):
        svc.ingest_event(
            TelemetryEventCreate(
                event_type=EventType.PAGE_VIEW,
                session_id=f"sess_{i}",
                page_path="/",
            )
        )

    # 3 out of 100 capacity = 3.0%
    assert svc.get_buffer_utilization() == 3.0
