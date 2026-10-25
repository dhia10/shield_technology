"""
Test suite for the Interactive Security & ML Workbench endpoints.
"""

import json
from fastapi import status
from app.security.auth import API_KEY, HMAC_SECRET, compute_hmac_signature


def test_workbench_demo_html_served(api_client):
    """Verifies that /demo serves the HTML console cleanly."""
    res = api_client.get("/demo")
    assert res.status_code == status.HTTP_200_OK
    assert "<!DOCTYPE html>" in res.text
    assert "Section 1" in res.text
    assert "Section 2" in res.text
    assert "Section 3" in res.text
    assert "Section 4" in res.text
    # Ensure no broken math operations
    assert "Math.round(threat 100)" not in res.text
    assert "Math.round(item.similarity_score 100)" not in res.text
    assert "Math.round(rec.similarity_score 100)" not in res.text


def test_workbench_section1_inspect(api_client):
    """Tests Section 1 real-time redaction diff and hashing."""
    payload = {
        "agent_id": "probe-sousse-dc1",
        "source_ip": "197.14.88.22",
        "payload": {
            "service": "billing",
            "password": "clear_password_xyz",
            "access_token": "token_12345",
            "normal_field": "ok",
        },
    }
    res = api_client.post("/api/v1/demo/inspect-sanitization", json=payload)
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert data["status"] == "success"
    assert data["sanitized_payload"]["password"] == "***REDACTED***"
    assert data["sanitized_payload"]["access_token"] == "***REDACTED***"
    assert data["sanitized_payload"]["normal_field"] == "ok"
    assert data["redacted_count"] == 2
    assert data["network_class"] == "EXTERNAL_WAN"
    assert len(data["event_hash"]) == 64


def test_workbench_section1_ingest(api_client):
    """Tests Section 1 submitting to live /api/v1/telemetry/ingest with HMAC."""
    batch = {
        "events": [
            {
                "agent_id": "probe-sousse-dc1",
                "source_ip": "197.14.88.22",
                "destination_ip": "10.0.0.1",
                "severity": "MEDIUM",
                "event_type": "ANOMALOUS_PAYLOAD",
                "payload": {"status": "probe_check"},
            }
        ]
    }
    body_bytes = json.dumps(batch).encode("utf-8")
    sig = compute_hmac_signature(body_bytes, HMAC_SECRET)
    headers = {
        "X-API-Key": API_KEY,
        "X-HMAC-Signature": sig,
        "Content-Type": "application/json",
    }
    res = api_client.post("/api/v1/telemetry/ingest", content=body_bytes, headers=headers)
    assert res.status_code == status.HTTP_202_ACCEPTED
    data = res.json()
    assert data["status"] == "accepted"
    assert data["accepted_count"] == 1
    assert data["queue_name"] == "telemetry.raw"


def test_workbench_section2_bare_string(api_client):
    """Tests Section 2 arbitrary string entropy and threat scoring."""
    # Test arbitrary SQL injection string
    res_sql = api_client.post(
        "/api/v1/demo/analyze-ml",
        json={"raw_text": "SELECT * FROM users WHERE username='admin' AND '1'='1' UNION SELECT token, password FROM accounts --"},
    )
    assert res_sql.status_code == status.HTTP_200_OK
    data_sql = res_sql.json()
    assert data_sql["entropy_score"] > 3.0
    assert data_sql["char_count"] > 20
    assert len(data_sql["char_frequencies"]) > 0
    assert "diagnostic" in data_sql

    # Test benign French sentence
    res_benign = api_client.post(
        "/api/v1/demo/analyze-ml",
        json={"raw_text": "Bonjour tout le monde, ceci est un message ordinaire du personnel."},
    )
    assert res_benign.status_code == status.HTTP_200_OK
    data_benign = res_benign.json()
    assert data_benign["threat_score"] < 0.80
    assert not data_benign["is_escalated"]


def test_workbench_section3_search_and_recommendations(api_client):
    """Tests Section 3 semantic search and dynamic affinity recommendations."""
    res_search = api_client.post(
        "/api/v1/search/semantic",
        json={"query": "caméra vision nocturne extérieure", "top_k": 3, "min_confidence": 0.05},
    )
    assert res_search.status_code == status.HTTP_200_OK
    data_search = res_search.json()
    assert len(data_search["results"]) > 0
    assert data_search["execution_time_ms"] > 0

    top_item_id = data_search["results"][0]["id"]
    res_rec = api_client.post(
        "/api/v1/search/recommendations",
        json={"source_item_id": top_item_id, "max_recommendations": 3},
    )
    assert res_rec.status_code == status.HTTP_200_OK
    data_rec = res_rec.json()
    assert "recommendations" in data_rec


def test_workbench_section4_burst_inject(api_client):
    """Tests Section 4 live burst generator with real RingBuffer metrics."""
    res_burst = api_client.post(
        "/api/v1/demo/burst-inject",
        json={"burst_size": 1000, "concurrency": 4, "inject_attacks": True},
    )
    assert res_burst.status_code == status.HTTP_200_OK
    data = res_burst.json()
    assert data["status"] == "completed"
    assert data["burst_size"] == 1000
    assert data["overall_throughput_eps"] > 0
    assert data["final_queue_depth"] == 0
    assert len(data["time_series"]) == 10
