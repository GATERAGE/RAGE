# SPDX-License-Identifier: Apache-2.0
# (c) 2024-2026 GATERAGE — RAGE: Retrieval Augmented Generative Engine
"""
RAGE Indexing Engine

Builds searchable vector indexes via sentence-transformers + FAISS.
Falls back gracefully (tag-based retrieval) when optional deps are
missing.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import numpy as np

from .storage import StorageEngine, DocumentMetadata

logger = logging.getLogger("rage.indexing")

try:
    from sentence_transformers import SentenceTransformer
    import faiss  # type: ignore
    EMBEDDINGS_AVAILABLE = True
except ImportError:
    EMBEDDINGS_AVAILABLE = False
    logger.warning(
        "sentence-transformers or faiss not installed. "
        "Install with: pip install rage[embeddings]"
    )


def _default_index_path() -> Path:
    return Path.cwd() / "data" / "rage" / "indexes"


class IndexingEngine:
    """Vector embeddings + FAISS-backed similarity search."""

    def __init__(
        self,
        storage_engine: StorageEngine,
        embedding_model: str = "all-MiniLM-L6-v2",
        index_path: Optional[Path] = None,
    ):
        self.storage = storage_engine
        self.embedding_model_name = embedding_model
        self.index_path = Path(index_path) if index_path else _default_index_path()
        self.index_path.mkdir(parents=True, exist_ok=True)

        self.embedder: Optional["SentenceTransformer"] = None
        self.index: Optional[Any] = None  # faiss.Index
        self.doc_id_to_index: Dict[str, int] = {}
        self.index_to_doc_id: Dict[int, str] = {}

        if EMBEDDINGS_AVAILABLE:
            self._initialize_embedder()
            self._load_index()
        else:
            logger.warning("Embeddings not available; tag-based retrieval only.")

    def _initialize_embedder(self) -> None:
        if not EMBEDDINGS_AVAILABLE:
            return
        try:
            self.embedder = SentenceTransformer(self.embedding_model_name)
            logger.info(f"Initialized embedding model: {self.embedding_model_name}")
        except Exception as e:
            logger.error(f"Error initializing embedder: {e}")

    def _load_index(self) -> None:
        index_file = self.index_path / "faiss.index"
        mapping_file = self.index_path / "mapping.json"

        if index_file.exists() and mapping_file.exists():
            try:
                self.index = faiss.read_index(str(index_file))
                with open(mapping_file, "r", encoding="utf-8") as f:
                    mapping = json.load(f)
                self.doc_id_to_index = mapping.get("doc_to_idx", {})
                self.index_to_doc_id = {int(v): k for k, v in self.doc_id_to_index.items()}
                logger.info(f"Loaded index with {self.index.ntotal} vectors")
                return
            except Exception as e:
                logger.error(f"Error loading index: {e}")

        # Create new index (384 dimensions for all-MiniLM-L6-v2).
        dimension = 384
        self.index = faiss.IndexFlatL2(dimension)
        logger.info(f"Created new index with dimension {dimension}")

    def _save_index(self) -> None:
        if not self.index:
            return
        try:
            index_file = self.index_path / "faiss.index"
            mapping_file = self.index_path / "mapping.json"
            faiss.write_index(self.index, str(index_file))
            with open(mapping_file, "w", encoding="utf-8") as f:
                json.dump(
                    {"doc_to_idx": self.doc_id_to_index, "model": self.embedding_model_name},
                    f,
                    indent=2,
                )
            logger.info("Saved index to disk")
        except Exception as e:
            logger.error(f"Error saving index: {e}")

    async def index_document(
        self,
        doc_id: str,
        content: str,
        chunks: Optional[List[str]] = None,
    ) -> bool:
        """Index a document by creating embeddings."""
        if not self.embedder or not self.index:
            logger.warning("Indexing not available (deps missing)")
            return False
        try:
            if chunks is None:
                chunks = self._chunk_text(content)
            embeddings = self.embedder.encode(chunks, show_progress_bar=False)
            start_idx = self.index.ntotal
            self.index.add(embeddings.astype("float32"))

            for i, _chunk in enumerate(chunks):
                idx = start_idx + i
                chunk_id = f"{doc_id}_chunk_{i}"
                self.doc_id_to_index[chunk_id] = idx
                self.index_to_doc_id[idx] = chunk_id

            self._save_index()
            logger.info(f"Indexed document {doc_id} with {len(chunks)} chunks")
            return True
        except Exception as e:
            logger.error(f"Error indexing document {doc_id}: {e}")
            return False

    @staticmethod
    def _chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
        """Split text into overlapping word-window chunks."""
        words = text.split()
        chunks: List[str] = []
        step = max(1, chunk_size - overlap)
        for i in range(0, len(words), step):
            chunk = " ".join(words[i:i + chunk_size])
            chunks.append(chunk)
        return chunks

    async def search(
        self,
        query: str,
        top_k: int = 5,
    ) -> List[Tuple[str, float, DocumentMetadata]]:
        """Return (doc_id, similarity, metadata) tuples."""
        if not self.embedder or not self.index:
            return []
        try:
            query_embedding = self.embedder.encode([query], show_progress_bar=False)
            k = min(top_k, self.index.ntotal)
            if k == 0:
                return []
            distances, indices = self.index.search(query_embedding.astype("float32"), k)
            results: List[Tuple[str, float, DocumentMetadata]] = []
            for dist, idx in zip(distances[0], indices[0]):
                if idx == -1:
                    continue
                chunk_id = self.index_to_doc_id.get(int(idx))
                if not chunk_id:
                    continue
                doc_id = chunk_id.split("_chunk_")[0]
                metadata = self.storage.get_metadata(doc_id)
                if metadata:
                    similarity = 1.0 / (1.0 + float(dist))
                    results.append((doc_id, similarity, metadata))
            results.sort(key=lambda x: x[1], reverse=True)
            return results[:top_k]
        except Exception as e:
            logger.error(f"Error searching index: {e}")
            return []

    def get_index_stats(self) -> Dict[str, Any]:
        return {
            "total_vectors": self.index.ntotal if self.index else 0,
            "total_documents": len(
                set(cid.split("_chunk_")[0] for cid in self.doc_id_to_index.keys())
            ),
            "embedding_model": self.embedding_model_name,
            "dimension": self.index.d if self.index else 0,
        }
