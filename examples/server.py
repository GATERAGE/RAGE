# SPDX-License-Identifier: Apache-2.0
"""
Minimal FastAPI server exposing RAGE as a hosted service.

Run:
    pip install -e ".[server,embeddings]"
    uvicorn examples.server:app --reload --port 8000

Endpoints:
    POST /ingest          — upload a file
    POST /retrieve        — semantic retrieval
    GET  /documents       — list ingested documents
    GET  /stats           — engine statistics

This server is the same shape that mindX runs at `/rage/*` (see
`mindx_backend_service/rage/routes.py` in the mindX repo). Mirrored
here so RAGE is independently hostable.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from rage import IngestionEngine, IndexingEngine, RetrievalEngine, StorageEngine

app = FastAPI(title="RAGE", version="0.2.0")

# Construct the four engines once at module load.
_storage = StorageEngine()
try:
    _indexing = IndexingEngine(storage_engine=_storage)
except Exception:
    _indexing = None
_ingestion = IngestionEngine(storage_engine=_storage, indexing_engine=_indexing)
_retrieval = RetrievalEngine(storage_engine=_storage, indexing_engine=_indexing)


class RetrieveRequest(BaseModel):
    query: str
    top_k: int = 5
    min_similarity: float = 0.5
    tags: Optional[List[str]] = None


@app.post("/ingest")
async def ingest(file: UploadFile = File(...), tags: Optional[str] = Form(None)):
    suffix = Path(file.filename or "").suffix or ".txt"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = Path(tmp.name)
    try:
        tag_list = [t.strip() for t in tags.split(",")] if tags else None
        result = await _ingestion.ingest_file(tmp_path, tags=tag_list)
    finally:
        tmp_path.unlink(missing_ok=True)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "ingest failed"))
    return result


@app.post("/retrieve")
async def retrieve(req: RetrieveRequest):
    hits = await _retrieval.retrieve_context(
        query=req.query, top_k=req.top_k,
        min_similarity=req.min_similarity, tags=req.tags,
    )
    return {"query": req.query, "results": hits, "count": len(hits)}


@app.get("/documents")
async def list_documents():
    docs = _storage.list_documents()
    return [
        {
            "doc_id": d.doc_id,
            "source_path": d.source_path,
            "file_type": d.file_type,
            "file_size": d.file_size,
            "ingested_at": d.ingested_at,
            "tags": d.tags,
        }
        for d in docs
    ]


@app.get("/stats")
async def stats():
    return _retrieval.get_retrieval_stats()
