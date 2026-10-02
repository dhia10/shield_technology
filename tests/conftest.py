"""
Pytest Test Fixtures and Global Harness.
Mocks external I/O, isolates SQLite storage, and provides FastAPI TestClients.
"""

import os
import tempfile
import pytest
from starlette.testclient import TestClient

from api.app import app
from domain.entities import EquipmentEntity
from domain.enums import EquipmentCategory
from infrastructure.config import settings
from infrastructure.embeddings import DeterministicSemanticEmbeddingEngine
from infrastructure.vector_store import CosineVectorStore
from infrastructure.webhook_client import WebhookClientInterface
from services.lead_scoring_service import LeadScoringService
from services.search_service import SearchService
from services.telemetry_service import TelemetryService


class MockWebhookClient(WebhookClientInterface):
    """In-memory recording webhook client for assertions."""

    def __init__(self):
        self.dispatched_events = []

    async def dispatch(self, payload, event_name="lead.qualified"):
        self.dispatched_events.append({"event": event_name, "payload": payload})
        return True


@pytest.fixture
def mock_webhook_client():
    return MockWebhookClient()


@pytest.fixture
def isolated_telemetry_service(tmp_path):
    """Provides a TelemetryService operating on an isolated temporary SQLite db."""
    db_file = str(tmp_path / "test_telemetry.db")
    service = TelemetryService(buffer_capacity=100, batch_flush_size=5, db_path=db_file)
    return service


@pytest.fixture
def isolated_search_service():
    """Provides a SearchService backed by an isolated in-memory vector store."""
    engine = DeterministicSemanticEmbeddingEngine(dimension=384)
    store = CosineVectorStore()
    service = SearchService(vector_store=store, embedding_engine=engine)

    # Seed 3 foundational test records
    items = [
        EquipmentEntity(
            id="test_cam_1",
            slug="test-cam-4k",
            name="Caméra Panasonic 4K IA Ultra",
            category=EquipmentCategory.CAMERA_4K_IA,
            manufacturer="Panasonic",
            description="Vidéosurveillance extérieure 4K avec détection de personnes par intelligence artificielle.",
            technical_specs={"resolution": "4K", "fps": 30},
            certifications=["NDAA", "CE"],
            warranty_months=36,
            price_tnd=850.0,
            in_stock=True,
        ),
        EquipmentEntity(
            id="test_alarm_1",
            slug="test-alarm-dsc",
            name="Kit Alarme DSC PowerG Grade 3",
            category=EquipmentCategory.ALARM_GRADE_3,
            manufacturer="DSC",
            description="Centrale anti-intrusion pour locaux sensibles et détection périmétrique.",
            technical_specs={"zones": 32, "grade": 3},
            certifications=["Grade 3"],
            warranty_months=24,
            price_tnd=750.0,
            in_stock=True,
        ),
        EquipmentEntity(
            id="test_fire_1",
            slug="test-fire-fc",
            name="Centrale Incendie FireClass EN54",
            category=EquipmentCategory.FIRE_EN54,
            manufacturer="FireClass",
            description="Détection incendie adressable et évacuation sonore conforme EN54.",
            technical_specs={"loops": 2, "points": 250},
            certifications=["EN54-2"],
            warranty_months=36,
            price_tnd=1200.0,
            in_stock=True,
        ),
    ]
    service.index_batch(items)
    return service


@pytest.fixture
def isolated_lead_scoring_service(mock_webhook_client):
    """Provides a LeadScoringService connected to a mock webhook."""
    return LeadScoringService(webhook_client=mock_webhook_client)


@pytest.fixture
def api_client():
    """FastAPI TestClient instance."""
    with TestClient(app) as client:
        yield client
