# SPDX-License-Identifier: Apache-2.0
"""Smoke tests for IngestionEngine."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rage import IngestionEngine, StorageEngine


@pytest.mark.asyncio
async def test_ingest_text(tmp_path: Path):
    src = tmp_path / "hello.md"
    src.write_text("# Hello\n\nThis is a test.")

    storage = StorageEngine(storage_path=tmp_path / "storage")
    ingest = IngestionEngine(storage_engine=storage)

    result = await ingest.ingest_file(src, tags=["greetings"])
    assert result["success"] is True
    assert result["file_type"] == ".md"
    assert "doc_id" in result


@pytest.mark.asyncio
async def test_ingest_json(tmp_path: Path):
    src = tmp_path / "data.json"
    src.write_text(json.dumps({"a": 1, "b": [2, 3]}))

    storage = StorageEngine(storage_path=tmp_path / "storage")
    ingest = IngestionEngine(storage_engine=storage)

    result = await ingest.ingest_file(src)
    assert result["success"] is True


@pytest.mark.asyncio
async def test_ingest_directory(tmp_path: Path):
    (tmp_path / "a.md").write_text("alpha")
    (tmp_path / "b.txt").write_text("beta")
    (tmp_path / "c.bin").write_bytes(b"\x00\x01")  # unsupported

    storage = StorageEngine(storage_path=tmp_path / "storage")
    ingest = IngestionEngine(storage_engine=storage)

    result = await ingest.ingest_directory(tmp_path, recursive=False)
    assert result["success"] is True
    assert result["total"] == 2  # .bin is skipped
    assert len(result["ingested"]) == 2


@pytest.mark.asyncio
async def test_unsupported_file(tmp_path: Path):
    src = tmp_path / "binary.exe"
    src.write_bytes(b"\xff\xfe")

    storage = StorageEngine(storage_path=tmp_path / "storage")
    ingest = IngestionEngine(storage_engine=storage)

    result = await ingest.ingest_file(src)
    assert result["success"] is False
    assert "Unsupported" in result["error"]
