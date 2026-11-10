# SPDX-License-Identifier: Apache-2.0
"""
Quick-start example for RAGE

Run:
    pip install -e ".[embeddings]"   # for semantic retrieval
    # OR
    pip install -e "."                # tag-based retrieval only
    python examples/quickstart.py
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from rage import IngestionEngine, IndexingEngine, RetrievalEngine, StorageEngine


async def main():
    # 1. Build the four engines.
    storage = StorageEngine(storage_path=Path("./data/rage/storage"))

    # IndexingEngine is optional. Without it, retrieval falls back to tags.
    try:
        indexing = IndexingEngine(storage_engine=storage)
    except Exception:
        indexing = None

    ingestion = IngestionEngine(storage_engine=storage, indexing_engine=indexing)
    retrieval = RetrievalEngine(storage_engine=storage, indexing_engine=indexing)

    # Ingest project README from localdocs
    readme = Path("README.md")
    if readme.exists():
        result = await ingestion.ingest_file(readme, tags=["readme"])
        print("ingest:", result)

    # Retrieve
    hits = await retrieval.retrieve_context("what is RAGE?", top_k=3)
    for h in hits:
        print(f"\n[{h['similarity']:.3f}] {h['metadata']['source_path']}")
        print(h["content"][:200], "…")


if __name__ == "__main__":
    asyncio.run(main())
