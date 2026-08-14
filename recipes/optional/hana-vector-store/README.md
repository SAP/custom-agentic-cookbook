---
title: "HANA Vector Store — RAG over customer documents"
sap-services: [HANA Cloud, SAP AI Core]
region-availability:
  - region: commercial
    hana-vector: yes
  - region: china-cf
    hana-vector: yes
    notes: "text-embedding-3-large not available — use a multilingual SAP-hosted model"
  - region: ksa
    hana-vector: yes
    notes: "regulated + non-regulated; confirm embedding model availability"
  - region: ns2
    hana-vector: yes
complexity: recipe
last-validated: 2026-07-06
---

# HANA Vector Store — RAG over customer documents

> **Flow:** optional retrieval **branch** layered on the agent project from **[optional/connect-data](../connect-data/)** (or the sovereign variant from optional/sovereign-model-gateway). Rejoins the happy path at **[02-deploy-btp](../../02-deploy-btp/)**.
> **Input:** the data-connected agent project from **optional/connect-data** (its Output), on a HANA-enabled tenant, plus source documents and an in-region embedding endpoint (AI Core `EMB_DEPLOYMENT_ID`, or the OpenAI-compatible gateway from optional/sovereign-model-gateway).
> **Output:** a `DOCS` table with `REAL_VECTOR(N)` loaded chunks, an HNSW index `IDX_DOCS_EMB`, and a `retrieve_context(query, k)` tool wired into the agent — the augmented project is consumed by **02-deploy-btp**.
> **Toolkit command:** none — this recipe extends the project emitted by `/sap-a2a-agent-toolkit:create-agent` in checkpoint 1.

Use this when the agent needs semantic retrieval over customer documents or structured business context. This recipe layers retrieval onto the finished agent from **[optional/connect-data](../connect-data/)**; work through checkpoint 1 and optional/connect-data first, then come back here.

> **Before you start**
> - Run `recipes/optional/region-preflight/` to confirm HANA Cloud and the embedding model are available in the target region.
> - For China and KSA, confirm which embedding model is allowed before Step 2. Check [`skills/sap-sovereign-regions/references/btp-regional-availability.md`](../../../skills/sap-sovereign-regions/references/btp-regional-availability.md).

## Prerequisites

- HANA Cloud instance available in the target region with vector engine enabled
- `HANA_HOST`, `HANA_PORT`, `HANA_USER`, `HANA_PASS` or a bound HDI service
- AI Core or OpenAI-compatible embedding endpoint (`EMB_DEPLOYMENT_ID` or equivalent)
- Source data files available locally or via accessible export

## Step 1 — Prepare the data

Invoke `sap-hana-data-prep`. It inspects source files, handles PII, chunks documents, and produces:

```text
prepared/chunks.jsonl            -- one record per chunk: id, text, metadata{}
prepared/ingestion-contract.yaml -- target_shape, embedding_model, pii_handling
prepared/sample-review.md        -- representative chunks for human sign-off
```

Review `prepared/sample-review.md` and confirm `pii_handling` is resolved before continuing.

## Step 2 — Create the HANA table

Read the `embedding_model` from `prepared/ingestion-contract.yaml` and set the vector dimension accordingly (`text-embedding-3-large` → 1536, `multilingual-e5-large` → 1024).

```sql
CREATE TABLE DOCS (
  ID        NVARCHAR(128) PRIMARY KEY,
  TEXT      NCLOB,
  METADATA  NCLOB,
  EMBEDDING REAL_VECTOR(1536)   -- match your model's dimension
);
```

Do **not** create the HNSW index yet — build it after the bulk load.

For schema details and pitfalls see `sap-hana-vector` → **Schema pattern** and **Pitfalls**.

## Step 3 — Embed and load chunks

```bash
pip install hdbcli langchain-hana generative-ai-hub-sdk
```

```python
import json, os
from pathlib import Path
from langchain_hana import HanaDB
from gen_ai_hub.proxy.langchain.openai import OpenAIEmbeddings
import hdbcli.dbapi as dbapi

conn = dbapi.connect(
    address=os.environ["HANA_HOST"],
    port=int(os.environ["HANA_PORT"]),
    user=os.environ["HANA_USER"],
    password=os.environ["HANA_PASS"],
    encrypt=True,
)
embeddings = OpenAIEmbeddings(deployment_id=os.environ["EMB_DEPLOYMENT_ID"])
store = HanaDB(connection=conn, embedding=embeddings, table_name="DOCS")

chunks = [json.loads(l) for l in Path("prepared/chunks.jsonl").read_text().splitlines()]
store.add_texts(
    texts=[c["text"] for c in chunks],
    metadatas=[c["metadata"] for c in chunks],
    ids=[c["id"] for c in chunks],
)
print(f"loaded {len(chunks)} chunks")
```

Then add the HNSW index:

```sql
CREATE HNSW VECTOR INDEX IDX_DOCS_EMB
  ON DOCS(EMBEDDING)
  SIMILARITY FUNCTION COSINE_SIMILARITY;
```

For the SQL-only ingestion path see `sap-hana-vector` → **Ingestion via SQL only**.

## Step 4 — Wire the retrieve_context tool

Wrap the vector search behind a named tool. Do not expose raw SQL or the HANA connection to the model.

```python
def retrieve_context(query: str, k: int = 4) -> list[dict]:
    results = store.similarity_search_with_score(query, k=k)
    return [{"text": doc.page_content, "metadata": doc.metadata, "score": float(score)}
            for doc, score in results]
```

Register `retrieve_context` as a tool in the agent:

```text
agent -> retrieve_context(query) -> top-k chunks -> model
```

For the SQL-based query pattern and metadata filtering see `sap-hana-vector` → **Query**.

## Verify it works

```sql
SELECT COUNT(*) FROM DOCS WHERE EMBEDDING IS NOT NULL;
-- expect: > 0
```

```python
hits = retrieve_context("test query matching something in your dataset")
assert hits, "no results — check row count and index"
print(f"top result (score={hits[0]['score']:.3f}):", hits[0]["text"][:120])
```

For the full SQL smoke-test see `sap-hana-vector` → **Verify**.

## Sovereign Note

`sap-hana-data-prep` flags restricted or unclassified data before embedding. Do not skip Step 1 for sovereign regions. Embedding model region constraints are listed in `sap-hana-vector` → **Pitfalls**.

## Cross-references

- [`skills/sap-hana-data-prep/`](../../../skills/sap-hana-data-prep/) — Step 1
- [`skills/sap-hana-vector/`](../../../skills/sap-hana-vector/) — Steps 2–4
- Hybrid (vector + KG): combine with [`recipes/optional/hana-kg-triple-store/`](../hana-kg-triple-store/)
- [`skills/sap-sovereign-regions/references/btp-regional-availability.md`](../../../skills/sap-sovereign-regions/references/btp-regional-availability.md)
- [`recipes/optional/region-preflight/`](../../optional/region-preflight/) — check HANA / vector-model availability in the target region.

