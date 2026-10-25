"""
Shield Technology Message Broker & Dead Letter Queue (DLQ).
High-throughput async in-memory broker with FIFO semantics, threshold alerts, and poison-pill DLQ.
"""

from abc import ABC, abstractmethod
import asyncio
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("shield.workers.broker")


class BrokerInterface(ABC):
    @abstractmethod
    async def publish(self, queue: str, message: Dict[str, Any]) -> bool:
        pass

    @abstractmethod
    async def publish_dlq(self, original_message: Dict[str, Any], error_reason: str) -> bool:
        pass

    @abstractmethod
    async def get_queue_depth(self, queue: str) -> int:
        pass

    @abstractmethod
    async def get_dlq_depth(self) -> int:
        pass


class MemoryMessageBroker(BrokerInterface):
    """
    High-throughput in-memory async message broker.
    Provides identical queue semantics (FIFO, batch consumption, DLQ) for local testing and high-speed delivery.
    """
    def __init__(self, critical_threshold: int = 5000, webhook_alert_callback=None):
        self.queues: Dict[str, asyncio.Queue] = {}
        self.dlq: List[Dict[str, Any]] = []
        self.critical_threshold = critical_threshold
        self.webhook_alert_callback = webhook_alert_callback
        self.alert_triggered = False

    def _get_queue(self, queue_name: str) -> asyncio.Queue:
        if queue_name not in self.queues:
            self.queues[queue_name] = asyncio.Queue()
        return self.queues[queue_name]

    async def publish(self, queue: str, message: Dict[str, Any]) -> bool:
        q = self._get_queue(queue)
        await q.put(message)

        if q.qsize() >= self.critical_threshold and not self.alert_triggered:
            self.alert_triggered = True
            logger.warning(f"CRITICAL: Queue {queue} exceeded threshold: {q.qsize()} items")
            if self.webhook_alert_callback:
                asyncio.create_task(
                    self.webhook_alert_callback(f"Queue {queue} reached critical depth of {q.qsize()} events.")
                )
        elif q.qsize() < self.critical_threshold:
            self.alert_triggered = False

        return True

    async def publish_dlq(self, original_message: Dict[str, Any], error_reason: str) -> bool:
        dlq_entry = {
            "error_reason": error_reason,
            "failed_payload": original_message,
        }
        self.dlq.append(dlq_entry)
        logger.error(f"[DLQ] Routing failed payload to Dead Letter Queue. Reason: {error_reason}")
        return True

    async def consume_batch(self, queue: str, batch_size: int = 100, timeout_sec: float = 0.1) -> List[Dict[str, Any]]:
        """Drains up to `batch_size` messages or returns on timeout."""
        q = self._get_queue(queue)
        batch = []
        start_time = asyncio.get_event_loop().time()

        while len(batch) < batch_size:
            try:
                item = await asyncio.wait_for(q.get(), timeout=timeout_sec)
                batch.append(item)
                q.task_done()
            except (asyncio.TimeoutError, Exception):
                break

            if asyncio.get_event_loop().time() - start_time > timeout_sec:
                break

        return batch

    async def get_queue_depth(self, queue: str) -> int:
        if queue not in self.queues:
            return 0
        return self.queues[queue].qsize()

    async def get_dlq_depth(self) -> int:
        return len(self.dlq)


# Singleton broker instance for application runtime
message_broker = MemoryMessageBroker()
