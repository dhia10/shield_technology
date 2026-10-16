"""
Shield Technology - Real-Time Stream Processing & Windowing Engine.
Implements tumbling and sliding time-windows to compute high-velocity security aggregations.
"""

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
import threading
import time
from typing import Any, Deque, Dict, List, Optional, Tuple

from app.schemas import RawTelemetryEvent, SeverityEnum


@dataclass
class WindowAggregate:
    window_start_ms: int
    window_end_ms: int
    total_events: int = 0
    critical_count: int = 0
    high_count: int = 0
    event_counts_by_type: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    unique_sources: set = field(default_factory=set)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "window_start": datetime.fromtimestamp(self.window_start_ms / 1000.0, tz=timezone.utc).isoformat(),
            "window_end": datetime.fromtimestamp(self.window_end_ms / 1000.0, tz=timezone.utc).isoformat(),
            "duration_sec": (self.window_end_ms - self.window_start_ms) / 1000.0,
            "total_events": self.total_events,
            "critical_count": self.critical_count,
            "high_count": self.high_count,
            "events_by_type": dict(self.event_counts_by_type),
            "unique_source_ips": len(self.unique_sources),
        }


class StreamPipeline:
    """
    Stream processing pipeline executing rolling window calculations.
    """

    def __init__(self, tumbling_window_sec: int = 10, sliding_window_sec: int = 30):
        self.tumbling_sec = tumbling_window_sec
        self.sliding_sec = sliding_window_sec

        self._recent_events: Deque[Tuple[float, RawTelemetryEvent]] = deque()
        self._lock = threading.RLock()
        self.completed_tumbling_windows: List[WindowAggregate] = []

    def ingest_event(self, event: RawTelemetryEvent):
        """Streams an event into the rolling window accumulator."""
        now = time.time()
        with self._lock:
            self._recent_events.append((now, event))
            cutoff = now - (self.sliding_sec * 2)
            while self._recent_events and self._recent_events[0][0] < cutoff:
                self._recent_events.popleft()

    def compute_sliding_window(self) -> WindowAggregate:
        """Computes instantaneous metrics over the last `sliding_sec` seconds."""
        now = time.time()
        window_start = now - self.sliding_sec
        agg = WindowAggregate(
            window_start_ms=int(window_start * 1000),
            window_end_ms=int(now * 1000),
        )

        with self._lock:
            for t, ev in self._recent_events:
                if t >= window_start:
                    agg.total_events += 1
                    if ev.severity == SeverityEnum.CRITICAL:
                        agg.critical_count += 1
                    elif ev.severity == SeverityEnum.HIGH:
                        agg.high_count += 1
                    agg.event_counts_by_type[ev.event_type.value] += 1
                    agg.unique_sources.add(ev.source_ip)

        return agg

    def trigger_tumbling_window_flush(self) -> WindowAggregate:
        """Closes the current tumbling window and archives its computed aggregates."""
        now = time.time()
        window_start = now - self.tumbling_sec
        agg = WindowAggregate(
            window_start_ms=int(window_start * 1000),
            window_end_ms=int(now * 1000),
        )

        with self._lock:
            for t, ev in self._recent_events:
                if window_start <= t <= now:
                    agg.total_events += 1
                    if ev.severity == SeverityEnum.CRITICAL:
                        agg.critical_count += 1
                    elif ev.severity == SeverityEnum.HIGH:
                        agg.high_count += 1
                    agg.event_counts_by_type[ev.event_type.value] += 1
                    agg.unique_sources.add(ev.source_ip)

            self.completed_tumbling_windows.append(agg)
            if len(self.completed_tumbling_windows) > 50:
                self.completed_tumbling_windows.pop(0)

        return agg
