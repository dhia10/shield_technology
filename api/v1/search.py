"""
Shield Technology Semantic Search & AI Recommendation API Controller.
Dense vector retrieval and cross-sell hardware synergy endpoints.
"""

from fastapi import APIRouter, HTTPException, status
from domain.schemas import (
    RecommendationRequest,
    RecommendationResponse,
    SemanticSearchRequest,
    SemanticSearchResponse,
)
from services.search_service import search_service

router = APIRouter(prefix="/search", tags=["Semantic Search & AI Engine"])


@router.post(
    "/semantic",
    response_model=SemanticSearchResponse,
    status_code=status.HTTP_200_OK,
    summary="Natural Language Semantic Vector Search",
    description="Vectorizes natural language query and performs cosine similarity search.",
)
async def semantic_search(request: SemanticSearchRequest) -> SemanticSearchResponse:
    return search_service.semantic_search(request)


@router.post(
    "/recommendations",
    response_model=RecommendationResponse,
    status_code=status.HTTP_200_OK,
    summary="Contextual Equipment & SLA Recommendations",
    description="Returns complementary hardware accessories and SLA plans for an equipment item.",
)
async def get_recommendations(request: RecommendationRequest) -> RecommendationResponse:
    response = search_service.get_recommendations(request)
    return response


@router.get(
    "/stats",
    summary="Vector Index Status",
)
async def get_search_stats():
    return {
        "indexed_documents_count": search_service.count_indexed(),
        "vector_dimension": search_service.embedding_engine.dimension,
        "engine_type": type(search_service.embedding_engine).__name__,
        "vector_store_type": type(search_service.vector_store).__name__,
    }
