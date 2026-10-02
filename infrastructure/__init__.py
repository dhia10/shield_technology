"""Shield Technology Infrastructure Package."""
from infrastructure.config import settings
from infrastructure.embeddings import (
    DeterministicSemanticEmbeddingEngine,
    EmbeddingEngineInterface,
    SentenceTransformerEmbeddingEngine,
    get_embedding_engine,
)
from infrastructure.vector_store import (
    CosineVectorStore,
    VectorSearchResult,
    VectorStoreInterface,
)
from infrastructure.webhook_client import (
    HttpWebhookClient,
    WebhookClientInterface,
)

__all__ = [
    "settings",
    "EmbeddingEngineInterface",
    "DeterministicSemanticEmbeddingEngine",
    "SentenceTransformerEmbeddingEngine",
    "get_embedding_engine",
    "VectorStoreInterface",
    "CosineVectorStore",
    "VectorSearchResult",
    "WebhookClientInterface",
    "HttpWebhookClient",
]
