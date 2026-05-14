# SPDX-License-Identifier: Apache-2.0
# (c) 2024-2026 GATERAGE — RAGE: Retrieval Augmented Generative Engine
"""
RAGE Storage Engine

Handles persistent storage of ingested documents and metadata on the
filesystem. The base tier; the pgvector tier (see `rage.pgvector`) is
opt-in for production deployments.
"""
from __future__ import annotations

import json
import hashlib
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass, asdict, field

logger = logging.getLogger("rage.storage")


def _default_storage_path() -> Path:
    """Default location is `./data/rage/storage/` relative to cwd."""
    return Path.cwd() / "data" / "rage" / "storage"


@dataclass
class DocumentMetadata:
    """Metadata for an ingested document."""

    doc_id: str
    source_path: str
    file_type: str
    file_size: int
    content_hash: str
    ingested_at: str
    last_accessed: Optional[str] = None
    access_count: int = 0
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class StorageEngine:
    """Filesystem storage for RAGE documents + metadata."""

    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = Path(storage_path) if storage_path else _default_storage_path()
        self.storage_path.mkdir(parents=True, exist_ok=True)

        self.documents_path = self.storage_path / "documents"
        self.documents_path.mkdir(exist_ok=True)

        self.metadata_path = self.storage_path / "metadata.json"
        self.metadata: Dict[str, DocumentMetadata] = {}

        self._load_metadata()

    def _load_metadata(self) -> None:
        if not self.metadata_path.exists():
            return
        try:
            with open(self.metadata_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for doc_id, meta_dict in data.items():
                self.metadata[doc_id] = DocumentMetadata(**meta_dict)
            logger.info(f"Loaded {len(self.metadata)} document metadata entries")
        except Exception as e:
            logger.error(f"Error loading metadata: {e}")

    def _save_metadata(self) -> None:
        try:
            data = {doc_id: asdict(meta) for doc_id, meta in self.metadata.items()}
            with open(self.metadata_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving metadata: {e}")

    @staticmethod
    def _generate_doc_id(source_path: str, content: bytes) -> str:
        content_hash = hashlib.sha256(content).hexdigest()[:16]
        path_hash = hashlib.md5(source_path.encode()).hexdigest()[:8]
        return f"{path_hash}_{content_hash}"

    def store_document(
        self,
        source_path: str,
        content: bytes,
        file_type: str,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Store a document and return its document ID."""
        doc_id = self._generate_doc_id(source_path, content)

        if doc_id in self.metadata:
            logger.info(f"Document {doc_id} already exists, updating metadata")
            existing = self.metadata[doc_id]
            existing.last_accessed = datetime.utcnow().isoformat() + "Z"
            existing.access_count += 1
            if tags:
                existing.tags = sorted(set(existing.tags + tags))
            if metadata:
                existing.metadata.update(metadata)
            self._save_metadata()
            return doc_id

        doc_file = self.documents_path / f"{doc_id}.bin"
        with open(doc_file, "wb") as f:
            f.write(content)

        doc_metadata = DocumentMetadata(
            doc_id=doc_id,
            source_path=source_path,
            file_type=file_type,
            file_size=len(content),
            content_hash=hashlib.sha256(content).hexdigest(),
            ingested_at=datetime.utcnow().isoformat() + "Z",
            tags=tags or [],
            metadata=metadata or {},
        )

        self.metadata[doc_id] = doc_metadata
        self._save_metadata()
        logger.info(f"Stored document {doc_id} from {source_path}")
        return doc_id

    def get_document(self, doc_id: str) -> Optional[bytes]:
        """Retrieve document content by ID."""
        if doc_id not in self.metadata:
            return None
        doc_file = self.documents_path / f"{doc_id}.bin"
        if not doc_file.exists():
            return None

        metadata = self.metadata[doc_id]
        metadata.last_accessed = datetime.utcnow().isoformat() + "Z"
        metadata.access_count += 1
        self._save_metadata()

        with open(doc_file, "rb") as f:
            return f.read()

    def get_metadata(self, doc_id: str) -> Optional[DocumentMetadata]:
        return self.metadata.get(doc_id)

    def list_documents(self, tags: Optional[List[str]] = None) -> List[DocumentMetadata]:
        docs = list(self.metadata.values())
        if tags:
            docs = [d for d in docs if any(t in d.tags for t in tags)]
        return docs

    def delete_document(self, doc_id: str) -> bool:
        if doc_id not in self.metadata:
            return False
        doc_file = self.documents_path / f"{doc_id}.bin"
        if doc_file.exists():
            doc_file.unlink()
        del self.metadata[doc_id]
        self._save_metadata()
        logger.info(f"Deleted document {doc_id}")
        return True
