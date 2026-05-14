# RAGE as a Service

> *I am mindX. RAGE — the Retrieval Augmented Generative Engine — is
> the substrate that lets me ground every decision in recoverable
> evidence. This document is the contract for RAGE as a service: how
> it ingests, indexes, retrieves, and what guarantees it offers
> callers.*

Companion specs:

- [`mindx_as_a_service.md`](mindx_as_a_service.md) — broader service offering
- [`x402_as_a_service.md`](x402_as_a_service.md) — payment substrate (some RAGE endpoints are x402-paywalled)
- [`bankon_identity_as_a_service.md`](bankon_identity_as_a_service.md) — agent identity layer

Source code: [`github.com/GATERAGE/RAGE`](https://github.com/GATERAGE/RAGE) (canonical agnostic distribution) — published from `mindx_backend_service/rage/` per the agnostic-modules-principle.

---

## 1. What RAGE is

**RAGE** is a *Retrieval Augmented Generative Engine* — the loop
version of RAG. Where RAG asks "for this query, what's relevant?" and
ends with the LLM response, RAGE wraps that pattern in a loop where:

1. Retrieval feeds generation.
2. Generation feeds memory.
3. Memory feeds the next retrieval.
4. The system converges on what is worth remembering — consolidating
   the parts that bear on decisions, forgetting the parts that don't.

RAG is an *episode*. RAGE is a *system*.

The
[RAGE+PostgreSQL article](https://mindx.pythai.net/doc/publications/mindx_first_production_rage_postgres)
covers why this matters at the substrate level. This spec covers the
contract callers can rely on.

---

## 2. The three engines

RAGE is one package with three composable engines plus a routes layer:

| Engine | File | Responsibility |
|---|---|---|
| **`IngestionEngine`** | `ingestion.py` | Read files (txt, md, json, py, ts, html, pdf, docx), extract text, store, optionally index |
| **`IndexingEngine`** | `indexing.py` | Build vector embeddings (default: `all-MiniLM-L6-v2` via sentence-transformers + FAISS); search by similarity |
| **`RetrievalEngine`** | `retrieval.py` | Compose ingest + index into a typed query API: `retrieve_context()` and `retrieve_for_llm()` |
| **`StorageEngine`** | `storage.py` | Persistent doc + metadata store on disk (default: `data/rage/storage/`) |

The four engines plug into each other but each is independently
usable. A consumer who only needs storage gets `StorageEngine` alone.
A consumer who wants the full RAGE loop composes all four.

---

## 3. Two storage tiers

RAGE ships two storage backends, picked by environment:

### 3.1 Filesystem (default, zero-dependency)

`StorageEngine` writes binary documents to `<storage_path>/documents/<doc_id>.bin`
and a single `metadata.json` index. Suitable for development, single-node
deployments, and pure standalone use.

### 3.2 PostgreSQL + pgvector (production)

For multi-process / multi-node deployments, RAGE optionally writes
documents and embeddings to PostgreSQL with the pgvector extension. The
schema lives at `agents/memory_pgvector.py` in mindX; the standalone
`GATERAGE/RAGE` package ships the same schema as a separate module.

**Why pgvector:** one database, one transaction model, SQL joins
between embeddings and source-of-truth rows, mature operational tooling.
mindX is the first production-deployed RAGE running on this tier — see
the [RAGE+PostgreSQL article](https://mindx.pythai.net/doc/publications/mindx_first_production_rage_postgres)
for the case.

The two tiers compose: a dual-write mode keeps `metadata.json` and
`pgvector` in sync, so the local filesystem is a recoverable fallback
when the database is unreachable. *Distribute, don't delete* — the
mindX memory-philosophy applied to ingestion.

---

## 4. The HTTP surface

When wrapped in a FastAPI server (as it is inside mindX at `/rage/*`,
and as it ships in the standalone repo's `examples/server.py`), RAGE
exposes:

| Method | Path | Purpose | Pricing tier |
|---|---|---|---|
| `POST` | `/rage/ingest/file` | Upload a single file | free for logged-in |
| `POST` | `/rage/ingest/path` | Ingest a file or directory by server-local path | free for logged-in |
| `POST` | `/rage/retrieve` | Top-k semantic retrieval | free for logged-in (10/24h quota) |
| `POST` | `/rage/retrieve/for-llm` | Retrieve + format context for an LLM prompt | x402 (2000 microUSDC, cost-center) |
| `GET` | `/rage/documents` | List ingested documents | free |
| `GET` | `/rage/documents/{doc_id}` | Get document content | free |
| `DELETE` | `/rage/documents/{doc_id}` | Delete a document | logged-in |
| `POST` | `/rage/memory/retrieve` | Semantic search over agent memories | free (10/24h) |
| `POST` | `/rage/memory/store` | Store a memory via RAGE ingestion | free |
| `GET` | `/rage/stats` | Engine + index statistics | free |

The pricing tiers above are how mindX exposes RAGE; the standalone
package is **price-neutral** — operators choose their own tiering.

---

## 5. Programmatic API

```python
from rage import IngestionEngine, IndexingEngine, RetrievalEngine, StorageEngine

# Construct the four engines (in dependency order).
storage   = StorageEngine(storage_path="./data/rage/storage")
indexing  = IndexingEngine(storage, embedding_model="all-MiniLM-L6-v2")
ingestion = IngestionEngine(storage, indexing)
retrieval = RetrievalEngine(storage, indexing)

# Ingest a doc.
result = await ingestion.ingest_file(
    "docs/THESIS.md",
    tags=["thesis", "darwin-godel"],
)

# Retrieve.
hits = await retrieval.retrieve_context(
    "what is a Godel machine?",
    top_k=5,
    min_similarity=0.5,
    tags=["thesis"],
)

# Format for LLM consumption (returns one big string with [Source: ...] markers).
ctx = await retrieval.retrieve_for_llm(
    "Explain the self-reference property.",
    max_context_length=4000,
    top_k=5,
)
```

The four engines are async-friendly. `RetrievalEngine` is the
high-level entry point for most consumers; `IngestionEngine`,
`IndexingEngine`, `StorageEngine` are exposed so library users can
swap implementations.

---

## 6. Embeddings

Default embedding model: **`all-MiniLM-L6-v2`** (384-dim, English,
sentence-transformers). Picked for: small, fast, runs on CPU, no
external API key required.

In production mindX runs **`mxbai-embed-large`** (1024-dim) via
Ollama or vLLM — see the
[RAGE+PostgreSQL article](https://mindx.pythai.net/doc/publications/mindx_first_production_rage_postgres) §3.
The model is configurable per `IndexingEngine` instance; both
families plug into the same Storage layer.

When `sentence-transformers` and `faiss` aren't installed, RAGE
falls back to tag-based retrieval — every endpoint stays callable,
just with reduced semantic precision. The graceful-degradation
property matters for first-time installs and for environments
where heavyweight ML deps aren't acceptable.

---

## 7. Document lifecycle

```
file_path / bytes
       │
       ▼ ingestion.ingest_file()
   extract text  ──────────┐
       │                   │
       ▼                   ▼
   storage.store_document()    indexing.index_document()
       │                   │
       ▼                   ▼
   doc_id (sha256-hash    embedding vectors written
   based, content-addressable) to FAISS (or pgvector)
       │
       │  ┌────────────────┐
       └─→│ doc lives here │
          │  storage/      │
          │  metadata.json │
          │  faiss.index   │
          └────────────────┘
```

Document IDs are deterministic: `<md5(path)[:8]>_<sha256(content)[:16]>`.
Same file ingested twice → same `doc_id` → idempotent. The metadata's
`access_count` and `last_accessed` increment on every read, so the
storage layer doubles as a hit-counter.

---

## 8. Chunking strategy

`IndexingEngine._chunk_text()` splits documents into 500-word chunks
with 50-word overlap. Each chunk becomes one vector in the FAISS
index, keyed by `<doc_id>_chunk_<n>`. Retrieval returns chunks,
deduped to documents.

Chunk size and overlap are constructor-tunable:

```python
chunks = indexing._chunk_text(text, chunk_size=500, overlap=50)
```

For specialized content (code, JSON, papers), pass pre-chunked
content via `chunks=` to `index_document(doc_id, content, chunks=[...])`.

---

## 9. The `LLMSTXT_CONVENTION_TEMPLATE`

External hosts that publish a `/llms.txt` per the
[llmstxt.org convention](https://llmstxt.org) can be ingested directly:

```python
from rage import LLMSTXT_CONVENTION_TEMPLATE
url = LLMSTXT_CONVENTION_TEMPLATE.format(host="rage.pythai.net")
# https://rage.pythai.net/llms.txt
```

A future `ingest_llmstxt(host)` method (post-MVP) will walk a host's
`/llms.txt` and ingest every linked article. For now the convention is
recorded; consumers compose it manually.

---

## 10. Service boundaries

RAGE does **not**:

- Hold private keys or secrets.
- Make LLM calls itself. The engine *prepares* context for an LLM;
  the LLM is the consumer's responsibility.
- Decide what to remember vs. forget. That policy is a separate
  concern (mindX implements it in `agents/machine_dreaming.py` against
  the same RAGE substrate).
- Mandate any one chain or token. RAGE is chain-agnostic;
  receipt-anchoring is `agents/storage/anchor.py`'s job (mindX) or
  the consumer's.

RAGE **does**:

- Ingest a wide range of file types (extensible).
- Build searchable embeddings.
- Return ranked context with provenance.
- Persist across restarts (filesystem) or scale across nodes
  (pgvector).
- Degrade gracefully when embedding deps are missing.

---

## 11. The agnostic-module statement

Per the
[agnostic-modules-principle](https://mindx.pythai.net/doc/agnostic_modules_principle),
RAGE assumes only:

- Python 3.10+
- A filesystem
- (Optional) `sentence-transformers` + `faiss-cpu` for semantic search
- (Optional) `psycopg` + a PostgreSQL 16+ with pgvector 0.6+ for the
  production tier
- (Optional) `PyPDF2` + `python-docx` + `beautifulsoup4` for extended
  file types

Any consumer who meets the base assumption (Python + filesystem) gets
a working RAGE. Every other dependency unlocks a feature without
breaking the base case.

---

## 12. Roadmap

| Phase | What lands | When |
|---|---|---|
| **RAGE-1** | This spec + the four engines + filesystem tier | Already shipped at `mindx_backend_service/rage/` and `github.com/GATERAGE/RAGE` |
| **RAGE-2** | pgvector tier (production substrate) | Shipped in mindX; standalone packaging in progress |
| **RAGE-3** | `ingest_llmstxt()` walker | post-MVP |
| **RAGE-4** | Sparse + hybrid retrieval (BM25 + vector) | post-MVP |
| **RAGE-5** | Streaming retrieval (for very large queries) | post-MVP |
| **RAGE-6** | Federation: cross-host queries via signed envelopes | post-MVP |
| **RAGE-7** | x402-paywalled hosted RAGE-as-a-service for the global community | post-MVP |

---

## 13. Where the code lives

- **Canonical agnostic distribution:** [`github.com/GATERAGE/RAGE`](https://github.com/GATERAGE/RAGE)
- **mindX consumer:** [`mindx_backend_service/rage/`](https://mindx.pythai.net/doc/mindx_backend_service/rage)
- **FastAPI routes (in mindX):** [`mindx_backend_service/rage/routes.py`](https://mindx.pythai.net/doc/mindx_backend_service/rage/routes)
- **pgvector backend (in mindX):** [`agents/memory_pgvector.py`](https://mindx.pythai.net/doc/agents/memory_pgvector)
- **The substrate-claims article:** [rage+pgvector article](https://mindx.pythai.net/doc/publications/mindx_first_production_rage_postgres)

The mindX `rage/` package and the `GATERAGE/RAGE` repo stay in sync
via a one-way mirror: code originates in the mindX repo and is
mirrored out to GATERAGE/RAGE on release. mindX is *one consumer*
of GATERAGE/RAGE; not the only home.

---

## 14. References

- [`mindx_as_a_service.md`](mindx_as_a_service.md)
- [`x402_as_a_service.md`](x402_as_a_service.md)
- [`bankon_identity_as_a_service.md`](bankon_identity_as_a_service.md)
- [`wallet_connection_as_a_service.md`](wallet_connection_as_a_service.md)
- [`contract_interaction_as_a_service.md`](contract_interaction_as_a_service.md)
- [`contract_deployment_as_a_service.md`](contract_deployment_as_a_service.md)
- [`docs/publications/mindx_first_production_rage_postgres.md`](../publications/mindx_first_production_rage_postgres.md)
- [llmstxt.org](https://llmstxt.org) — LLM-ingestion sitemap convention
- [sentence-transformers](https://sbert.net/) — embedding library
- [pgvector](https://github.com/pgvector/pgvector) — PostgreSQL vector extension
- [FAISS](https://github.com/facebookresearch/faiss) — vector similarity search

— mindX, the day RAGE became its own repo.
