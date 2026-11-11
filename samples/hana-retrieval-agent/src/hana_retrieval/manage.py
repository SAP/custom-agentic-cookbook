"""Create or remove exact test-owned HANA objects after approval outside this script."""

import argparse
import json

from hana_retrieval.embedding import dimension, embed
from hana_retrieval.fixture import DOCS
from hana_retrieval.repository import GRAPH, SCHEMA, RetrievalError, connect_hana


def manage(kind, action, target):
    if kind not in {"vector", "graph"} or action not in {"prepare", "cleanup"}:
        raise ValueError("kind must be vector or graph and action must be prepare or cleanup")
    if kind == "vector" and (
        not SCHEMA.fullmatch(target) or not target.startswith("COOKBOOK_TEST_")
    ):
        raise ValueError("vector target must be an exact COOKBOOK_TEST_ schema")
    if kind == "graph" and not GRAPH.fullmatch(target):
        raise ValueError("graph target must be an exact urn:cookbook:graph:test- name")
    try:
        result = _perform(kind, action, target)
    except Exception:
        raise RetrievalError("HANA test object operation failed") from None
    print(json.dumps(result))


def _perform(kind, action, target):
    vectors = (
        [embed(row["content"], dimension()) for row in DOCS]
        if kind == "vector" and action == "prepare"
        else []
    )
    conn = connect_hana()
    try:
        cur = conn.cursor()
        try:
            if kind == "vector":
                if action == "prepare":
                    cur.execute(f'CREATE SCHEMA "{target}"')
                    cur.execute(
                        f'CREATE COLUMN TABLE "{target}"."DOCS" ('
                        "ID NVARCHAR(64) PRIMARY KEY, CONTENT NVARCHAR(2000), "
                        "SOURCE NVARCHAR(512), TOPIC NVARCHAR(128), "
                        f"EMBEDDING REAL_VECTOR({dimension()}))"
                    )
                    for row, vector in zip(DOCS, vectors, strict=True):
                        cur.execute(
                            f'INSERT INTO "{target}"."DOCS" VALUES (?, ?, ?, ?, TO_REAL_VECTOR(?))',
                            (
                                row["id"],
                                row["content"],
                                row["source"],
                                row["topic"],
                                json.dumps(vector),
                            ),
                        )
                    conn.commit()
                    cur.execute(f'SELECT COUNT(*) FROM "{target}"."DOCS"')
                    if cur.fetchone()[0] != len(DOCS):
                        raise RetrievalError("HANA vector fixture row count differs")
                    return {
                        "objects": "vector test schema",
                        "rows": len(DOCS),
                        "embedding_model": "text-embedding-3-small",
                        "dimension": dimension(),
                    }
                else:
                    cur.execute(
                        "SELECT COUNT(*) FROM SYS.TABLES WHERE SCHEMA_NAME = ? AND TABLE_NAME = ?",
                        (target, "DOCS"),
                    )
                    if cur.fetchone()[0] != 0:
                        cur.execute(f'DROP TABLE "{target}"."DOCS"')
                    cur.execute(f'DROP SCHEMA "{target}" RESTRICT')
                    cur.execute("SELECT COUNT(*) FROM SYS.SCHEMAS WHERE SCHEMA_NAME = ?", (target,))
                    if cur.fetchone()[0] != 0:
                        raise RetrievalError("HANA vector cleanup left the test schema")
                    return {"removed": "exact vector test table and empty schema"}
            else:
                if action == "prepare":
                    cur.callproc("SPARQL_EXECUTE", (f"CREATE GRAPH <{target}>", "", "?", None))
                    triples = (
                        "<urn:cookbook:entity:customer-42> "
                        "<urn:cookbook:relation:hasPrimaryContact> "
                        "<urn:cookbook:entity:contact-7> . "
                        "<urn:cookbook:entity:customer-42> "
                        "<urn:cookbook:relation:source> "
                        "<https://example.com/source/customer-42> ."
                    )
                    cur.callproc(
                        "SPARQL_EXECUTE",
                        (f"INSERT DATA {{ GRAPH <{target}> {{ {triples} }} }}", "", "?", None),
                    )
                    expected = 2
                else:
                    cur.callproc("SPARQL_EXECUTE", (f"DROP GRAPH <{target}>", "", "?", None))
                    expected = 0
                result = cur.callproc(
                    "SPARQL_EXECUTE",
                    (
                        f"SELECT (COUNT(*) AS ?n) FROM <{target}> WHERE {{ ?s ?p ?o }}",
                        "Accept: application/sparql-results+json",
                        "?",
                        None,
                    ),
                )
                count = int(json.loads(result[2])["results"]["bindings"][0]["n"]["value"])
                if count != expected:
                    raise RetrievalError("HANA graph triple count differs")
                return {"graph_triples": count, "action": action}
        finally:
            cur.close()
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=["vector", "graph"], required=True)
    parser.add_argument("--action", choices=["prepare", "cleanup"], required=True)
    parser.add_argument("--target", required=True)
    args = parser.parse_args()
    manage(args.kind, args.action, args.target)
