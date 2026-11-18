import json

import pytest

from hana_retrieval.repository import HanaRepository, RetrievalError, validate_vector


class Cursor:
    def __init__(self, fail=False):
        self.closed = False
        self.fail = fail
        self.params = None

    def execute(self, sql, params):
        self.sql, self.params = sql, params
        if self.fail:
            raise RuntimeError("private database response")

    def fetchall(self):
        return [
            ("doc-1", "Late assembly", "https://example.com/source/doc-1", "manufacturing", 0.9)
        ]

    def callproc(self, name, args):
        self.sql, self.params = name, args
        if self.fail:
            raise RuntimeError("private database response")
        return (
            args[0],
            args[1],
            json.dumps(
                {
                    "results": {
                        "bindings": [
                            {
                                "contact": {"value": "urn:cookbook:entity:contact-7"},
                                "source": {"value": "https://example.com/source/customer-42"},
                            }
                        ]
                    }
                }
            ),
            None,
        )

    def close(self):
        self.closed = True


class Connection:
    def __init__(self, fail=False):
        self.cur = Cursor(fail)
        self.closed = False

    def cursor(self):
        return self.cur

    def close(self):
        self.closed = True


def test_vector_filter_and_bound_inputs_and_cleanup():
    connection = Connection()
    repo = HanaRepository(
        "COOKBOOK_TEST_VECTOR01",
        "urn:cookbook:graph:test-graph01",
        connect=lambda: connection,
        dimension=3,
    )
    rows = repo.vector([1.0, 0.0, 0.0], "manufacturing", 2)
    assert rows[0]["source"] == "https://example.com/source/doc-1"
    assert "WHERE TOPIC = ?" in connection.cur.sql
    assert connection.cur.params == ("[1.0,0.0,0.0]", "manufacturing", 2)
    assert connection.closed and connection.cur.closed


def test_graph_query_is_read_only_and_scoped_and_sources_survive():
    connection = Connection()
    repo = HanaRepository(
        "COOKBOOK_TEST_VECTOR01",
        "urn:cookbook:graph:test-graph01",
        connect=lambda: connection,
        dimension=3,
    )
    rows = repo.graph("customer-42", 2)
    assert rows == [
        {
            "contact": "urn:cookbook:entity:contact-7",
            "source": "https://example.com/source/customer-42",
        }
    ]
    assert "FROM <urn:cookbook:graph:test-graph01>" in connection.cur.params[0]
    assert "LIMIT 2" in connection.cur.params[0]
    assert connection.closed and connection.cur.closed


@pytest.mark.parametrize("mode", ["vector", "graph"])
def test_failures_close_connections_and_hide_database_details(mode):
    connection = Connection(fail=True)
    repo = HanaRepository(
        "COOKBOOK_TEST_VECTOR01",
        "urn:cookbook:graph:test-graph01",
        connect=lambda: connection,
        dimension=3,
    )
    with pytest.raises(RetrievalError) as exc:
        if mode == "vector":
            repo.vector([1.0, 0.0, 0.0], "manufacturing", 1)
        else:
            repo.graph("customer-42", 1)
    assert "private" not in str(exc.value)
    assert connection.closed and connection.cur.closed


@pytest.mark.parametrize(
    "vector", [[], [float("nan"), 0, 1], [float("inf"), 0, 1], [1, 2], [True, 0, 1]]
)
def test_invalid_embedding_is_rejected(vector):
    with pytest.raises(ValueError):
        validate_vector(vector, 3)


@pytest.mark.parametrize("subject", ["", "x> SERVICE <evil", "x" * 65, "../another-graph"])
def test_graph_subject_injection_is_rejected_without_connection(subject):
    repo = HanaRepository(
        "COOKBOOK_TEST_VECTOR01",
        "urn:cookbook:graph:test-graph01",
        connect=lambda: pytest.fail("must not connect"),
        dimension=3,
    )
    with pytest.raises(ValueError):
        repo.graph(subject, 2)


@pytest.mark.parametrize("mode", ["vector", "graph"])
@pytest.mark.parametrize("failed_close", ["cursor", "connection"])
def test_cleanup_failures_are_safe_and_attempt_both_closes(mode, failed_close):
    connection = Connection()

    def fail_cursor():
        connection.cur.closed = True
        raise RuntimeError("private driver credential-canary")

    def fail_connection():
        connection.closed = True
        raise RuntimeError("private driver credential-canary")

    if failed_close == "cursor":
        connection.cur.close = fail_cursor
    else:
        connection.close = fail_connection
    repo = HanaRepository(
        "COOKBOOK_TEST_VECTOR01",
        "urn:cookbook:graph:test-graph01",
        connect=lambda: connection,
        dimension=3,
    )
    with pytest.raises(RetrievalError, match="cleanup failed") as error:
        if mode == "vector":
            repo.vector([1.0, 0.0, 0.0], "manufacturing", 1)
        else:
            repo.graph("customer-42", 1)
    assert connection.closed and connection.cur.closed
    assert "credential-canary" not in str(error.value)
    assert error.value.__suppress_context__ is True
