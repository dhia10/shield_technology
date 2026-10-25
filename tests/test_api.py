"""
Integration tests for Shield Technology FastAPI Endpoints.
Verifies HTTP status codes, JSON response schemas, HMAC security, and error boundaries.
"""

from fastapi import status
from app.security.auth import API_KEY, HMAC_SECRET, compute_hmac_signature


def test_system_health_and_root(api_client):
    """Verifies base health check and root endpoints."""
    res_root = api_client.get("/")
    assert res_root.status_code == status.HTTP_200_OK
    assert res_root.json()["status"] == "operational"

    res_health = api_client.get("/api/v1/health")
    assert res_health.status_code == status.HTTP_200_OK
    data = res_health.json()
    assert data["status"] in ("healthy", "degraded")
    assert "queue_depth" in data


def test_api_telemetry_flow_unauthorized(api_client):
    """Verifies that missing or invalid API Key returns HTTP 401."""
    event_payload = {
        "events": [
            {
                "agent_id": "probe-test-01",
                "severity": "HIGH",
                "event_type": "PORT_SCAN",
                "source_ip": "197.14.88.22",
                "destination_ip": "10.0.0.1",
                "payload": {"target_port": 22},
            }
        ]
    }
    res = api_client.post("/api/v1/telemetry/ingest", json=event_payload)
    assert res.status_code == status.HTTP_401_UNAUTHORIZED


def test_api_telemetry_flow_authorized(api_client):
    """Verifies successful ingestion with valid X-API-Key and HMAC signature."""
    import json
    event_payload = {
        "events": [
            {
                "agent_id": "probe-test-01",
                "severity": "HIGH",
                "event_type": "PORT_SCAN",
                "source_ip": "197.14.88.22",
                "destination_ip": "10.0.0.1",
                "payload": {"target_port": 22, "password": "ClearPassword!"},
            }
        ]
    }
    raw_body = json.dumps(event_payload).encode("utf-8")
    sig = compute_hmac_signature(raw_body, HMAC_SECRET)

    headers = {
        "X-API-Key": API_KEY,
        "X-HMAC-Signature": sig,
        "Content-Type": "application/json",
    }
    res = api_client.post("/api/v1/telemetry/ingest", content=raw_body, headers=headers)
    assert res.status_code == status.HTTP_202_ACCEPTED
    data = res.json()
    assert data["status"] == "accepted"
    assert data["accepted_count"] == 1


def test_api_demo_analyze_endpoint(api_client):
    """Tests the /api/v1/demo/analyze-ml interactive inspection endpoint."""
    payload = {
        "agent_id": "probe-demo-01",
        "event_type": "SQL_INJECTION_ATTEMPT",
        "source_ip": "197.14.88.22",
        "destination_ip": "10.0.0.5",
        "severity": "MEDIUM",
        "payload": {
            "query": "SELECT * FROM users WHERE username='admin' AND '1'='1' --",
            "password": "SecretPassword123!",
            "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.t-IDNbu3rqL0xWNWymPNph6JwUKoWjyAfFD0Mgcvda0",
        },
    }
    res = api_client.post("/api/v1/demo/analyze-ml", json=payload)
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert data["status"] == "success"
    assert data["sanitized_payload"]["password"] == "***REDACTED***"
    assert data["sanitized_payload"]["token"] == "***REDACTED***"
    assert "entropy_score" in data
    assert "threat_score" in data
    assert "features" in data
    assert len(data["features"]) == 7


def test_api_demo_burst_benchmark(api_client):
    """Tests the /api/v1/demo/burst-inject benchmark endpoint."""
    res = api_client.post("/api/v1/demo/burst-inject", json={"burst_size": 500})
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert data["status"] == "completed"
    assert data["burst_size"] == 500
    assert "overall_throughput_eps" in data
    assert "p50_latency_ms" in data
