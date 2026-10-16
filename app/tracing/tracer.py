"""
Shield Technology - OpenTelemetry Distributed Tracing Engine.
Generates W3C-compliant trace contexts, manages span parent-child hierarchies,
and measures end-to-end traversal latency across distributed microservices.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import random
import time
from typing import Any, Dict, List, Optional
import uuid


@dataclass
class Span:
    name: str
    trace_id: str
    span_id: str
    parent_span_id: Optional[str]
    start_time_ns: int
    end_time_ns: Optional[int] = None
    tags: Dict[str, Any] = field(default_factory=dict)
    logs: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def duration_ms(self) -> float:
        if self.end_time_ns is None:
            return 0.0
        return (self.end_time_ns - self.start_time_ns) / 1_000_000.0

    def finish(self):
        self.end_time_ns = time.perf_counter_ns()

    def log(self, message: str, **payload):
        self.logs.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": message,
            "data": payload,
        })

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "duration_ms": round(self.duration_ms, 3),
            "tags": self.tags,
            "logs": self.logs,
        }


class DistributedTracer:
    """
    Tracer maintaining in-flight and completed spans across microservice boundaries.
    """

    def __init__(self, service_name: str = "shield-telemetry-engine"):
        self.service_name = service_name
        self._completed_traces: Dict[str, List[Span]] = {}

    @staticmethod
    def generate_trace_id() -> str:
        return uuid.uuid4().hex

    @staticmethod
    def generate_span_id() -> str:
        return f"{random.getrandbits(64):016x}"

    def start_span(
        self,
        name: str,
        trace_id: Optional[str] = None,
        parent_span_id: Optional[str] = None,
        tags: Optional[Dict[str, Any]] = None,
    ) -> Span:
        t_id = trace_id or self.generate_trace_id()
        s_id = self.generate_span_id()
        base_tags = {"service.name": self.service_name}
        if tags:
            base_tags.update(tags)

        span = Span(
            name=name,
            trace_id=t_id,
            span_id=s_id,
            parent_span_id=parent_span_id,
            start_time_ns=time.perf_counter_ns(),
            tags=base_tags,
        )
        return span

    def record_span(self, span: Span):
        """Records a finished span into the trace index."""
        if span.end_time_ns is None:
            span.finish()

        if span.trace_id not in self._completed_traces:
            self._completed_traces[span.trace_id] = []
        self._completed_traces[span.trace_id].append(span)

    def get_trace(self, trace_id: str) -> List[Dict[str, Any]]:
        spans = self._completed_traces.get(trace_id, [])
        return [s.to_dict() for s in spans]

    def generate_sample_trace(self) -> Dict[str, Any]:
        """Synthesizes a realistic end-to-end trace across 5 microservice hops."""
        trace_id = self.generate_trace_id()

        # Hop 1: gRPC Gateway Ingestion
        s1 = self.start_span("grpc_gateway_ingest", trace_id=trace_id, tags={"protocol": "gRPC/HTTP2", "agent.id": "probe-tunis-01"})
        time.sleep(0.0008) # 0.8ms
        s1.log("Decoded binary protobuf payload", bytes=342)
        s1.finish()
        self.record_span(s1)

        # Hop 2: Ring Buffer & Backpressure check
        s2 = self.start_span("ring_buffer_enqueue", trace_id=trace_id, parent_span_id=s1.span_id, tags={"buffer.utilization": "24.5%"})
        time.sleep(0.0003) # 0.3ms
        s2.log("Enqueued into circular buffer")
        s2.finish()
        self.record_span(s2)

        # Hop 3: Stream Rules Engine & Anomaly Detection
        s3 = self.start_span("stream_rules_evaluation", trace_id=trace_id, parent_span_id=s2.span_id, tags={"rules.evaluated": 3})
        time.sleep(0.0012) # 1.2ms
        s3.log("Pattern matched: DDOS_SYN_FLOOD", severity="CRITICAL")
        s3.finish()
        self.record_span(s3)

        # Hop 4: PostgreSQL Bulk Upsert Transaction
        s4 = self.start_span("postgres_bulk_upsert", trace_id=trace_id, parent_span_id=s3.span_id, tags={"db.table": "telemetry_events", "batch.size": 100})
        time.sleep(0.0028) # 2.8ms
        s4.log("Committed transaction with ON CONFLICT DO UPDATE")
        s4.finish()
        self.record_span(s4)

        # Hop 5: WebSocket Real-Time Alert Broadcast
        s5 = self.start_span("websocket_soc_dispatch", trace_id=trace_id, parent_span_id=s3.span_id, tags={"clients.notified": 8})
        time.sleep(0.0006) # 0.6ms
        s5.log("Dispatched alert payload to connected SOC rooms")
        s5.finish()
        self.record_span(s5)

        total_latency = (
            s1.duration_ms + s2.duration_ms + s3.duration_ms + s4.duration_ms + s5.duration_ms
        )

        return {
            "trace_id": trace_id,
            "root_service": self.service_name,
            "total_spans": 5,
            "total_latency_ms": round(total_latency, 3),
            "w3c_traceparent": f"00-{trace_id}-{s1.span_id}-01",
            "spans": self.get_trace(trace_id),
        }


# Singleton tracer instance
distributed_tracer = DistributedTracer()
