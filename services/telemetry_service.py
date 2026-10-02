"""
Shield Technology Ingestion & Proprietary Telemetry Service.
High-throughput, asynchronous event buffering & batching engine designed to handle traffic spikes.
Provides real-time pipeline observability and Zero-PII anonymization.
"""

from collections import deque
from datetime import datetime, timezone
import hashlib
import logging
import sqlite3
import threading
import time
from typing import Deque, Dict, List, Optional

from domain.entities import TelemetryEventEntity
from domain.enums import EventType
from domain.schemas import (
    TelemetryBatchCreate,
    TelemetryEventCreate,
    TelemetryMetricsResponse,
)
from infrastructure.config import settings

logger = logging.getLogger("shield.telemetry")


class TelemetryService:
    """
    Thread-safe event ingestion engine featuring memory buffering,
    anonymization (SHA-256 IP hashing), and periodic batch persistence.
    """

    def __init__(
        self,
        buffer_capacity: Optional[int] = None,
        batch_flush_size: Optional[int] = None,
        db_path: Optional[str] = None,
    ):
        self.capacity = buffer_capacity or settings.TELEMETRY_BUFFER_CAPACITY
        self.batch_size = batch_flush_size or settings.TELEMETRY_BATCH_FLUSH_SIZE
        self.db_path = db_path or settings.SQLITE_DB_PATH

        self._buffer: Deque[TelemetryEventEntity] = deque(maxlen=self.capacity)
        self._lock = threading.RLock()

        # Metrics counters
        self._total_received: int = 0
        self._total_flushed: int = 0
        self._error_count: int = 0
        self._events_by_type: Dict[str, int] = {e.value: 0 for e in EventType}
        self._start_time: float = time.time()

        # Initialize SQLite destination table
        self._init_storage()

    def _init_storage(self) -> None:
        """Ensures SQLite persistence table exists."""
        try:
            import os
            os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS telemetry_events (
                        event_id TEXT PRIMARY KEY,
                        event_type TEXT NOT NULL,
                        session_id TEXT NOT NULL,
                        page_path TEXT NOT NULL,
                        element_id TEXT,
                        duration_seconds REAL,
                        ip_hash TEXT,
                        timestamp TEXT NOT NULL
                    )
                    """
                )
                conn.commit()
        except Exception as exc:
            logger.error(f"Failed to initialize telemetry storage: {exc}")
            self._error_count += 1

    def _hash_ip(self, ip_address: Optional[str]) -> Optional[str]:
        """One-way SHA-256 IP pseudonymization (GDPR Zero-PII compliance)."""
        if not ip_address:
            return None
        salt = "shield_telemetry_salt_v1"
        return hashlib.sha256(f"{ip_address}:{salt}".encode("utf-8")).hexdigest()[:16]

    def ingest_event(
        self, event: TelemetryEventCreate, ip_address: Optional[str] = None
    ) -> bool:
        """
        Accepts an event into the high-speed in-memory buffer.
        Triggers automatic batch flush if batch threshold is reached.
        """
        entity = TelemetryEventEntity(
            event_type=event.event_type,
            session_id=event.session_id,
            page_path=event.page_path,
            element_id=event.element_id,
            duration_seconds=event.duration_seconds,
            ip_hash=self._hash_ip(ip_address),
            metadata=event.metadata,
        )

        with self._lock:
            self._buffer.append(entity)
            self._total_received += 1
            self._events_by_type[event.event_type.value] = (
                self._events_by_type.get(event.event_type.value, 0) + 1
            )
            should_flush = len(self._buffer) >= self.batch_size

        if should_flush:
            self.flush()

        return True

    def ingest_batch(
        self, batch: TelemetryBatchCreate, ip_address: Optional[str] = None
    ) -> int:
        """Batch ingestion for client telemetry sendBeacon payloads."""
        accepted = 0
        for ev in batch.events:
            if self.ingest_event(ev, ip_address=ip_address):
                accepted += 1
        return accepted

    def flush(self) -> int:
        """Drains the in-memory buffer to persistent storage."""
        with self._lock:
            if not self._buffer:
                return 0
            items_to_persist = list(self._buffer)
            self._buffer.clear()

        try:
            records = [
                (
                    e.event_id,
                    e.event_type.value,
                    e.session_id,
                    e.page_path,
                    e.element_id,
                    e.duration_seconds,
                    e.ip_hash,
                    e.timestamp.isoformat(),
                )
                for e in items_to_persist
            ]
            with sqlite3.connect(self.db_path) as conn:
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO telemetry_events 
                    (event_id, event_type, session_id, page_path, element_id, duration_seconds, ip_hash, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    records,
                )
                conn.commit()

            with self._lock:
                self._total_flushed += len(items_to_persist)
            return len(items_to_persist)
        except Exception as exc:
            logger.error(f"Error persisting telemetry batch: {exc}")
            with self._lock:
                self._error_count += 1
            return 0

    def get_metrics(self) -> TelemetryMetricsResponse:
        """Returns real-time pipeline operational metrics."""
        now = time.time()
        uptime = max(0.001, now - self._start_time)
        with self._lock:
            current_size = len(self._buffer)
            total = self._total_received
            flushed = self._total_flushed
            errors = self._error_count
            breakdown = dict(self._events_by_type)

        hourly_estimate = round((total / uptime) * 3600, 2)

        return TelemetryMetricsResponse(
            total_events_received=total,
            total_batches_flushed=flushed,
            current_buffer_size=current_size,
            buffer_capacity=self.capacity,
            error_count=errors,
            events_by_type=breakdown,
            hourly_throughput_estimate=hourly_estimate,
            uptime_seconds=round(uptime, 2),
        )

    def get_buffer_utilization(self) -> float:
        with self._lock:
            return round((len(self._buffer) / self.capacity) * 100.0, 2)


# Global singleton instance
telemetry_service = TelemetryService()
