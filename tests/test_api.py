"""
Integration tests for Shield Technology FastAPI Endpoints.
Verifies HTTP status codes, JSON response schemas, and error boundaries.
"""

from fastapi import status


def test_system_health_and_root(api_client):
    """Verifies base health check and root endpoints."""
    res_root = api_client.get("/")
    assert res_root.status_code == status.HTTP_200_OK
    assert res_root.json()["status"] == "operational"

    res_health = api_client.get("/health")
    assert res_health.status_code == status.HTTP_200_OK
    assert res_health.json()["status"] == "healthy"


def test_api_telemetry_flow(api_client):
    """Verifies telemetry event submission and metric query."""
    event_payload = {
        "event_type": "CTA_CLICK",
        "session_id": "integration_session_99",
        "page_path": "/produits",
        "element_id": "cta_devis",
        "metadata": {"source": "header_nav"},
    }
    res_ingest = api_client.post("/api/v1/telemetry/events", json=event_payload)
    assert res_ingest.status_code == status.HTTP_202_ACCEPTED
    assert res_ingest.json()["status"] == "accepted"
    assert res_ingest.json()["count"] == 1

    res_metrics = api_client.get("/api/v1/telemetry/metrics")
    assert res_metrics.status_code == status.HTTP_200_OK
    metrics = res_metrics.json()
    assert metrics["total_events_received"] >= 1


def test_api_semantic_search_flow(api_client):
    """Verifies vector search endpoint with natural language query."""
    search_payload = {
        "query": "caméra 4k extérieure intelligence artificielle",
        "top_k": 3,
        "min_confidence": 0.1,
    }
    res = api_client.post("/api/v1/search/semantic", json=search_payload)
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert "results" in data
    assert data["total_matches"] >= 0
    assert "execution_time_ms" in data


def test_api_lead_qualification_flow(api_client):
    """Verifies RFQ submission and scoring via API."""
    lead_payload = {
        "contact_name": "Ing. Yassine Triki",
        "company_name": "Société Industrielle du Sud",
        "email": "yassine.triki@industrie-sud.tn",
        "phone": "+216 74 999 888",
        "client_type": "INDUSTRY",
        "domain_interest": "FIRE_DETECTION",
        "project_description": "Mise aux normes incendie EN54 urgente pour notre usine de 3000m2 suite à inspection.",
        "urgency": "IMMEDIATE_MISSION_CRITICAL",
        "surface_m2": 3000.0,
        "estimated_budget_tnd": 28000.0,
    }
    res = api_client.post("/api/v1/leads/qualify", json=lead_payload)
    assert res.status_code == status.HTTP_201_CREATED
    data = res.json()
    assert "lead_id" in data
    assert data["opportunity_score"] > 60.0
    assert "breakdown" in data
    assert data["qualification_tier"] in ("TIER_1_ENTERPRISE_VIP", "TIER_2_QUALIFIED")


def test_api_validation_error_boundaries(api_client):
    """Ensures malformed payload returns HTTP 422 Unprocessable Entity."""
    bad_payload = {
        "contact_name": "",  # Too short
        "email": "invalid-email",
        "phone": "123",
        "client_type": "UNKNOWN_TYPE",
    }
    res = api_client.post("/api/v1/leads/qualify", json=bad_payload)
    assert res.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
