"""
Unit & Integration Test Suite for Mohamed Ali Romdhane's Software Engineering Deliverables.
Covers:
- Binary Serializer & Protobuf Wire Protocol
- Schema Registry Compatibility Enforcement
- gRPC Ingestion & Streaming Channels
- MQTT Protocol Adapter
- WebSocket Real-Time Pub/Sub & Tenant Isolation
- Circuit Breaker Fault Isolation
- Ring Buffer Backpressure & Priority Eviction
- Stream Pipeline Time-Windows & Rules Engine
- Event Sourcing Immutable Ledger & State Replay
- OpenTelemetry Distributed Tracing
"""

import asyncio
import json
import time
import pytest

from app.eventsourcing.event_store import EventStore
from app.protocols.binary_serializer import BinarySerializer, WireTelemetryEvent
from app.protocols.grpc_service import MockGrpcTelemetryServer
from app.protocols.mqtt_adapter import MQTTTelemetryAdapter, MQTTTopicParser
from app.protocols.schema_registry import CompatibilityMode, SchemaRegistry, SchemaValidationError
from app.protocols.websocket_manager import WebSocketManager
from app.schemas import EventTypeEnum, RawTelemetryEvent, SeverityEnum
from app.streaming.backpressure import BackpressureState, RingBufferBackpressureController
from app.streaming.circuit_breaker import CircuitBreaker, CircuitBreakerOpenException, CircuitState
from app.streaming.rules_engine import RulesEngine
from app.streaming.stream_pipeline import StreamPipeline
from app.tracing.tracer import DistributedTracer


# ─── 1. BINARY SERIALIZER TESTS ──────────────────────────────────────────────

def test_binary_serialization_roundtrip():
    original = WireTelemetryEvent(
        event_id="evt-test-101",
        timestamp_unix_ms=1770000000000,
        agent_id="probe-sfax-01",
        tenant_id="tenant-alpha",
        severity_code=4,
        event_type_code=4,
        source_ip_packed=bytes([192, 168, 1, 100]),
        destination_ip_packed=bytes([10, 0, 0, 1]),
        payload_bytes=b'{"syn_pps": 75000, "attack": "SYN_FLOOD"}',
        event_hash="abc1234567890abcdef1234567890abcdef",
    )

    packed = BinarySerializer.serialize_event(original)
    assert packed.startswith(BinarySerializer.MAGIC_HEADER)

    unpacked = BinarySerializer.deserialize_event(packed)
    assert unpacked.event_id == original.event_id
    assert unpacked.timestamp_unix_ms == original.timestamp_unix_ms
    assert unpacked.agent_id == original.agent_id
    assert unpacked.tenant_id == original.tenant_id
    assert unpacked.severity_code == original.severity_code
    assert unpacked.event_type_code == original.event_type_code
    assert unpacked.source_ip_packed == original.source_ip_packed
    assert unpacked.destination_ip_packed == original.destination_ip_packed
    assert unpacked.payload_bytes == original.payload_bytes


def test_binary_serializer_benchmark():
    res = BinarySerializer.benchmark_comparison(count=500)
    assert res["binary"]["size_bytes"] < res["json"]["size_bytes"]
    assert res["compression_gain_percent"] > 30.0


# ─── 2. SCHEMA REGISTRY TESTS ────────────────────────────────────────────────

def test_schema_registry_compatibility():
    reg = SchemaRegistry(default_mode=CompatibilityMode.BACKWARD)
    # v1.0
    v1 = {
        "required_fields": ["event_id", "timestamp"],
        "field_types": {"event_id": "string", "timestamp": "int"},
    }
    reg.register_schema("topic.test", "v1.0", v1, validate_compat=False)

    # Compatible v1.1
    v1_1 = {
        "required_fields": ["event_id", "timestamp"],
        "optional_fields": ["tenant_id"],
        "field_types": {"event_id": "string", "timestamp": "int", "tenant_id": "string"},
    }
    fp = reg.register_schema("topic.test", "v1.1", v1_1, validate_compat=True)
    assert len(fp) == 16

    # Incompatible change (adding mandatory field without default under BACKWARD)
    v2_bad = {
        "required_fields": ["event_id", "timestamp", "breaking_field"],
        "field_types": {"event_id": "string", "timestamp": "int", "breaking_field": "string"},
    }
    with pytest.raises(SchemaValidationError):
        reg.register_schema("topic.test", "v2.0", v2_bad, validate_compat=True)


# ─── 3. GRPC SERVICE TESTS ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_grpc_unary_and_streaming():
    server = MockGrpcTelemetryServer()
    ev = WireTelemetryEvent(
        event_id="evt-grpc-1",
        timestamp_unix_ms=int(time.time() * 1000),
        agent_id="probe-g1",
        tenant_id="tenant-g",
        severity_code=3,
        event_type_code=2,
        source_ip_packed=bytes([197, 14, 88, 99]),
        destination_ip_packed=bytes([10, 0, 0, 2]),
        payload_bytes=b'{"user": "admin"}',
        event_hash="hash123",
    )

    # 1. Unary
    res_unary = await server.IngestEvent(ev)
    assert res_unary["status"] == "ACCEPTED"
    assert "trace_id" in res_unary

    # 2. Batch
    res_batch = await server.IngestBatch([ev, ev])
    assert res_batch["accepted_count"] == 2

    # 3. Client Stream
    async def _stream_gen():
        for i in range(5):
            yield ev

    res_stream = await server.StreamTelemetry(_stream_gen())
    assert res_stream["accepted_count"] == 5


# ─── 4. MQTT ADAPTER TESTS ───────────────────────────────────────────────────

def test_mqtt_topic_parsing_and_conversion():
    adapter = MQTTTelemetryAdapter()
    topic = "shield/telemetry/tenant-alpha/probe-sfax-iot-01/network"
    payload = json.dumps({
        "severity": "HIGH",
        "event_type": "PORT_SCAN",
        "source_ip": "41.226.11.8",
        "destination_ip": "10.0.0.1",
        "payload": {"ports": [80, 443, 8080]},
    }).encode("utf-8")

    ok, event, err = adapter.process_message(topic, payload)
    assert ok is True
    assert event is not None
    assert event.agent_id == "probe-sfax-iot-01"
    assert event.tenant_id == "tenant-alpha"
    assert event.severity == SeverityEnum.HIGH
    assert event.event_type == EventTypeEnum.PORT_SCAN


# ─── 5. WEBSOCKET MANAGER TESTS ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_websocket_pubsub_tenant_isolation():
    manager = WebSocketManager()
    client_a = await manager.connect("client-1", tenant_id="tenant-bank-a")
    client_b = await manager.connect("client-2", tenant_id="tenant-gov-b")

    alert_a = {
        "alert_id": "alt-01",
        "tenant_id": "tenant-bank-a",
        "severity": "CRITICAL",
        "description": "SQL Injection attempt",
    }

    await manager.broadcast_alert(alert_a)

    # Client A must receive it
    assert client_a.message_queue.qsize() == 1
    msg = client_a.message_queue.get_nowait()
    assert msg["alert_id"] == "alt-01"

    # Client B (different tenant) must NOT receive it
    assert client_b.message_queue.qsize() == 0

    await manager.disconnect("client-1")
    await manager.disconnect("client-2")
    assert manager.active_connections_count() == 0


# ─── 6. CIRCUIT BREAKER TESTS ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_circuit_breaker_state_transitions():
    cb = CircuitBreaker("test_db", failure_threshold=3, recovery_timeout_sec=0.1)

    async def flaky_call(fail: bool):
        if fail:
            raise RuntimeError("Database connection refused")
        return "SUCCESS"

    # 1. Start in CLOSED
    assert cb.state == CircuitState.CLOSED
    res = await cb.call_async(flaky_call, fail=False)
    assert res == "SUCCESS"

    # 2. Trigger 3 failures -> Should trip to OPEN
    for _ in range(3):
        try:
            await cb.call_async(flaky_call, fail=True)
        except RuntimeError:
            pass

    assert cb.state == CircuitState.OPEN

    # 3. Immediate call must fail-fast with CircuitBreakerOpenException
    with pytest.raises(CircuitBreakerOpenException):
        await cb.call_async(flaky_call, fail=False)

    # 4. Wait for recovery timeout -> enters HALF-OPEN
    await asyncio.sleep(0.12)
    assert cb.allow_request() is True
    assert cb.state == CircuitState.HALF_OPEN

    # 5. Success in trial -> recovers to CLOSED
    await cb.call_async(flaky_call, fail=False)
    await cb.call_async(flaky_call, fail=False)
    assert cb.state == CircuitState.CLOSED


# ─── 7. BACKPRESSURE RING BUFFER TESTS ───────────────────────────────────────

def test_ring_buffer_backpressure_and_priority_shedding():
    controller = RingBufferBackpressureController(capacity=10, low_watermark_ratio=0.4, high_watermark_ratio=0.7)

    # Enqueue low severity events
    for i in range(7):
        ev = RawTelemetryEvent(
            timestamp="2026-06-15T12:00:00Z",
            agent_id=f"agent-{i}",
            severity=SeverityEnum.LOW,
            event_type=EventTypeEnum.AUTH_ATTEMPT,
            source_ip="192.168.1.1",
            payload={},
        )
        ok, reason = controller.enqueue(ev)
        assert ok is True

    # High watermark is 7 (70%). At capacity 7, state is LOAD_SHEDDING
    assert controller.state == BackpressureState.LOAD_SHEDDING

    # Trying to add another LOW severity event must be shed
    low_ev = RawTelemetryEvent(
        timestamp="2026-06-15T12:00:00Z",
        agent_id="agent-low",
        severity=SeverityEnum.LOW,
        event_type=EventTypeEnum.AUTH_ATTEMPT,
        source_ip="192.168.1.1",
        payload={},
    )
    ok, reason = controller.enqueue(low_ev)
    assert ok is False
    assert "SHED" in reason

    # But adding a CRITICAL severity event MUST be accepted
    crit_ev = RawTelemetryEvent(
        timestamp="2026-06-15T12:00:00Z",
        agent_id="agent-crit",
        severity=SeverityEnum.CRITICAL,
        event_type=EventTypeEnum.DDOS_FLOOD,
        source_ip="185.220.101.4",
        payload={},
    )
    ok_crit, reason_crit = controller.enqueue(crit_ev)
    assert ok_crit is True

    # Drain buffer
    drained = controller.dequeue_batch(batch_size=20)
    assert len(drained) == 8
    assert controller.current_size == 0


# ─── 8. STREAM PIPELINE & RULES ENGINE TESTS ─────────────────────────────────

def test_rules_engine_threat_detection():
    engine = RulesEngine()

    ddos_event = RawTelemetryEvent(
        timestamp="2026-07-02T10:00:00Z",
        agent_id="probe-edge-01",
        severity=SeverityEnum.HIGH,
        event_type=EventTypeEnum.DDOS_FLOOD,
        source_ip="185.220.101.5",
        payload={"syn_rate_pps": 95000},
    )
    alert = engine.evaluate_event(ddos_event)
    assert alert is not None
    assert alert.rule_name == "RULE_CRITICAL_DDOS_HIGH_PPS"
    assert alert.severity == SeverityEnum.CRITICAL

    sqli_event = RawTelemetryEvent(
        timestamp="2026-07-02T10:00:00Z",
        agent_id="probe-core-02",
        severity=SeverityEnum.MEDIUM,
        event_type=EventTypeEnum.SQL_INJECTION_ATTEMPT,
        source_ip="197.14.88.99",
        payload={"query": "SELECT * FROM users WHERE id = 1 UNION SELECT password FROM admin --"},
    )
    alert_sqli = engine.evaluate_event(sqli_event)
    assert alert_sqli is not None
    assert alert_sqli.rule_name == "RULE_HIGH_SQL_INJECTION_SIGNATURE"


def test_stream_pipeline_windowing():
    pipeline = StreamPipeline(tumbling_window_sec=2, sliding_window_sec=5)
    ev = RawTelemetryEvent(
        timestamp="2026-07-02T10:00:00Z",
        agent_id="probe-p1",
        severity=SeverityEnum.CRITICAL,
        event_type=EventTypeEnum.DDOS_FLOOD,
        source_ip="10.0.0.5",
        payload={},
    )
    for _ in range(10):
        pipeline.ingest_event(ev)

    sliding = pipeline.compute_sliding_window()
    assert sliding.total_events == 10
    assert sliding.critical_count == 10

    tumbling = pipeline.trigger_tumbling_window_flush()
    assert tumbling.total_events == 10


# ─── 9. EVENT SOURCING TESTS ─────────────────────────────────────────────────

def test_event_store_cryptographic_chain_and_replay():
    store = EventStore()
    incident_id = "inc-2026-sec-9901"

    ev1 = store.append(incident_id, "INCIDENT_DETECTED", {"attack_type": "DDOS_FLOOD", "severity": "HIGH"})
    ev2 = store.append(incident_id, "SEVERITY_ESCALATED", {"new_severity": "CRITICAL", "reason": "Syn rate > 80k pps"})
    ev3 = store.append(incident_id, "IP_QUARANTINED", {"ip": "185.220.101.4"})
    ev4 = store.append(incident_id, "INCIDENT_RESOLVED", {"resolution": "Firewall BGP blackholing applied"})

    # Verify cryptographic integrity
    is_valid, err = store.verify_integrity()
    assert is_valid is True
    assert err is None

    # Replay state
    state = store.replay_aggregate_state(incident_id)
    assert state["status"] == "RESOLVED"
    assert state["severity"] == "CRITICAL"
    assert state["quarantined_ip"] == "185.220.101.4"
    assert state["version"] == 4


# ─── 10. DISTRIBUTED TRACING TESTS ───────────────────────────────────────────

def test_distributed_tracer_hierarchy():
    tracer = DistributedTracer("test-gateway")
    sample_trace = tracer.generate_sample_trace()

    assert sample_trace["total_spans"] == 5
    assert sample_trace["total_latency_ms"] > 0.0
    assert "w3c_traceparent" in sample_trace
    assert len(sample_trace["spans"]) == 5
