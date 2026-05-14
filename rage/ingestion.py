# SPDX-License-Identifier: Apache-2.0
# (c) 2024-2026 GATERAGE — RAGE: Retrieval Augmented Generative Engine
"""
RAGE Ingestion Engine

Reads files (txt/md/json/py/ts/html/pdf/docx), extracts text, stores
the bytes via StorageEngine, and optionally indexes via IndexingEngine.

Optional extractors gracefully no-op when their backing deps aren't
installed; install via the `pdf`, `docx`, or `html` extras.
"""
from __future__ import annotations

import fnmatch
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .storage import StorageEngine
from .indexing import IndexingEngine

logger = logging.getLogger("rage.ingestion")


class IngestionEngine:
    """File / directory ingestion across common text-bearing formats."""

    def __init__(
        self,
        storage_engine: Optional[StorageEngine] = None,
        indexing_engine: Optional[IndexingEngine] = None,
    ):
        self.storage = storage_engine or StorageEngine()
        self.indexing = indexing_engine

        self.supported_types = {
            ".txt": self._ingest_text,
            ".md": self._ingest_text,
            ".json": self._ingest_json,
            ".py": self._ingest_text,
            ".js": self._ingest_text,
            ".ts": self._ingest_text,
            ".html": self._ingest_html,
            ".pdf": self._ingest_pdf,
            ".docx": self._ingest_docx,
        }

    async def ingest_file(
        self,
        file_path: Union[str, Path],
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        auto_index: bool = True,
    ) -> Dict[str, Any]:
        """Ingest a file into RAGE. Returns {success, doc_id, ...}."""
        file_path = Path(file_path)
        if not file_path.exists():
            return {"success": False, "error": f"File not found: {file_path}"}

        try:
            with open(file_path, "rb") as f:
                content = f.read()

            file_type = file_path.suffix.lower()
            if file_type not in self.supported_types:
                return {"success": False, "error": f"Unsupported file type: {file_type}"}

            extractor = self.supported_types[file_type]
            text_content = await extractor(content)
            if not text_content:
                return {"success": False, "error": "Could not extract text content"}

            doc_id = self.storage.store_document(
                source_path=str(file_path),
                content=content,
                file_type=file_type,
                tags=tags or [],
                metadata=metadata or {},
            )

            if auto_index and self.indexing:
                await self.indexing.index_document(doc_id, text_content)

            return {
                "success": True,
                "doc_id": doc_id,
                "file_path": str(file_path),
                "file_type": file_type,
                "content_length": len(text_content),
                "tags": tags or [],
            }
        except Exception as e:
            logger.error(f"Error ingesting file {file_path}: {e}")
            return {"success": False, "error": str(e)}

    async def ingest_directory(
        self,
        directory_path: Union[str, Path],
        recursive: bool = True,
        file_patterns: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Ingest all supported files from a directory."""
        directory_path = Path(directory_path)
        if not directory_path.exists() or not directory_path.is_dir():
            return {"success": False, "error": f"Directory not found: {directory_path}"}

        results: Dict[str, Any] = {"success": True, "ingested": [], "failed": [], "total": 0}

        files = list(directory_path.rglob("*")) if recursive else list(directory_path.glob("*"))
        supported_files = [
            f for f in files
            if f.is_file() and f.suffix.lower() in self.supported_types
        ]
        if file_patterns:
            supported_files = [
                f for f in supported_files
                if any(fnmatch.fnmatch(str(f), pat) for pat in file_patterns)
            ]

        results["total"] = len(supported_files)
        for file_path in supported_files:
            result = await self.ingest_file(file_path, tags=tags)
            if result.get("success"):
                results["ingested"].append(result)
            else:
                results["failed"].append({"file": str(file_path), "error": result.get("error")})
        return results

    # ── extractors ──────────────────────────────────────────

    async def _ingest_text(self, content: bytes) -> str:
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            return content.decode("utf-8", errors="ignore")

    async def _ingest_json(self, content: bytes) -> str:
        try:
            data = json.loads(content.decode("utf-8"))
            return json.dumps(data, indent=2)
        except Exception as e:
            logger.error(f"Error parsing JSON: {e}")
            return content.decode("utf-8", errors="ignore")

    async def _ingest_html(self, content: bytes) -> str:
        try:
            from bs4 import BeautifulSoup  # type: ignore
            soup = BeautifulSoup(content, "html.parser")
            return soup.get_text()
        except ImportError:
            logger.warning("beautifulsoup4 not installed; install rage[html] for HTML extraction.")
            return content.decode("utf-8", errors="ignore")
        except Exception as e:
            logger.error(f"Error parsing HTML: {e}")
            return content.decode("utf-8", errors="ignore")

    async def _ingest_pdf(self, content: bytes) -> str:
        try:
            import PyPDF2  # type: ignore
            from io import BytesIO
            reader = PyPDF2.PdfReader(BytesIO(content))
            return "\n".join((page.extract_text() or "") for page in reader.pages)
        except ImportError:
            logger.warning("PyPDF2 not installed; install rage[pdf] for PDF extraction.")
            return ""
        except Exception as e:
            logger.error(f"Error parsing PDF: {e}")
            return ""

    async def _ingest_docx(self, content: bytes) -> str:
        try:
            from docx import Document  # type: ignore
            from io import BytesIO
            doc = Document(BytesIO(content))
            return "\n".join(p.text for p in doc.paragraphs)
        except ImportError:
            logger.warning("python-docx not installed; install rage[docx] for DOCX extraction.")
            return ""
        except Exception as e:
            logger.error(f"Error parsing DOCX: {e}")
            return ""
