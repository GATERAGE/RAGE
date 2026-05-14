# SPDX-License-Identifier: Apache-2.0
"""Smoke tests for the filesystem StorageEngine."""
from __future__ import annotations

from pathlib import Path

from rage import StorageEngine


def test_store_and_load(tmp_path: Path):
    storage = StorageEngine(storage_path=tmp_path / "storage")
    doc_id = storage.store_document(
        source_path="hello.md",
        content=b"# Hello\n\nThis is a test document.",
        file_type=".md",
        tags=["test"],
    )
    assert doc_id

    content = storage.get_document(doc_id)
    assert content == b"# Hello\n\nThis is a test document."

    meta = storage.get_metadata(doc_id)
    assert meta is not None
    assert meta.file_type == ".md"
    assert "test" in meta.tags


def test_idempotent_store(tmp_path: Path):
    storage = StorageEngine(storage_path=tmp_path / "storage")
    a = storage.store_document("a.md", b"same content", ".md")
    b = storage.store_document("a.md", b"same content", ".md")
    assert a == b


def test_list_by_tag(tmp_path: Path):
    storage = StorageEngine(storage_path=tmp_path / "storage")
    storage.store_document("a.md", b"alpha", ".md", tags=["x"])
    storage.store_document("b.md", b"beta", ".md", tags=["y"])
    storage.store_document("c.md", b"gamma", ".md", tags=["x", "y"])

    x_docs = storage.list_documents(tags=["x"])
    assert len(x_docs) == 2

    all_docs = storage.list_documents()
    assert len(all_docs) == 3


def test_delete(tmp_path: Path):
    storage = StorageEngine(storage_path=tmp_path / "storage")
    doc_id = storage.store_document("a.md", b"content", ".md")
    assert storage.delete_document(doc_id) is True
    assert storage.get_document(doc_id) is None
    assert storage.delete_document(doc_id) is False
