---
name: sap-hana-vector
description: Use this skill when building RAG on SAP HANA Cloud's vector engine — REAL_VECTOR columns, VECTOR_EMBEDDING() function, cosine search, and the langchain-hana / generative-ai-hub-sdk client paths. Covers ingestion, indexing, and querying patterns.
---

# SAP HANA Cloud Vector — RAG patterns

HANA Cloud ships a native vector column type (`REAL_VECTOR`) and a SQL function `VECTOR_EMBEDDING(text, model)` that calls AI Core embeddings inline. That means you can ingest, embed, and query without leaving SQL — but the Python clients (langchain-hana / generative-ai-hub-sdk) are usually nicer.

## Schema pattern

```sql
CREATE TABLE DOCS (
  ID NVARCHAR(64) PRIMARY KEY,
  TEXT NCLOB,
  METADATA NCLOB,                  -- JSON
  EMBEDDING REAL_VECTOR(1536)      -- dim = your embedding model's dim
);

-- Cosine HNSW index — fastest, smallest, default choice.
CREATE HNSW VECTOR INDEX IDX_DOCS_EMB ON DOCS(EMBEDDING) SIMILARITY FUNCTION COSINE_SIMILARITY;
```

## Before ingestion: data preparation

Run `sap-hana-data-prep` before this skill. It produces the ingestion contract and chunked artifacts this skill consumes:

```text
prepared/chunks.jsonl            -- id, text, metadata per chunk
prepared/ingestion-contract.yaml -- confirms target_shape: hana_vector, embedding_model, pii_handling
```

If `prepared/ingestion-contract.yaml` is absent or `target_shape` is not `hana_vector`, return to `sap-hana-data-prep`.

## Ingestion via SQL only

```sql
INSERT INTO DOCS (ID, TEXT, EMBEDDING)
  VALUES (?, ?, VECTOR_EMBEDDING(?, 'AICORE', 'text-embedding-3-large'));
```

For region-availability of `text-embedding-3-large` see [`sap-sovereign-regions`](../sap-sovereign-regions/SKILL.md) and run [`recipes/00-develop/00-region-preflight/`](../../recipes/00-develop/00-region-preflight/) — China and KSA need to swap to a multilingual SAP-hosted embedding instead.

## Ingestion via Python

```python
from langchain_hana import HanaDB
from gen_ai_hub.proxy.langchain.openai import OpenAIEmbeddings

embeddings = OpenAIEmbeddings(deployment_id=os.environ["EMB_DEPLOYMENT_ID"])
store = HanaDB(connection=hana_conn, embedding=embeddings, table_name="DOCS")

store.add_texts(
    texts=["...chunk 1...", "...chunk 2..."],
    metadatas=[{"source": "doc.pdf", "page": 1}, ...],
)
```

## Query

```python
results = store.similarity_search_with_score("how do I deploy to Kyma?", k=4)
```

Or as SQL:

```sql
SELECT TOP 4 ID, TEXT, COSINE_SIMILARITY(EMBEDDING, VECTOR_EMBEDDING(?, 'AICORE', 'text-embedding-3-large')) AS SCORE
  FROM DOCS ORDER BY SCORE DESC;
```

## Pitfalls

- Wrong dimension → INSERT fails. Pick the embedding model first, then create the table.
- No HNSW index → slow at >10k rows. Add the index after the bulk-load, not before.
- Mixing embedding models without re-indexing → silent quality drop. Pick one and stick to it.
- Embedding model mismatch with region → run [`recipes/00-develop/00-region-preflight/`](../../recipes/00-develop/00-region-preflight/) first and cross-check `sap-sovereign-regions`; China / KSA / NS2 constraints on `text-embedding-3-large` apply here too.

## Verify

```sql
SELECT COUNT(*) FROM DOCS WHERE EMBEDDING IS NOT NULL;
-- expect: > 0
SELECT TOP 1 ID, COSINE_SIMILARITY(EMBEDDING, VECTOR_EMBEDDING('hello', 'AICORE', 'text-embedding-3-large')) FROM DOCS;
-- expect: a score in (0, 1)
```

## Cross-references

- Upstream data prep: [`skills/sap-hana-data-prep/`](../sap-hana-data-prep/) — run this first for any new dataset
- Walkthrough: [`recipes/optional/hana-vector-store/`](../../recipes/optional/hana-vector-store/)
- Template: `references/kg-project/` for the KG+vector hybrid pattern — planned; tracked as TODO in [`references/README.md`](../../references/README.md).
- HANA docs: https://help.sap.com/docs/hana-cloud-database/sap-hana-cloud-sap-hana-database-vector-engine-guide
