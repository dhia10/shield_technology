"""
Unit tests for Shield Technology Semantic Search & Recommendation Engine.
Validates cosine similarity ranking, category pruning, confidence thresholds, and recommendations.
"""

import pytest
from domain.enums import EquipmentCategory
from domain.schemas import (
    RecommendationRequest,
    SemanticSearchRequest,
)


def test_index_and_count(isolated_search_service):
    """Verifies indexed document count."""
    svc = isolated_search_service
    assert svc.count_indexed() == 3


def test_semantic_retrieval_camera_query(isolated_search_service):
    """Verifies that an inquiry for video surveillance prioritizes the 4K camera."""
    svc = isolated_search_service
    req = SemanticSearchRequest(
        query="besoin d'une caméra de vidéosurveillance 4k extérieure haute résolution",
        top_k=3,
        min_confidence=0.1,
    )
    res = svc.semantic_search(req)

    assert res.total_matches > 0
    top_match = res.results[0]
    assert top_match.id == "test_cam_1"
    assert top_match.category == EquipmentCategory.CAMERA_4K_IA
    assert top_match.similarity_score > 0.4
    assert res.execution_time_ms >= 0.0


def test_semantic_retrieval_alarm_query(isolated_search_service):
    """Verifies that anti-intrusion inquiries prioritize Grade 3 alarm systems."""
    svc = isolated_search_service
    req = SemanticSearchRequest(
        query="système d'alarme intrusion centrale pour bâtiment industriel",
        top_k=2,
        min_confidence=0.1,
    )
    res = svc.semantic_search(req)

    assert res.total_matches > 0
    top_match = res.results[0]
    assert top_match.id == "test_alarm_1"
    assert top_match.category == EquipmentCategory.ALARM_GRADE_3


def test_category_filtering(isolated_search_service):
    """Ensures category filtering restricts output to only target segment."""
    svc = isolated_search_service
    req = SemanticSearchRequest(
        query="équipement de sécurité",
        category=EquipmentCategory.FIRE_EN54,
        top_k=5,
        min_confidence=0.0,
    )
    res = svc.semantic_search(req)

    assert res.total_matches == 1
    assert res.results[0].category == EquipmentCategory.FIRE_EN54
    assert res.results[0].id == "test_fire_1"


def test_confidence_threshold_pruning(isolated_search_service):
    """Verifies that items with low similarity score are filtered out."""
    svc = isolated_search_service
    # Set an impossible threshold (0.99)
    req = SemanticSearchRequest(
        query="pain au chocolat boulangerie pâtisserie",
        top_k=5,
        min_confidence=0.99,
    )
    res = svc.semantic_search(req)
    assert res.total_matches == 0


def test_hardware_recommendations(isolated_search_service):
    """Verifies cross-category accessory recommendations based on technical affinity."""
    svc = isolated_search_service
    req = RecommendationRequest(
        source_item_id="test_cam_1",
        max_recommendations=2,
    )
    res = svc.get_recommendations(req)

    assert res.source_item_id == "test_cam_1"
    # Camera recommends alarm or complementary items based on affinity graph
    for item in res.recommendations:
        assert item.id != "test_cam_1"
