# SPDX-License-Identifier: Apache-2.0
# (c) 2024-2026 GATERAGE — RAGE: Retrieval Augmented Generative Engine
"""
RAGE: Retrieval Augmented Generative Engine

A composable retrieval framework for grounding LLM calls in evidence
that can be ingested, indexed, retrieved, persisted, and replayed.

Four engines:
  - StorageEngine   — durable doc + metadata store (filesystem default)
  - IndexingEngine  — vector embeddings + FAISS / pgvector search
  - IngestionEngine — file/byte ingestion across txt / md / json / py / ts / html / pdf / docx
  - RetrievalEngine — typed query API (`retrieve_context`, `retrieve_for_llm`)

Companion convention:
  - LLMSTXT_CONVENTION_TEMPLATE — per llmstxt.org, hosts may publish
    `/llms.txt` as an LLM-ingestion sitemap. RAGE consumes this when
    ingesting from external hosts.

Spec: see `docs/rage_as_a_service.md` in this repo (mirror of
`mindx_backend_service/rage/` in github.com/agenticplace).
"""

from .ingestion import IngestionEngine
from .retrieval import RetrievalEngine
from .indexing import IndexingEngine
from .storage import StorageEngine


# ─── External LLM-ingestion convention ──────────────────────────────────
# Per llmstxt.org, hosts may publish a /llms.txt sitemap for LLM
# ingestion. Format `LLMSTXT_CONVENTION_TEMPLATE` with a host to build
# the URL.
LLMSTXT_CONVENTION_TEMPLATE = "https://{host}/llms.txt"

LLMSTXT_KNOWN_HOSTS = (
    "rage.pythai.net",
)


__version__ = "0.2.0"

__all__ = [
    "IngestionEngine",
    "RetrievalEngine",
    "IndexingEngine",
    "StorageEngine",
    "LLMSTXT_CONVENTION_TEMPLATE",
    "LLMSTXT_KNOWN_HOSTS",
    "__version__",
]
