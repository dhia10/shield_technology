"""
Shield Technology Async Telemetry Worker & Batch Consumer.
Consumes broker queues in batches, applies LogParser and ML anomaly scoring,
executes high-speed bulk upsert into PostgreSQL/SQLite, and routes poison payloads to the DLQ.
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Tuple

from app.ingestion.parser import LogParser, MalformedLogException
from app.metrics import (
    DB_BULK_INSERT_DURATION_SECONDS,
    DLQ_EVENTS_TOTAL,
    QUEUE_DEPTH_GAUGE,
)
from app.ml.scorer import ml_anomaly_scorer
from app.schemas.telemetry import RawTelemetryEvent, SanitizedTelemetryEvent
from app.storage.database import async_session_factory
from app.storage.repository import TelemetryRepository
from app.workers.broker import message_broker

logger = logging.getLogger("shield.workers.worker")


class TelemetryWorker:
    def __init__(self, broker=message_broker, queue_name: str = "telemetry.raw", batch_size: int = 100):
        self.broker = broker
        self.queue_name = queue_name
        self.batch_size = batch_size
        self._running = False
        self.processed_count = 0
        self.dlq_count = 0

    async def process_batch(self, raw_items: List[Dict[str, Any]]) -> Tuple[int, int]:
        """
        Parses, sanitizes, scores via ML, and bulk-inserts a batch of raw log messages.
        Corrupt messages are safely dispatched to the DLQ.
        """
        if not raw_items:
            return 0, 0

        valid_events: List[SanitizedTelemetryEvent] = []
        dlq_sent = 0

        for item in raw_items:
            try:
                # 1. Pydantic schema validation
                raw_event = RawTelemetryEvent(**item)
                # 2. Parsing, enrichment, and credential masking
                sanitized_event = LogParser.parse_and_sanitize(raw_event)
                # 3. Machine Learning Anomaly Detection & Autonomous Escalation
                ml_anomaly_scorer.score_and_enrich_event(sanitized_event)
                valid_events.append(sanitized_event)
            except Exception as exc:
                dlq_sent += 1
                self.dlq_count += 1
                try:
                    DLQ_EVENTS_TOTAL.labels(reason=str(exc)[:50]).inc()
                except Exception:
                    pass
                await self.broker.publish_dlq(item, error_reason=str(exc))

        # 4. High-throughput Bulk Insert for valid events
        inserted = 0
        if valid_events:
            t0 = time.perf_counter()
            async with async_session_factory() as session:
                repo = TelemetryRepository(session)
                inserted = await repo.bulk_insert(valid_events)
                self.processed_count += inserted
            elapsed_sec = time.perf_counter() - t0
            try:
                DB_BULK_INSERT_DURATION_SECONDS.observe(elapsed_sec)
            except Exception:
                pass

        depth = await self.broker.get_queue_depth(self.queue_name)
        try:
            QUEUE_DEPTH_GAUGE.labels(queue_name=self.queue_name).set(depth)
        except Exception:
            pass

        return inserted, dlq_sent

    async def run_once(self, timeout_sec: float = 0.05) -> Tuple[int, int]:
        """Runs a single batch drain iteration (ideal for testing and benchmarking)."""
        raw_items = await self.broker.consume_batch(self.queue_name, batch_size=self.batch_size, timeout_sec=timeout_sec)
        return await self.process_batch(raw_items)

    async def start(self) -> None:
        """Continuous background worker loop."""
        self._running = True
        logger.info(f"Telemetry Worker started on queue '{self.queue_name}' (batch={self.batch_size})")

        while self._running:
            try:
                inserted, dlq = await self.run_once(timeout_sec=0.1)
                if inserted == 0 and dlq == 0:
                    await asyncio.sleep(0.05)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"Worker loop exception: {exc}")
                await asyncio.sleep(0.2)

    def stop(self) -> None:
        self._running = False


# Application worker instance
telemetry_worker = TelemetryWorker()
