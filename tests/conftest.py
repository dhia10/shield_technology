"""
Pytest Test Fixtures and Global Harness for Shield Technology.
Provides isolated test environments, TestClients, and search service fixtures.
"""

import os
import pytest
from sqlalchemy import text
from starlette.testclient import TestClient

from app.api.main import app
from app.schemas.enums import EquipmentCategory
from app.search.engine import SearchService
from app.search.embeddings import SemanticEmbeddingEngine
from app.search.vector_store import NumPyCosineVectorStore
from app.storage.database import engine, init_db
from app.storage.models import Base
from app.workers.broker import message_broker
from app.storage.cache import cache_service


@pytest.fixture(autouse=True)
async def setup_test_environment():
    """Initializes schema, purges test tables, and resets memory brokers before each test."""
    await init_db()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("DELETE FROM telemetry_events"))

    message_broker.queues.clear()
    message_broker.dlq.clear()
    await cache_service.invalidate("stats:")
    yield


@pytest.fixture
def api_client():
    """FastAPI TestClient instance."""
    with TestClient(app) as client:
        yield client


@pytest.fixture
def isolated_search_service():
    """Provides a fresh SearchService backed by an isolated in-memory vector store."""
    engine_inst = SemanticEmbeddingEngine(dimension=384)
    store = NumPyCosineVectorStore()
    service = SearchService(vector_store=store, embedding_engine_instance=engine_inst, bootstrap=False)

    # Seed 3 foundational test records
    items = [
        {
            "id": "test_cam_1",
            "slug": "test-cam-4k",
            "name": "Caméra Panasonic 4K IA Ultra",
            "category": EquipmentCategory.CAMERA_4K_IA,
            "manufacturer": "Panasonic",
            "description": "Vidéosurveillance extérieure 4K avec détection de personnes par intelligence artificielle.",
            "technical_specs": {"resolution": "4K", "fps": 30},
            "certifications": ["NDAA", "CE"],
            "warranty_months": 36,
            "price_tnd": 850.0,
            "in_stock": True,
        },
        {
            "id": "test_alarm_1",
            "slug": "test-alarm-dsc",
            "name": "Kit Alarme DSC PowerG Grade 3",
            "category": EquipmentCategory.ALARM_GRADE_3,
            "manufacturer": "DSC",
            "description": "Centrale anti-intrusion pour locaux sensibles et détection périmétrique.",
            "technical_specs": {"zones": 32, "grade": 3},
            "certifications": ["Grade 3"],
            "warranty_months": 24,
            "price_tnd": 750.0,
            "in_stock": True,
        },
        {
            "id": "test_fire_1",
            "slug": "test-fire-fc",
            "name": "Centrale Incendie FireClass EN54",
            "category": EquipmentCategory.FIRE_EN54,
            "manufacturer": "FireClass",
            "description": "Détection incendie adressable et évacuation sonore conforme EN54.",
            "technical_specs": {"loops": 2, "points": 250},
            "certifications": ["EN54-2"],
            "warranty_months": 36,
            "price_tnd": 1200.0,
            "in_stock": True,
        },
    ]
    service.index_batch(items)
    return service
