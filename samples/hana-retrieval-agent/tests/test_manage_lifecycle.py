"""Stateful DDL tests for partial test-schema creation and exact RESTRICT cleanup."""

import json

import pytest

from hana_retrieval import manage
from hana_retrieval.fixture import DOCS
from hana_retrieval.repository import RetrievalError

TARGET = "COOKBOOK_TEST_PARTIAL"


class Database:
    def __init__(self):
        self.schemas = {}
        self.connections = []
        self.fail_create_table = False
        self.ignore_schema_drop = False

    def connect(self):
        connection = Connection(self)
        self.connections.append(connection)
        return connection


class Connection:
    def __init__(self, database):
        self.database = database
        self.closed = False
        self.cur = Cursor(database)

    def cursor(self):
        return self.cur

    def commit(self):
        pass

    def close(self):
        self.closed = True


class Cursor:
    def __init__(self, database):
        self.database = database
        self.closed = False
        self.count = None

    def execute(self, statement, parameters=None):
        schemas = self.database.schemas
        if statement == f'CREATE SCHEMA "{TARGET}"':
            if TARGET in schemas:
                raise RuntimeError("schema already exists")
            schemas[TARGET] = {}
        elif statement.startswith(f'CREATE COLUMN TABLE "{TARGET}"."DOCS"'):
            if self.database.fail_create_table:
                self.database.fail_create_table = False
                raise RuntimeError("private driver detail after committed schema DDL")
            schemas[TARGET]["DOCS"] = []
        elif statement.startswith(f'INSERT INTO "{TARGET}"."DOCS"'):
            schemas[TARGET]["DOCS"].append(parameters)
        elif statement == f'SELECT COUNT(*) FROM "{TARGET}"."DOCS"':
            self.count = len(schemas[TARGET]["DOCS"])
        elif (
            statement == "SELECT COUNT(*) FROM SYS.TABLES WHERE SCHEMA_NAME = ? AND TABLE_NAME = ?"
        ):
            schema, table = parameters
            self.count = int(table in schemas.get(schema, {}))
        elif statement == "SELECT COUNT(*) FROM SYS.SCHEMAS WHERE SCHEMA_NAME = ?":
            self.count = int(parameters[0] in schemas)
        elif statement == f'DROP TABLE "{TARGET}"."DOCS"':
            del schemas[TARGET]["DOCS"]
        elif statement == f'DROP SCHEMA "{TARGET}" RESTRICT':
            if schemas[TARGET]:
                raise RuntimeError("RESTRICT prevents deleting unrelated objects")
            if not self.database.ignore_schema_drop:
                del schemas[TARGET]
        else:
            raise AssertionError("unexpected or broader SQL operation")

    def fetchone(self):
        return (self.count,)

    def close(self):
        self.closed = True


@pytest.fixture
def database(monkeypatch):
    database = Database()
    monkeypatch.setattr(manage, "connect_hana", database.connect)
    monkeypatch.setattr(manage, "dimension", lambda: 2)
    monkeypatch.setattr(manage, "embed", lambda *_: [1.0, 0.0])
    yield database
    assert all(conn.closed and conn.cur.closed for conn in database.connections)


def test_partial_prepare_cleanup_allows_fresh_prepare_retry(database, capsys):
    database.fail_create_table = True
    with pytest.raises(RetrievalError):
        manage.manage("vector", "prepare", TARGET)
    assert database.schemas == {TARGET: {}}
    assert capsys.readouterr().out == ""

    manage.manage("vector", "cleanup", TARGET)
    assert database.schemas == {}
    assert json.loads(capsys.readouterr().out) == {
        "removed": "exact vector test table and empty schema"
    }

    manage.manage("vector", "prepare", TARGET)
    assert len(database.schemas[TARGET]["DOCS"]) == len(DOCS)
    assert json.loads(capsys.readouterr().out)["rows"] == len(DOCS)
    manage.manage("vector", "cleanup", TARGET)
    assert database.schemas == {}


@pytest.mark.parametrize("docs_exists", [False, True])
def test_restrict_preserves_unrelated_objects_without_success(database, capsys, docs_exists):
    unrelated = [{"owner": "another application"}]
    database.schemas[TARGET] = {"UNRELATED": unrelated}
    if docs_exists:
        database.schemas[TARGET]["DOCS"] = []
    with pytest.raises(RetrievalError) as error:
        manage.manage("vector", "cleanup", TARGET)
    assert database.schemas[TARGET]["UNRELATED"] == unrelated
    assert error.value.__suppress_context__ is True
    assert "RESTRICT" not in str(error.value)
    assert capsys.readouterr().out == ""


def test_schema_remains_without_docs_never_reports_cleanup_success(database, capsys):
    database.schemas[TARGET] = {"DOCS": []}
    database.ignore_schema_drop = True
    with pytest.raises(RetrievalError):
        manage.manage("vector", "cleanup", TARGET)
    assert database.schemas == {TARGET: {}}
    assert capsys.readouterr().out == ""
