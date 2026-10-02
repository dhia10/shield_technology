"""
Shield Technology Semantic Search & Recommendation Service.
Translates unstructured natural language inquiries into dense embeddings,
executes cosine similarity vector search, and delivers contextual upsell/hardware recommendations.
"""

import time
from typing import Dict, List, Optional

from domain.entities import EquipmentEntity
from domain.enums import EquipmentCategory
from domain.schemas import (
    RecommendationRequest,
    RecommendationResponse,
    SearchResultItem,
    SemanticSearchRequest,
    SemanticSearchResponse,
)
from infrastructure.embeddings import EmbeddingEngineInterface, get_embedding_engine
from infrastructure.vector_store import (
    CosineVectorStore,
    VectorSearchResult,
    VectorStoreInterface,
)


class SearchService:
    """
    Core vector retrieval service coordinating dense embeddings
    and cosine similarity vector indexing.
    """

    # Recommendation affinity mapping: maps source category to complementary equipment categories
    CATEGORY_AFFINITY_GRAPH: Dict[EquipmentCategory, List[EquipmentCategory]] = {
        EquipmentCategory.CAMERA_4K_IA: [
            EquipmentCategory.IT_NETWORKING,
            EquipmentCategory.SLA_SERVICE,
            EquipmentCategory.ALARM_GRADE_3,
        ],
        EquipmentCategory.ALARM_GRADE_3: [
            EquipmentCategory.CAMERA_4K_IA,
            EquipmentCategory.ACCESS_BIOMETRIC,
            EquipmentCategory.SLA_SERVICE,
        ],
        EquipmentCategory.FIRE_EN54: [
            EquipmentCategory.SLA_SERVICE,
            EquipmentCategory.ACCESS_BIOMETRIC,
            EquipmentCategory.ALARM_GRADE_3,
        ],
        EquipmentCategory.ACCESS_BIOMETRIC: [
            EquipmentCategory.CAMERA_4K_IA,
            EquipmentCategory.ALARM_GRADE_3,
            EquipmentCategory.IT_NETWORKING,
        ],
        EquipmentCategory.IT_NETWORKING: [
            EquipmentCategory.SLA_SERVICE,
            EquipmentCategory.CAMERA_4K_IA,
        ],
        EquipmentCategory.SLA_SERVICE: [
            EquipmentCategory.CAMERA_4K_IA,
            EquipmentCategory.ALARM_GRADE_3,
            EquipmentCategory.FIRE_EN54,
        ],
    }

    def __init__(
        self,
        vector_store: Optional[VectorStoreInterface] = None,
        embedding_engine: Optional[EmbeddingEngineInterface] = None,
    ):
        self.vector_store = vector_store or CosineVectorStore()
        self.embedding_engine = embedding_engine or get_embedding_engine()

    def index_equipment(self, item: EquipmentEntity) -> None:
        """Vectorizes and indexes an equipment record."""
        text = item.to_searchable_text()
        vector = self.embedding_engine.embed_text(text)
        metadata = {
            "slug": item.slug,
            "name": item.name,
            "category": item.category.value,
            "manufacturer": item.manufacturer,
            "description": item.description,
            "technical_specs": item.technical_specs,
            "certifications": item.certifications,
            "warranty_months": item.warranty_months,
            "price_tnd": item.price_tnd,
            "in_stock": item.in_stock,
        }
        self.vector_store.upsert(item.id, vector, text, metadata)

    def index_batch(self, items: List[EquipmentEntity]) -> int:
        """Batch indexes catalog entities."""
        for item in items:
            self.index_equipment(item)
        return len(items)

    def semantic_search(self, request: SemanticSearchRequest) -> SemanticSearchResponse:
        """Executes natural language semantic query across vector index."""
        start_time = time.perf_counter()
        query_vector = self.embedding_engine.embed_text(request.query)

        cat_filter = request.category.value if request.category else None
        matches = self.vector_store.search(
            query_vector=query_vector,
            top_k=request.top_k,
            min_score=request.min_confidence,
            category_filter=cat_filter,
        )

        results: List[SearchResultItem] = []
        for match in matches:
            meta = match.metadata
            score = match.similarity_score

            # Categorize confidence tier
            if score >= 0.65:
                confidence = "High"
            elif score >= 0.40:
                confidence = "Medium"
            else:
                confidence = "Low"

            results.append(
                SearchResultItem(
                    id=match.id,
                    slug=meta.get("slug", ""),
                    name=meta.get("name", ""),
                    category=EquipmentCategory(meta.get("category", EquipmentCategory.CAMERA_4K_IA.value)),
                    manufacturer=meta.get("manufacturer", ""),
                    description=meta.get("description", ""),
                    technical_specs=meta.get("technical_specs", {}),
                    certifications=meta.get("certifications", []),
                    warranty_months=meta.get("warranty_months", 12),
                    price_tnd=float(meta.get("price_tnd", 0.0)),
                    in_stock=bool(meta.get("in_stock", True)),
                    similarity_score=score,
                    match_confidence_tier=confidence,
                )
            )

        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return SemanticSearchResponse(
            query=request.query,
            total_matches=len(results),
            execution_time_ms=elapsed_ms,
            results=results,
        )

    def get_recommendations(self, request: RecommendationRequest) -> RecommendationResponse:
        """Generates cross-category complementary recommendations."""
        source = self.vector_store.get_by_id(request.source_item_id)
        if not source:
            return RecommendationResponse(source_item_id=request.source_item_id, recommendations=[])

        source_meta = source.metadata
        source_cat = EquipmentCategory(source_meta.get("category", EquipmentCategory.CAMERA_4K_IA.value))
        affinity_cats = self.CATEGORY_AFFINITY_GRAPH.get(source_cat, [])

        recommendations: List[SearchResultItem] = []
        for aff_cat in affinity_cats:
            if len(recommendations) >= request.max_recommendations:
                break

            # Search highest relevance item in target complementary category
            matches = self.vector_store.search(
                query_vector=self.embedding_engine.embed_text(source.document),
                top_k=2,
                min_score=0.1,
                category_filter=aff_cat.value,
            )

            for m in matches:
                if m.id != request.source_item_id and len(recommendations) < request.max_recommendations:
                    meta = m.metadata
                    recommendations.append(
                        SearchResultItem(
                            id=m.id,
                            slug=meta.get("slug", ""),
                            name=meta.get("name", ""),
                            category=EquipmentCategory(meta.get("category")),
                            manufacturer=meta.get("manufacturer", ""),
                            description=meta.get("description", ""),
                            technical_specs=meta.get("technical_specs", {}),
                            certifications=meta.get("certifications", []),
                            warranty_months=meta.get("warranty_months", 12),
                            price_tnd=float(meta.get("price_tnd", 0.0)),
                            in_stock=bool(meta.get("in_stock", True)),
                            similarity_score=m.similarity_score,
                            match_confidence_tier="High" if m.similarity_score >= 0.5 else "Medium",
                        )
                    )

        return RecommendationResponse(
            source_item_id=request.source_item_id,
            recommendations=recommendations,
        )

    def count_indexed(self) -> int:
        return self.vector_store.count()


# Global singleton instance
search_service = SearchService()
