# SPDX-License-Identifier: Apache-2.0
"""Smoke tests for RetrievalEngine — tag-based fallback (no embeddings required)."""
from __future__ import annotations

from pathlib import Path

import pytest

from rage import IngestionEngine, RetrievalEngine, StorageEngine


@pytest.mark.asyncio
async def test_retrieve_tag_filtered(tmp_path: Path):
    (tmp_path / "alpha.md").write_text("alpha content")
    (tmp_path / "beta.md").write_text("beta content")

    storage = StorageEngine(storage_path=tmp_path / "storage")
    ingest = IngestionEngine(storage_engine=storage)

    await ingest.ingest_file(tmp_path / "alpha.md", tags=["x"])
    await ingest.ingest_file(tmp_path / "beta.md", tags=["y"])

    retrieval = RetrievalEngine(storage_engine=storage, indexing_engine=None)
    out = await retrieval.retrieve_context("anything", tags=["x"])
    assert len(out) == 1
    assert "alpha" in out[0]["content"]


@pytest.mark.asyncio
async def test_retrieve_for_llm(tmp_path: Path):
    (tmp_path / "doc.md").write_text("the answer is forty-two")

    storage = StorageEngine(storage_path=tmp_path / "storage")
    ingest = IngestionEngine(storage_engine=storage)
    await ingest.ingest_file(tmp_path / "doc.md")

    retrieval = RetrievalEngine(storage_engine=storage)
    out = await retrieval.retrieve_for_llm("what is the answer?")
    assert "forty-two" in out
    assert "[Source:" in out


@pytest.mark.asyncio
async def test_llmstxt_template():
    from rage import LLMSTXT_CONVENTION_TEMPLATE, LLMSTXT_KNOWN_HOSTS
    url = LLMSTXT_CONVENTION_TEMPLATE.format(host=LLMSTXT_KNOWN_HOSTS[0])
    assert url == "https://rage.pythai.net/llms.txt"
