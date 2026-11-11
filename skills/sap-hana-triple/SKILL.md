---
name: sap-hana-triple
description: Use this skill when building knowledge graphs on SAP HANA Cloud's Triple Store — RDF named graphs, reviewed ingestion, scoped SPARQL queries, and public agent integration boundaries.
---

# SAP HANA Cloud Triple Store — RDF named graphs

Model relationships as RDF triples and query with SPARQL.
RDF named graphs are not SQL property-graph workspaces.
The [recipe](../../recipes/optional/hana-kg-triple-store/) provides named-graph
creation, a synthetic fixture, verification, and exact test-graph cleanup.
Each live change needs approval for the selected new graph.

## Modeling — ontology in Turtle

```turtle
@prefix : <https://example.com/cookbook/customer#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

:Customer a rdfs:Class .
:Contact a rdfs:Class .
:hasPrimaryContact a rdf:Property ;
    rdfs:domain :Customer ; rdfs:range :Contact .
```

Review ontology changes with the source data model. Use
[sap-hana-data-prep](../sap-hana-data-prep/) to produce entity mapping, complete
Turtle, and an ingestion contract with `target_shape: hana_triple`.
Resolve its data classification, PII handling, and open questions before loading.
Parse complete RDF; do not remove prefixes or split arbitrary Turtle by lines.
Keep connected blank-node data within the same update request.

## HANA procedure and result contract

Use [SPARQL_EXECUTE](https://help.sap.com/docs/HANA_CLOUD_DATABASE/c4deb9de973544cbaf43cd88f85203f4/8b16f906aa9b492382260a824e517f89.html?version=2026_3_QRC),
not `cursor.execute("SPARQL ...")`. For an already approved TLS connection,
the documented Python call returns a result string at index 2 and metadata
at index 3:

```python
import json

try:
    cur = conn.cursor()
    try:
        response = cur.callproc(
            "SPARQL_EXECUTE",
            (
                "SELECT (COUNT(*) AS ?n) FROM <urn:cookbook:kg:test-001> WHERE { ?s ?p ?o }",
                "Accept: application/sparql-results+json",
                "?",
                None,
            ),
        )
        result = json.loads(response[2])
        assert int(result["results"]["bindings"][0]["n"]["value"]) == 4
    finally:
        cur.close()
finally:
    conn.close()
```

The caller creates `conn` for this check; the snippet closes it on success or
failure. It does not supply a connection or an agent adapter. Replace the example graph IRI with
the approved graph. See SAP's [Python interface](https://help.sap.com/docs/HANA_CLOUD_DATABASE/5c3488c559d64d2c8b4f331a1d9b281a/93c683782a4347c1afff5871b83431b9.html?version=2026_3_QRC).

## Query and permissions

Use reviewed read-only queries and an explicit `FROM <approved-graph>` dataset.
HANA's [FROM clause](https://help.sap.com/docs/HANA_CLOUD_DATABASE/c4deb9de973544cbaf43cd88f85203f4/d0e5043bc27a46d0a238f11db95c70c5.html?version=2026_3_QRC)
can merge all available graphs when no dataset is specified.
Database privileges and named-graph ownership both matter; a graph clause does
not restrict arbitrary generated SPARQL or establish an agent authorization boundary.

## Agent-over-KG pattern

Implement and register a narrow read-only tool in the chosen public agent.
Use bounded inputs, reviewed queries, and source references. Keep credentials,
cursors, and raw database errors outside model inputs and public replies.
Unrestricted NL-to-SPARQL generation is not an authorization control.

The separate [retrieval sample](../../samples/hana-retrieval-agent/) now supplies a bounded primary-contact tool.
The full recipe remains partial until a real A2A request calls the graph tool,
returns the expected relationship answer, and deployment and cleanup pass.
The documentation checks do not add those application pieces.

## Hybrid KG + Vector

Hybrid retrieval requires a separate data model, public integration, and tests.
A property-graph annotation table is not an RDF named graph.
Use the [vector guide](../../recipes/optional/hana-vector-store/) only after its
applicable integration is available and tested.

## Verify

Use the recipe's [count and relationship checks](../../recipes/optional/hana-kg-triple-store/#verify-it-works)
and [test-graph cleanup](../../recipes/optional/hana-kg-triple-store/#cleanup).
A nonempty graph alone does not prove a working agent.

## Checked-in retrieval runtime

The separate [HANA retrieval sample](../../samples/hana-retrieval-agent/) contains bounded vector and RDF tools.
Its graph tool accepts one entity identifier and a result limit.
It uses the configured named graph and a fixed read-only query.
The A2A answer includes the contact and its source reference.
The sample includes a chart with a ClusterIP Service, loopback smoke, and exact named-graph cleanup.
Controlled fixture tests pass. Live HANA retrieval remains pending until the approved service exists.
