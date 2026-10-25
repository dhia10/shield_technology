"""Shield Technology Vector Search & Hardware Recommendations Module."""

from app.search.catalog import CATALOG_ITEMS
from app.search.embeddings import SemanticEmbeddingEngine, embedding_engine
from app.search.engine import SearchService, search_service
from app.search.vector_store import NumPyCosineVectorStore, VectorSearchResult

__all__ = [
    "CATALOG_ITEMS",
    "SemanticEmbeddingEngine",
    "embedding_engine",
    "NumPyCosineVectorStore",
    "VectorSearchResult",
    "SearchService",
    "search_service",
]
