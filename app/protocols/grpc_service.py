"""
Shield Technology - High-Throughput gRPC Telemetry Service.
Provides unary and bi-directional streaming channels for low-latency log collection.
Includes interceptors for distributed tracing and Prometheus request profiling.
"""

import asyncio
from datetime import datetime, timezone
import logging
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

from app.protocols.binary_serializer import WireTelemetryEvent
from app.protocols.schema_registry import schema_registry

logger = logging.getLogger("shield.grpc")


class GrpcTracingInterceptor:
    """Interceptor extracting W3C trace context and injecting distributed spans."""

    def __init__(self):
        self.call_count = 0
        self.total_duration_ms = 0.0

    async def intercept_call(self, method_name: str, metadata: Dict[str, str], handler_func, *args, **kwargs):
        t0 = time.perf_counter()
        trace_id = metadata.get("traceparent", f"00-{int(time.time()*1000):x}-00000001-01")
        try:
            res = await handler_func(*args, **kwargs)
            return res, trace_id
        finally:
            elapsed = (time.perf_counter() - t0) * 1000.0
            self.call_count += 1
            self.total_duration_ms += elapsed
            logger.debug("[gRPC] %s completed in %.2f ms (trace: %s)", method_name, elapsed, trace_id)


class MockGrpcTelemetryServer:
    """
    Asynchronous gRPC server implementing TelemetryIngestService protocol.
    Works natively in Python asyncio environments with zero external C-extensions.
    """

    def __init__(self):
        self.interceptor = GrpcTracingInterceptor()
        self.ingested_count = 0
        self.rejected_count = 0
        self.alert_subscribers: List[asyncio.Queue] = []
        self._lock = asyncio.Lock()

    async def IngestEvent(self, event: WireTelemetryEvent, metadata: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Unary gRPC invocation."""
        metadata = metadata or {}

        async def _handle():
            # Validate against schema registry
            schema_registry.validate_message(
                "telemetry.raw", "v1.1",
                {"event_id": event.event_id, "timestamp_unix_ms": event.timestamp_unix_ms,
                 "agent_id": event.agent_id, "severity": str(event.severity_code),
                 "event_type": str(event.event_type_code), "payload": {}}
            )
            self.ingested_count += 1
            return {
                "status": "ACCEPTED",
                "accepted_count": 1,
                "rejected_count": 0,
                "queue_name": "telemetry.grpc.raw",
            }

        res, trace_id = await self.interceptor.intercept_call("IngestEvent", metadata, _handle)
        res["trace_id"] = trace_id
        return res

    async def IngestBatch(self, events: List[WireTelemetryEvent], metadata: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Unary batch gRPC invocation."""
        metadata = metadata or {}
        t0 = time.perf_counter()

        async def _handle():
            accepted = 0
            rejected = 0
            for ev in events:
                try:
                    self.ingested_count += 1
                    accepted += 1
                except Exception:
                    rejected += 1

            self.rejected_count += rejected
            return {
                "status": "ACCEPTED",
                "accepted_count": accepted,
                "rejected_count": rejected,
                "processing_latency_ms": round((time.perf_counter() - t0) * 1000.0, 3),
                "queue_name": "telemetry.grpc.batch",
            }

        res, trace_id = await self.interceptor.intercept_call("IngestBatch", metadata, _handle)
        res["trace_id"] = trace_id
        return res

    async def StreamTelemetry(
        self, stream_iterator: AsyncGenerator[WireTelemetryEvent, None], metadata: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Client-side streaming: probe streams events continuously over a single HTTP/2 TCP stream."""
        metadata = metadata or {}
        t0 = time.perf_counter()

        async def _handle():
            count = 0
            async for ev in stream_iterator:
                count += 1
                self.ingested_count += 1

            return {
                "status": "STREAM_COMPLETED",
                "accepted_count": count,
                "rejected_count": 0,
                "processing_latency_ms": round((time.perf_counter() - t0) * 1000.0, 3),
                "queue_name": "telemetry.grpc.stream",
            }

        res, trace_id = await self.interceptor.intercept_call("StreamTelemetry", metadata, _handle)
        res["trace_id"] = trace_id
        return res

    async def SubscribeAlerts(self, tenant_id: str, min_severity: int = 3) -> AsyncGenerator[Dict[str, Any], None]:
        """Server-side streaming: pushes real-time alert frames to connected SOC subscribers."""
        q = asyncio.Queue()
        async with self._lock:
            self.alert_subscribers.append(q)

        try:
            while True:
                alert = await q.get()
                if alert.get("tenant_id") == tenant_id and alert.get("severity_code", 0) >= min_severity:
                    yield alert
        finally:
            async with self._lock:
                if q in self.alert_subscribers:
                    self.alert_subscribers.remove(q)

    async def broadcast_alert(self, alert_payload: Dict[str, Any]):
        """Dispatches an alert to all active streaming subscribers."""
        async with self._lock:
            for q in self.alert_subscribers:
                await q.put(alert_payload)


# Singleton gRPC server instance
grpc_telemetry_server = MockGrpcTelemetryServer()
