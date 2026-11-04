---
title: "HANA KG / Triple Store — knowledge graph for agents"
sap-services: [HANA Cloud]
region-availability:
  - region: commercial
    hana-triple: yes
  - region: china-cf
    hana-triple: yes
    notes: "confirm tenant-level KG feature is enabled before starting"
  - region: ksa
    hana-triple: yes
    notes: "regulated + non-regulated"
  - region: ns2
    hana-triple: yes
complexity: recipe
last-validated: 2026-07-06
---

# HANA KG / Triple Store — knowledge graph for agents

> Flow: This is a separate HANA graph extension with its own application and deployment contract.
> Input: An agent with a tested graph-tool extension interface, source data, and a tenant with the graph feature enabled.
> Output: A HANA graph workspace loaded with source data and a `graph_query(nl_question)` tool. The augmented project needs separately tested deployment packaging.
> Toolkit command: None. This extension needs a compatible application interface.

The [Kyma sample recipe](../../02-deploy-btp/) fixes data and model providers to `mock`.
It does not package this HANA extension or its bindings.
The local data recipe alone does not provide this deployment handoff.

Use this guide for graph queries with a compatible agent tool interface.
HANA graph access and application integration require separate tests.
An S/4 connection is not a prerequisite for this HANA extension.

> **Before you start**
> - Run `recipes/optional/region-preflight/` to confirm HANA Cloud is available and the KG/triple-store feature is enabled on the target tenant.
> - If `CREATE GRAPH` fails, raise a tenant enablement request — the feature is not on by default in all tenants.
> - Agree the data model with customer domain experts before any loading. Changes to entity classes or predicates after bulk load require a reload.

## Prerequisites

- HANA Cloud instance in the target region with triple-store feature enabled
- `HANA_HOST`, `HANA_PORT`, `HANA_USER`, `HANA_PASS` or a bound HDI service
- Source data files and a domain expert available to confirm entity/relationship definitions

## Step 1 — Prepare the data

Invoke `sap-hana-data-prep`. It identifies entity classes and relationships with domain experts, then produces:

```text
prepared/entity_mapping.yaml      -- entity classes, id fields, predicates, IRI base
prepared/triples.ttl              -- full RDF dataset in Turtle
prepared/ingestion-contract.yaml  -- target_shape: hana_triple, pii_handling, open_questions
```

Do not proceed while `open_questions` is non-empty or `pii_handling` is unresolved.

## Step 2 — Create the graph workspace

```bash
pip install hdbcli
```

```python
import os
import hdbcli.dbapi as dbapi

conn = dbapi.connect(
    address=os.environ["HANA_HOST"],
    port=int(os.environ["HANA_PORT"]),
    user=os.environ["HANA_USER"],
    password=os.environ["HANA_PASS"],
    encrypt=True,
)
cur = conn.cursor()
cur.execute("CREATE GRAPH IF NOT EXISTS COE_PILOT WORKSPACE")
conn.commit()
print("workspace ready")
```

Pick a stable, descriptive workspace name — it appears in every SPARQL statement. For workspace details and SPARQL pitfalls see `sap-hana-triple` → **Graph workspace** and **Pitfalls**.

## Step 3 — Load triples

Batch INSERT DATA in chunks of 1 000 triples. Single-triple inserts are an order of magnitude slower.

```python
from pathlib import Path

GRAPH = "coe-pilot"

def load_triples(ttl_path: str, batch_size: int = 1000) -> int:
    lines = [l.strip() for l in Path(ttl_path).read_text(encoding="utf-8").splitlines()
             if l.strip() and not l.strip().startswith(("#", "@"))]
    triples = [l for l in lines if l.endswith(".")]
    total = 0
    for i in range(0, len(triples), batch_size):
        batch = "\n    ".join(triples[i : i + batch_size])
        cur.execute(f"SPARQL INSERT DATA {{ GRAPH <{GRAPH}> {{ {batch} }} }}")
        conn.commit()
        total += len(triples[i : i + batch_size])
        print(f"  {total}/{len(triples)}")
    return total

n = load_triples("prepared/triples.ttl")
print(f"total triples inserted: {n}")
```

For the full loading pattern and bulk-import alternatives see `sap-hana-triple` → **Loading**.

## Step 4 — Wire the graph_query tool

Keep the tool narrow: one NL question in, one answer out. Do not expose raw SPARQL generation or the cursor to the model. Few-shot the LLM with the ontology so it translates NL to SPARQL, then execute and rephrase.

```text
agent -> graph_query(nl_question) -> [NL→SPARQL→HANA→result→rephrase] -> answer
```

For the full agent-over-KG pattern see `sap-hana-triple` → **Agent-over-KG pattern**.

## Verify it works

```python
cur.execute(f"SPARQL SELECT (COUNT(*) AS ?n) WHERE {{ GRAPH <{GRAPH}> {{ ?s ?p ?o }} }}")
assert cur.fetchone()[0] > 0, "graph is empty — re-run load_triples()"
```

Run one relationship traversal matching a known pair from `prepared/entity_mapping.yaml`. For the full SPARQL verification query see `sap-hana-triple` → **Verify**.

## Feedback

Missing HANA KG capability, tenant enablement gaps, region blockers, or product feedback must be logged in GitHub. Use a region gap issue for regional/product gaps and a cookbook gap issue for recipe issues.

## Cross-references

- [`skills/sap-hana-data-prep/`](../../../skills/sap-hana-data-prep/) — Step 1
- [`skills/sap-hana-triple/`](../../../skills/sap-hana-triple/) — Steps 2–4
- Hybrid (KG + vector): combine with [`recipes/optional/hana-vector-store/`](../hana-vector-store/)
- [`skills/sap-sovereign-regions/references/btp-regional-availability.md`](../../../skills/sap-sovereign-regions/references/btp-regional-availability.md)
