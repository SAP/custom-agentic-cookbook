"""Read-only HANA vector and RDF adapters with fixed query shapes."""

from __future__ import annotations

import json
import math
import os
import re
from contextlib import contextmanager

SCHEMA = re.compile(r"[A-Z][A-Z0-9_]{0,63}\Z")
GRAPH = re.compile(r"urn:cookbook:graph:test-[a-z0-9-]{1,48}\Z")
SUBJECT = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}\Z")


class RetrievalError(RuntimeError):
    pass


def validate_vector(vector, dimension):
    if not isinstance(vector, list) or len(vector) != dimension:
        raise ValueError("embedding dimension does not match the configured dimension")
    if any(
        isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value)
        for value in vector
    ):
        raise ValueError("embedding must contain finite numbers")
    if not any(vector):
        raise ValueError("embedding must have nonzero length")
    return vector


def limit_value(limit):
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 20:
        raise ValueError("limit must be 1-20")
    return limit


def connect_hana():
    try:
        from hdbcli import dbapi

        return dbapi.connect(
            address=os.environ["HANA_HOST"],
            port=int(os.environ.get("HANA_PORT", "443")),
            user=os.environ["HANA_USER"],
            password=os.environ["HANA_PASSWORD"],
            encrypt=True,
            sslValidateCertificate=True,
            connectTimeout=15,
        )
    except Exception:
        raise RetrievalError("HANA connection failed") from None


class HanaRepository:
    def __init__(self, schema, graph, *, connect=connect_hana, dimension):
        if not SCHEMA.fullmatch(schema) or not GRAPH.fullmatch(graph):
            raise ValueError("invalid schema or test graph name")
        if not isinstance(dimension, int) or not 1 <= dimension <= 4096:
            raise ValueError("embedding dimension must be 1-4096")
        self.schema, self.graph_name, self.connect, self.dimension = (
            schema,
            graph,
            connect,
            dimension,
        )

    @contextmanager
    def cursor(self):
        conn, cursor = None, None
        try:
            conn = self.connect()
            cursor = conn.cursor()
            yield cursor
        except Exception:
            raise RetrievalError("HANA retrieval failed") from None
        finally:
            cleanup_failed = False
            for resource in (cursor, conn):
                if resource is not None:
                    try:
                        resource.close()
                    except Exception:
                        cleanup_failed = True
            if cleanup_failed:
                raise RetrievalError("HANA connection cleanup failed") from None

    def vector(self, embedding, topic, limit=5):
        validate_vector(embedding, self.dimension)
        limit_value(limit)
        if not isinstance(topic, str) or not 1 <= len(topic) <= 128:
            raise ValueError("topic must contain 1-128 characters")
        sql = (
            "SELECT ID, CONTENT, SOURCE, TOPIC, "
            "COSINE_SIMILARITY(EMBEDDING, TO_REAL_VECTOR(?)) AS SCORE "
            f'FROM "{self.schema}"."DOCS" WHERE TOPIC = ? ORDER BY SCORE DESC LIMIT ?'
        )
        with self.cursor() as cur:
            cur.execute(sql, (json.dumps(embedding, separators=(",", ":")), topic, limit))
            rows = cur.fetchall()
        return [
            dict(zip(["id", "content", "source", "topic", "score"], row, strict=True))
            for row in rows
        ]

    def graph(self, subject, limit=5):
        limit_value(limit)
        if not isinstance(subject, str) or not SUBJECT.fullmatch(subject):
            raise ValueError("subject must be a bounded entity identifier")
        query = (
            f"SELECT ?contact ?source FROM <{self.graph_name}> WHERE {{ "
            f"<urn:cookbook:entity:{subject}> "
            "<urn:cookbook:relation:hasPrimaryContact> ?contact . "
            f"<urn:cookbook:entity:{subject}> "
            f"<urn:cookbook:relation:source> ?source . }} LIMIT {limit}"
        )
        with self.cursor() as cur:
            response = cur.callproc(
                "SPARQL_EXECUTE", (query, "Accept: application/sparql-results+json", "?", None)
            )
            try:
                bindings = json.loads(response[2])["results"]["bindings"]
                rows = [
                    {"contact": row["contact"]["value"], "source": row["source"]["value"]}
                    for row in bindings
                ]
            except (ValueError, KeyError, TypeError, IndexError):
                raise RetrievalError("HANA returned malformed graph results") from None
        return rows
