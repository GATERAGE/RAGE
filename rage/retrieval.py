# SPDX-License-Identifier: Apache-2.0
# (c) 2024-2026 GATERAGE — RAGE: Retrieval Augmented Generative Engine
"""
RAGE Retrieval Engine

The high-level entry point for consumers. Composes Storage + Indexing
into typed `retrieve_context()` and `retrieve_for_llm()` calls.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .indexing import IndexingEngine
from .storage import StorageEngine

logger = logging.getLogger("rage.retrieval")


class RetrievalEngine:
    """High-level context retrieval for LLM generation."""

    def __init__(
        self,
        storage_engine: StorageEngine,
        indexing_engine: Optional[IndexingEngine] = None,
    ):
        self.storage = storage_engine
        self.indexing = indexing_engine

    async def retrieve_context(
        self,
        query: str,
        top_k: int = 5,
        min_similarity: float = 0.5,
        tags: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Return ranked list of `{doc_id, content, similarity, metadata}`."""
        results: List[Dict[str, Any]] = []

        if self.indexing:
            search_results = await self.indexing.search(query, top_k=top_k * 2)
            for doc_id, similarity, metadata in search_results:
                if similarity < min_similarity:
                    continue
                if tags and not any(t in metadata.tags for t in tags):
                    continue
                content = self.storage.get_document(doc_id)
                if not content:
                    continue
                try:
                    text_content = content.decode("utf-8")
                except Exception:
                    text_content = str(content)[:1000]
                results.append({
                    "doc_id": doc_id,
                    "content": text_content[:2000],
                    "similarity": similarity,
                    "metadata": {
                        "source_path": metadata.source_path,
                        "file_type": metadata.file_type,
                        "tags": metadata.tags,
                        "ingested_at": metadata.ingested_at,
                    },
                })
                if len(results) >= top_k:
                    break
        else:
            # Tag-based fallback for installs without embedding deps.
            documents = self.storage.list_documents(tags=tags)
            for metadata in documents[:top_k]:
                content = self.storage.get_document(metadata.doc_id)
                if not content:
                    continue
                try:
                    text_content = content.decode("utf-8")
                except Exception:
                    text_content = str(content)[:1000]
                results.append({
                    "doc_id": metadata.doc_id,
                    "content": text_content[:2000],
                    "similarity": 0.5,
                    "metadata": {
                        "source_path": metadata.source_path,
                        "file_type": metadata.file_type,
                        "tags": metadata.tags,
                        "ingested_at": metadata.ingested_at,
                    },
                })
        return results

    async def retrieve_for_llm(
        self,
        query: str,
        max_context_length: int = 4000,
        top_k: int = 5,
    ) -> str:
        r"""Return a single string of `[Source: <path>]\n<chunk>` blocks."""
        contexts = await self.retrieve_context(query, top_k=top_k)
        formatted: List[str] = []
        total = 0
        for ctx in contexts:
            block = f"[Source: {ctx['metadata']['source_path']}]\n{ctx['content']}\n"
            if total + len(block) > max_context_length:
                break
            formatted.append(block)
            total += len(block)
        return "\n---\n".join(formatted)

    def get_retrieval_stats(self) -> Dict[str, Any]:
        all_docs = self.storage.list_documents()
        stats: Dict[str, Any] = {
            "total_documents": len(all_docs),
            "total_size_bytes": sum(d.file_size for d in all_docs),
            "indexed_documents": 0,
            "index_vectors": 0,
        }
        if self.indexing:
            idx_stats = self.indexing.get_index_stats()
            stats["indexed_documents"] = idx_stats.get("total_documents", 0)
            stats["index_vectors"] = idx_stats.get("total_vectors", 0)
        return stats
