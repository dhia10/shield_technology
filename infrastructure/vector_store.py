"""
Shield Technology Vector Store Infrastructure.
Abstract vector storage interface and high-performance thread-safe Cosine Vector Store implementation.
Supports metadata filtering, threshold pruning, and SQLite/JSON persistence.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
import json
import os
import threading
from typing import Any, Dict, List, Optional
import numpy as np


@dataclass
class VectorSearchResult:
    """Standardized retrieval record from vector search."""
    id: str
    document: str
    metadata: Dict[str, Any]
    similarity_score: float


class VectorStoreInterface(ABC):
    """Abstract interface defining the contract for any vector database adapter."""

    @abstractmethod
    def upsert(
        self,
        item_id: str,
        vector: List[float],
        document: str,
        metadata: Dict[str, Any],
    ) -> None:
        """Insert or replace an indexed document vector."""
        pass

    @abstractmethod
    def search(
        self,
        query_vector: List[float],
        top_k: int = 5,
        min_score: float = 0.0,
        category_filter: Optional[str] = None,
    ) -> List[VectorSearchResult]:
        """Perform similarity search and return scored matches."""
        pass

    @abstractmethod
    def count(self) -> int:
        """Return total indexed items."""
        pass

    @abstractmethod
    def get_by_id(self, item_id: str) -> Optional[VectorSearchResult]:
        """Retrieve indexed item by unique ID."""
        pass

    @abstractmethod
    def clear(self) -> None:
        """Purge all index entries."""
        pass


class CosineVectorStore(VectorStoreInterface):
    """
    High-performance, in-memory, thread-safe Cosine Similarity Vector Store.
    Implements fast vectorized dot products via NumPy with optional disk persistence.
    Zero external database server needed for local dev, testing, or edge deployment.
    """

    def __init__(self, persistence_path: Optional[str] = None):
        self._lock = threading.RLock()
        self._persistence_path = persistence_path
        self._ids: List[str] = []
        self._vectors: Optional[np.ndarray] = None
        self._documents: Dict[str, str] = {}
        self._metadata: Dict[str, Dict[str, Any]] = {}

        if self._persistence_path and os.path.exists(self._persistence_path):
            self.load_from_disk()

    def count(self) -> int:
        with self._lock:
            return len(self._ids)

    def upsert(
        self,
        item_id: str,
        vector: List[float],
        document: str,
        metadata: Dict[str, Any],
    ) -> None:
        with self._lock:
            # Ensure unit normalization for cosine similarity
            vec_np = np.array(vector, dtype=np.float32)
            norm = np.linalg.norm(vec_np)
            if norm > 0:
                vec_np = vec_np / norm

            if item_id in self._ids:
                idx = self._ids.index(item_id)
                assert self._vectors is not None
                self._vectors[idx] = vec_np
            else:
                self._ids.append(item_id)
                if self._vectors is None:
                    self._vectors = np.expand_dims(vec_np, axis=0)
                else:
                    self._vectors = np.vstack([self._vectors, vec_np])

            self._documents[item_id] = document
            self._metadata[item_id] = metadata

            if self._persistence_path:
                self.save_to_disk()

    def search(
        self,
        query_vector: List[float],
        top_k: int = 5,
        min_score: float = 0.0,
        category_filter: Optional[str] = None,
    ) -> List[VectorSearchResult]:
        with self._lock:
            if not self._ids or self._vectors is None:
                return []

            q_vec = np.array(query_vector, dtype=np.float32)
            q_norm = np.linalg.norm(q_vec)
            if q_norm > 0:
                q_vec = q_vec / q_norm

            # Matrix-vector multiplication for all cosine similarities at once
            scores = np.dot(self._vectors, q_vec)

            # Filter indices based on category and min_score threshold
            candidates = []
            for idx, score in enumerate(scores):
                score_val = float(score)
                if score_val < min_score:
                    continue

                item_id = self._ids[idx]
                meta = self._metadata.get(item_id, {})

                if category_filter:
                    item_cat = meta.get("category", "")
                    if item_cat.lower() != category_filter.lower():
                        continue

                candidates.append((score_val, item_id, idx))

            # Sort descending by similarity score
            candidates.sort(key=lambda x: x[0], reverse=True)
            top_matches = candidates[:top_k]

            results = []
            for score_val, item_id, idx in top_matches:
                results.append(
                    VectorSearchResult(
                        id=item_id,
                        document=self._documents.get(item_id, ""),
                        metadata=self._metadata.get(item_id, {}),
                        similarity_score=round(score_val, 4),
                    )
                )
            return results

    def get_by_id(self, item_id: str) -> Optional[VectorSearchResult]:
        with self._lock:
            if item_id not in self._documents:
                return None
            return VectorSearchResult(
                id=item_id,
                document=self._documents[item_id],
                metadata=self._metadata.get(item_id, {}),
                similarity_score=1.0,
            )

    def clear(self) -> None:
        with self._lock:
            self._ids = []
            self._vectors = None
            self._documents = {}
            self._metadata = {}
            if self._persistence_path and os.path.exists(self._persistence_path):
                try:
                    os.remove(self._persistence_path)
                except OSError:
                    pass

    def save_to_disk(self) -> None:
        if not self._persistence_path:
            return
        os.makedirs(os.path.dirname(self._persistence_path) or ".", exist_ok=True)
        data = {
            "ids": self._ids,
            "vectors": self._vectors.tolist() if self._vectors is not None else [],
            "documents": self._documents,
            "metadata": self._metadata,
        }
        with open(self._persistence_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_from_disk(self) -> bool:
        if not self._persistence_path or not os.path.exists(self._persistence_path):
            return False
        try:
            with open(self._persistence_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._ids = data.get("ids", [])
            vecs = data.get("vectors", [])
            self._vectors = np.array(vecs, dtype=np.float32) if vecs else None
            self._documents = data.get("documents", {})
            self._metadata = data.get("metadata", {})
            return True
        except Exception:
            return False
