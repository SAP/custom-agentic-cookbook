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
status: partial
last-validated: 2026-07-06
---

# HANA KG / Triple Store — knowledge graph for agents

This guide prepares RDF and describes HANA named-graph operations.
The checked-in [HANA retrieval sample](../../../samples/hana-retrieval-agent/)
provides a registered read-only graph tool and an A2A application.
Its controlled fixtures verify primary-contact answers with source references.
Actual HANA retrieval from the deployed application and live cleanup remain pending.

Use synthetic documents or reviewed business exports. S/4 connectivity is
optional. [Regional preflight](../region-preflight/) checks service availability;
confirm knowledge graph engine enablement and permissions on the selected tenant
separately. Catalog availability does not prove tenant enablement.

## Prerequisites

- An enabled HANA Cloud knowledge graph engine and approved TLS connection
- A database user with `SPARQL UPDATE` and `SPARQL QUERY` system privileges
- Graph-specific privileges when accessing another user's named graph
- Reviewed source data and entity/relationship definitions

Keep credentials outside Git and chat. See SAP's
[permissions workflow](https://help.sap.com/docs/HANA_CLOUD_DATABASE/5c3488c559d64d2c8b4f331a1d9b281a/89e0501693974811a0cb3d0fb48ff5f7.html?version=2026_3_QRC).

## Step 1 — Prepare and parse RDF

Use [sap-hana-data-prep](../../../skills/sap-hana-data-prep/) to produce
`prepared/entity_mapping.yaml`, `prepared/triples.ttl`, and
`prepared/ingestion-contract.yaml` with `target_shape: hana_triple`.
Resolve `open_questions` and `pii_handling` before loading.

Turtle supports prefixes, semicolons, multiline literals, and blank nodes.
Removing prefix lines or selecting dot-terminated lines corrupts valid RDF.
Parse the complete local file with [RDFLib](https://rdflib.readthedocs.io/en/stable/intro_to_parsing/):

```bash
uv run --with rdflib==7.6.0 python - <<'PY'
from pathlib import Path
from rdflib import Graph

data = Graph().parse(data=Path("prepared/triples.ttl").read_text(encoding="utf-8"), format="turtle")
assert len(data) > 0, "no RDF triples"
data.serialize(destination="prepared/triples.nt", format="nt")
print(f"parsed triples: {len(data)}")
PY
```

This local check creates no HANA objects. Review the count and source references.

## Step 2 — Create a new named graph

RDF named graphs are not SQL property-graph workspaces.
Use [SPARQL_EXECUTE](https://help.sap.com/docs/HANA_CLOUD_DATABASE/c4deb9de973544cbaf43cd88f85203f4/8b16f906aa9b492382260a824e517f89.html?version=2026_3_QRC),
not `CREATE GRAPH IF NOT EXISTS ... WORKSPACE`.
Select a new graph IRI and record ownership. Replace the example IRI
`urn:cookbook:kg:test-001` consistently with that approved new IRI.
After creation approval, run this in the HANA SQL console:

```sql
CALL SPARQL_EXECUTE('CREATE GRAPH <urn:cookbook:kg:test-001>', '', ?, ?);
```

Do not add `SILENT`: fail if the graph already exists. Check permissions,
syntax, and tenant configuration before retrying a failed command.

## Step 3 — Load reviewed triples

After insertion approval, this synthetic fixture adds exactly four triples
into only the new graph:

```sql
CALL SPARQL_EXECUTE('
PREFIX ex: <https://example.com/cookbook/customer#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
INSERT DATA { GRAPH <urn:cookbook:kg:test-001> {
  ex:acme a ex:Customer ; ex:hasPrimaryContact ex:alice .
  ex:alice a ex:Contact ; rdfs:label "Alice Example" .
} }', '', ?, ?);
```

For a prepared dataset, use reviewed RDF with its prefixes, or parsed N-Triples.
This guide does not supply a general loader. Do not split connected blank-node
triples across requests: blank-node labels are scoped to the request.
Choose batch sizes from actual tenant/client evidence. Larger datasets can use
[IMPORT FROM RDF FILE](https://help.sap.com/docs/HANA_CLOUD_DATABASE/c4deb9de973544cbaf43cd88f85203f4/f07faf9748d549dda8c70ca0b5d2ba20.html?version=2026_3_QRC),
which requires supported storage and extra import permissions. A local file
path is not a HANA Cloud storage URL.

## Step 4 — Wire the graph_query tool

The [retrieval sample](../../../samples/hana-retrieval-agent/) provides a bounded read-only graph tool.
Use it for the primary-contact fixture or implement a separately reviewed business query. Use reviewed query templates and
bounded inputs. Unrestricted model-generated SPARQL can reach other graphs
or perform updates. Keep credentials, cursors, and raw errors outside model
inputs and public replies. See [sap-hana-triple](../../../skills/sap-hana-triple/).

## Verify it works

Run these fixture checks in the SQL console:

```sql
CALL SPARQL_EXECUTE('
SELECT (COUNT(*) AS ?n) FROM <urn:cookbook:kg:test-001> WHERE { ?s ?p ?o }
', 'Accept: application/sparql-results+json', ?, ?);

CALL SPARQL_EXECUTE('
PREFIX ex: <https://example.com/cookbook/customer#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?contactLabel FROM <urn:cookbook:kg:test-001>
WHERE { ex:acme ex:hasPrimaryContact ?contact . ?contact rdfs:label ?contactLabel }
', 'Accept: application/sparql-results+json', ?, ?);
```

Require count 4 and `Alice Example` in the JSON bindings. Other prepared data
needs its exact reviewed count and a known relationship result.
`SPARQL_EXECUTE` returns a response string, not ordinary rows for `fetchone()`.
The [Python interface](https://help.sap.com/docs/HANA_CLOUD_DATABASE/5c3488c559d64d2c8b4f331a1d9b281a/93c683782a4347c1afff5871b83431b9.html?version=2026_3_QRC)
uses `cursor.callproc("SPARQL_EXECUTE", (request, headers, "?", None))`.
Response index 2 is the result; index 3 is response metadata.
Close cursors and connections in `finally` blocks in client applications.

Scope queries explicitly: HANA's [FROM behavior](https://help.sap.com/docs/HANA_CLOUD_DATABASE/c4deb9de973544cbaf43cd88f85203f4/d0e5043bc27a46d0a238f11db95c70c5.html?version=2026_3_QRC)
can merge all available graphs when no dataset is specified. A scoped query
alone is not an application authorization boundary.

Complete the agent recipe with a real A2A message through the registered graph
tool and verify its source-backed relationship answer. Record HANA, application,
deployment, and cleanup proof separately. Guide repairs and local RDF checks
do not satisfy the full acceptance criterion.

## Cleanup

After removal approval, drop only the new graph created for this test:

```sql
CALL SPARQL_EXECUTE('DROP GRAPH <urn:cookbook:kg:test-001>', '', ?, ?);
SELECT * FROM SPARQL_TABLE('
  SELECT (EXISTS { GRAPH ?g { } FILTER(?g = <urn:cookbook:kg:test-001>) } AS ?graphExists) WHERE { }
');
```

Require `graphExists` to be false. The graph-existence pattern is documented in
[DROP GRAPH](https://help.sap.com/docs/HANA_CLOUD_DATABASE/c4deb9de973544cbaf43cd88f85203f4/8555e1778fa64950bd90d85e89543c9d.html?version=2026_3_QRC).
Preserve existing graphs, users, and services. Do not use `DROP ALL`, `DROP NAMED`,
or a broad clear operation. No live HANA or cleanup result is claimed here.

## Cross-references

- [Data preparation](../../../skills/sap-hana-data-prep/)
- [Triple-store patterns](../../../skills/sap-hana-triple/)
- [Vector guide](../hana-vector-store/) — separate integration and tests required
- [Regional service context](../../../skills/sap-sovereign-regions/references/btp-regional-availability.md)

## Checked-in retrieval runtime

The separate [HANA retrieval sample](../../../samples/hana-retrieval-agent/) contains bounded vector and RDF tools.
Its graph tool accepts one entity identifier and a result limit.
It uses the configured named graph and a fixed read-only query.
The A2A answer includes the contact and its source reference.
The sample includes a chart with a ClusterIP Service, loopback smoke, and exact named-graph cleanup.
Controlled fixture tests pass. Live HANA retrieval remains pending until the approved service exists.

The SQL walkthrough uses a four-triple customer/contact example in `urn:cookbook:kg:test-001`. The retrieval sample uses its own two-triple fixture, entity IRIs, and a graph name under `urn:cookbook:graph:test-`. Prepare the sample with its management command and configure that exact graph; the walkthrough fixture does not supply the sample's relationship and source fields.
