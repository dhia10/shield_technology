"""
Shield Technology Vector Search & Hardware Recommendations Router.
Exposes NumPy-vectorized cosine similarity queries (<1.5 ms) and affinity graph cross-sell pairings.
"""

from fastapi import APIRouter, HTTPException, status

from app.schemas.search import (
    RecommendationRequest,
    RecommendationResponse,
    SemanticSearchRequest,
    SemanticSearchResponse,
)
from app.search.engine import search_service

router = APIRouter(prefix="/api/v1/search", tags=["Semantic Search & Hardware Engine"])


@router.post(
    "/semantic",
    response_model=SemanticSearchResponse,
    summary="Vectorized Cosine Similarity Search (<1.5 ms)",
)
async def semantic_search_endpoint(request: SemanticSearchRequest):
    """
    Searches the Shield Technology security equipment catalog via dense vector dot product.
    Returns ranked matches with similarity score and execution timing in milliseconds.
    """
    return search_service.semantic_search(request)


@router.post(
    "/recommendations",
    response_model=RecommendationResponse,
    summary="Complementary Hardware & SLA Recommendations",
)
async def recommendation_endpoint(request: RecommendationRequest):
    """
    Generates cross-category equipment recommendations based on category affinity graph.
    """
    return search_service.get_recommendations(request)
