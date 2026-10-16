"""
Shield Technology - Backpressure & Ring Buffer Controller.
Protects event stream pipelines from memory exhaustion during traffic spikes (up to 50,000 ev/s).
Features dynamic watermarks and priority-based load shedding (preserving CRITICAL logs).
"""

from collections import deque
from enum import Enum
import logging
import threading
import time
from typing import Any, Deque, Dict, List, Optional, Tuple

from app.schemas import RawTelemetryEvent, SeverityEnum

logger = logging.getLogger("shield.backpressure")


class BackpressureState(str, Enum):
    NORMAL = "NORMAL"            # Buffer utilization < 50%
    THROTTLED = "THROTTLED"      # Buffer utilization between 50% and 85%
    LOAD_SHEDDING = "LOAD_SHEDDING" # Buffer utilization > 85%, shedding low priority


class RingBufferBackpressureController:
    """
    High-performance circular memory buffer with adaptive backpressure policies.
    """

    def __init__(
        self,
        capacity: int = 10000,
        low_watermark_ratio: float = 0.50,
        high_watermark_ratio: float = 0.85,
    ):
        self.capacity = capacity
        self.low_watermark = int(capacity * low_watermark_ratio)
        self.high_watermark = int(capacity * high_watermark_ratio)

        self._buffer: Deque[RawTelemetryEvent] = deque()
        self._lock = threading.RLock()

        # Telemetry metrics
        self.total_enqueued = 0
        self.total_dequeued = 0
        self.total_dropped_low_priority = 0
        self.total_dropped_overflow = 0

    @property
    def current_size(self) -> int:
        with self._lock:
            return len(self._buffer)

    @property
    def utilization_ratio(self) -> float:
        with self._lock:
            return len(self._buffer) / self.capacity

    @property
    def state(self) -> BackpressureState:
        size = self.current_size
        if size >= self.high_watermark:
            return BackpressureState.LOAD_SHEDDING
        if size >= self.low_watermark:
            return BackpressureState.THROTTLED
        return BackpressureState.NORMAL

    def enqueue(self, event: RawTelemetryEvent) -> Tuple[bool, str]:
        """
        Enqueues an event according to priority and current buffer state.
        Returns (accepted: bool, reason: str).
        """
        with self._lock:
            curr = len(self._buffer)

            # Case 1: Extreme Buffer Exhaustion (Buffer full)
            if curr >= self.capacity:
                if event.severity in (SeverityEnum.CRITICAL, SeverityEnum.HIGH):
                    # Evict oldest low severity to make room for critical incident
                    for i in range(len(self._buffer)):
                        if self._buffer[i].severity in (SeverityEnum.LOW, SeverityEnum.MEDIUM):
                            del self._buffer[i]
                            self._buffer.append(event)
                            self.total_enqueued += 1
                            self.total_dropped_low_priority += 1
                            return True, "ACCEPTED_WITH_PRIORITY_EVICTION"
                self.total_dropped_overflow += 1
                return False, "DROPPED_BUFFER_OVERFLOW"

            # Case 2: Load Shedding active (> 85%)
            if curr >= self.high_watermark:
                if event.severity == SeverityEnum.LOW:
                    self.total_dropped_low_priority += 1
                    return False, "SHED_LOW_SEVERITY_DURING_SPIKE"

            # Case 3: Accepted
            self._buffer.append(event)
            self.total_enqueued += 1
            return True, "ACCEPTED"

    def dequeue_batch(self, batch_size: int = 200) -> List[RawTelemetryEvent]:
        """Drains a batch of events atomically for downstream worker persistence."""
        with self._lock:
            drained = []
            while self._buffer and len(drained) < batch_size:
                drained.append(self._buffer.popleft())
            self.total_dequeued += len(drained)
            return drained

    def get_metrics(self) -> Dict[str, Any]:
        with self._lock:
            curr = len(self._buffer)
            return {
                "capacity": self.capacity,
                "current_size": curr,
                "utilization_percent": round((curr / self.capacity) * 100.0, 2),
                "state": self.state.value,
                "total_enqueued": self.total_enqueued,
                "total_dequeued": self.total_dequeued,
                "dropped_low_priority": self.total_dropped_low_priority,
                "dropped_overflow": self.total_dropped_overflow,
            }
