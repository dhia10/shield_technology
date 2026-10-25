"""
Shield Technology Vector Store Infrastructure.
Pure NumPy thread-safe Cosine Similarity Vector Store with category filtering and threshold pruning.
Executes vector dot products in <0.5 ms for enterprise hardware catalogs.
"""

from dataclasses import dataclass
import threading
from typing import Any, Dict, List, Optional
import numpy as np


@dataclass
class VectorSearchResult:
    """Record retrieved from vector search."""
    id: str
    document: str
    metadata: Dict[str, Any]
    similarity_score: float


class NumPyCosineVectorStore:
    """
    High-performance in-memory vector store backed by normalized NumPy arrays.
    Calculates cosine similarity in O(N * D) vectorized time with sub-millisecond latency.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._ids: List[str] = []
        self._vectors: Optional[np.ndarray] = None  # Shape (N, D)
        self._documents: Dict[str, str] = {}
        self._metadata: Dict[str, Dict[str, Any]] = {}

    def upsert(
        self,
        item_id: str,
        vector: np.ndarray,
        document: str,
        metadata: Dict[str, Any],
    ) -> None:
        """Inserts or updates a document vector."""
        with self._lock:
            # Ensure float32 1D array
            v = np.asarray(vector, dtype=np.float32).flatten()
            norm = np.linalg.norm(v)
            if norm > 1e-6:
                v = v / norm

            self._documents[item_id] = document
            self._metadata[item_id] = metadata

            if item_id in self._ids:
                idx = self._ids.index(item_id)
                self._vectors[idx] = v
            else:
                self._ids.append(item_id)
                if self._vectors is None:
                    self._vectors = np.expand_dims(v, axis=0)
                else:
                    self._vectors = np.vstack([self._vectors, v])

    def search(
        self,
        query_vector: np.ndarray,
        top_k: int = 5,
        min_score: float = 0.0,
        category_filter: Optional[str] = None,
    ) -> List[VectorSearchResult]:
        """
        Executes vectorized cosine similarity search across indexed catalog.
        Cosine similarity = (M · q) / (||M|| * ||q||). Because vectors are unit-normalized,
        this simplifies to a single matrix-vector product M · q.
        """
        with self._lock:
            if self._vectors is None or len(self._ids) == 0:
                return []

            q = np.asarray(query_vector, dtype=np.float32).flatten()
            q_norm = np.linalg.norm(q)
            if q_norm > 1e-6:
                q = q / q_norm

            # Vectorized dot product M · q
            scores = np.dot(self._vectors, q)

            # Apply category filter mask if specified
            candidates = []
            for i, item_id in enumerate(self._ids):
                meta = self._metadata.get(item_id, {})
                if category_filter:
                    item_cat = meta.get("category")
                    # Handle both enum value and string comparison
                    if item_cat != category_filter and str(item_cat) != category_filter:
                        continue

                score = float(scores[i])
                if score >= min_score:
                    candidates.append((i, item_id, score))

            # Sort descending by similarity score
            candidates.sort(key=lambda x: x[2], reverse=True)
            top_candidates = candidates[:top_k]

            results: List[VectorSearchResult] = []
            for _, item_id, score in top_candidates:
                results.append(
                    VectorSearchResult(
                        id=item_id,
                        document=self._documents.get(item_id, ""),
                        metadata=self._metadata.get(item_id, {}),
                        similarity_score=round(max(0.0, min(1.0, score)), 4),
                    )
                )

            return results

    def get_by_id(self, item_id: str) -> Optional[VectorSearchResult]:
        with self._lock:
            if item_id not in self._ids:
                return None
            idx = self._ids.index(item_id)
            return VectorSearchResult(
                id=item_id,
                document=self._documents.get(item_id, ""),
                metadata=self._metadata.get(item_id, {}),
                similarity_score=1.0,
            )

    def count(self) -> int:
        with self._lock:
            return len(self._ids)

    def clear(self) -> None:
        with self._lock:
            self._ids.clear()
            self._vectors = None
            self._documents.clear()
            self._metadata.clear()
