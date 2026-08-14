---
name: sap-hana-triple
description: Use this skill when building Knowledge Graphs on SAP HANA Cloud's Triple Store — SPARQL 1.1 modeling, graph workspaces, ingestion from S/4 or business data, and the agent-over-KG NL→SPARQL→answer pattern. Includes hybrid KG+vector retrieval where both engines live in the same HANA tenant.
---

# SAP HANA Cloud Triple Store — SPARQL 1.1 / Knowledge Graphs

HANA Cloud's Triple Store is SPARQL 1.1 over a graph workspace. You model your domain as RDF triples (subject, predicate, object), load them, and query with SPARQL.

## Graph workspace

```sql
CREATE GRAPH IF NOT EXISTS COE_PILOT WORKSPACE;
```

## Modeling — ontology in Turtle

```turtle
@prefix : <http://coe.example/customer#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .

:Customer a rdfs:Class .
:hasPrimaryContact a rdf:Property ;
    rdfs:domain :Customer ; rdfs:range :Contact .
```

Keep the ontology in `ontology/*.ttl` files in the project — code-review changes the same way you do schema changes.

## Before loading: data preparation

Run `sap-hana-data-prep` before this skill. It produces the entity mapping and Turtle triples this skill consumes:

```text
prepared/entity_mapping.yaml      -- entity classes, id fields, relationship predicates, IRI base
prepared/triples.ttl              -- sample or full RDF in Turtle
prepared/ingestion-contract.yaml  -- confirms target_shape: hana_triple, pii_handling
```

If `prepared/ingestion-contract.yaml` is absent or `target_shape` is not `hana_triple`, return to `sap-hana-data-prep`.

## Loading

Bulk load via SPARQL INSERT DATA over an hdbcli connection:

```python
import hdbcli.dbapi as db
conn = db.connect(address=HANA_HOST, port=443, user=USER, password=PASS, encrypt=True)
cur = conn.cursor()
cur.execute("""
SPARQL INSERT DATA {
  GRAPH <coe-pilot> {
    <http://coe.example/customer#acme> a <http://coe.example/customer#Customer> ;
        <http://coe.example/customer#hasPrimaryContact> <http://coe.example/customer#alice> .
    <http://coe.example/customer#alice> a <http://coe.example/customer#Contact> .
  }
}""")
```

## Query

```python
cur.execute("""
SPARQL SELECT ?contactLabel WHERE {
  GRAPH <coe-pilot> {
    <http://coe.example/customer#acme> <http://coe.example/customer#hasPrimaryContact> ?c .
    ?c <http://www.w3.org/2000/01/rdf-schema#label> ?contactLabel .
  }
}""")
```

## Agent-over-KG pattern

1. Few-shot the LLM with the ontology to emit SPARQL from NL.
2. Execute the SPARQL.
3. Re-prompt the LLM to phrase the result.

This pattern lives conceptually in `references/kg-project/agent/kg-agent.py` (planned template; tracked as TODO in [`references/README.md`](../../references/README.md)). Until it lands, the SPARQL-over-HANA walkthrough is in [`recipes/optional/hana-kg-triple-store/`](../../recipes/optional/hana-kg-triple-store/).

## Hybrid KG + Vector

You can put `REAL_VECTOR` columns on a graph's annotation table and use a vector pre-filter to narrow candidate nodes before SPARQL traversal. Not yet documented as its own recipe — combine [`recipes/optional/hana-vector-store/`](../../recipes/optional/hana-vector-store/) and [`recipes/optional/hana-kg-triple-store/`](../../recipes/optional/hana-kg-triple-store/) for now.

## Pitfalls

- Forgetting the `GRAPH <name>` clause → query hits the default graph and returns nothing.
- IRI vs literal confusion: enclose IRIs in `< >`, literals in `" "`.
- Mixing tenants: each HANA Cloud tenant has its own workspace; cross-tenant SPARQL is not transparent.
- Insert performance: batch INSERT DATA in chunks of 1000 triples — much faster than one-by-one.

## Verify

```python
cur.execute("SPARQL SELECT (COUNT(*) AS ?n) WHERE { GRAPH <coe-pilot> { ?s ?p ?o } }")
n = cur.fetchone()[0]
assert n > 0, "graph is empty — re-run ingest"
```

## Cross-references

- Upstream data prep: [`skills/sap-hana-data-prep/`](../sap-hana-data-prep/) — run this first for any new dataset
- Walkthrough: [`recipes/optional/hana-kg-triple-store/`](../../recipes/optional/hana-kg-triple-store/)
- Template: `references/kg-project/` — planned; tracked as TODO in [`references/README.md`](../../references/README.md).
- HANA docs: https://help.sap.com/docs/hana-cloud-database/sap-hana-cloud-sap-hana-database-sparql-1-1-reference
