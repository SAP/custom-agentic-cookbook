"""Exercise the advertised example and MCP interface over the real adapter."""

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from mcp import ClientSession
from mcp.client.sse import sse_client

import example
import mcp_server
from datasphere import DatasphereReader, ReaderError


@pytest.fixture
def adapter(monkeypatch):
    instances, requests, records = [], [], [{"Region": "EMEA", "Revenue": "12.50"}]
    for name, value in {
        "BDC_ODATA_BASE_URL": "https://tenant.example/SPACE",
        "BDC_SPACE": "SPACE",
        "BDC_VIEW": "SALES",
        "BDC_SHAPE": "A",
        "BDC_TOKEN_URL": "https://auth.example/token",
        "BDC_CLIENT_ID": "fixture-id",
        "BDC_CLIENT_SECRET": "fixture-secret",
    }.items():
        monkeypatch.setenv(name, value)

    def handler(request):
        requests.append(request)
        if request.url.host == "auth.example":
            return httpx.Response(200, json={"access_token": "fixture-token", "expires_in": 60})
        return httpx.Response(200, json={"value": records})

    def factory(**kwargs):
        client = DatasphereReader(**kwargs, transport=httpx.MockTransport(handler))
        instances.append(client)
        return client

    monkeypatch.setattr(example, "DatasphereReader", factory)
    monkeypatch.setattr(mcp_server, "DatasphereReader", factory)
    yield instances, requests, records
    assert all(client.http.is_closed for client in instances)


async def test_example_aggregates_selected_rows_and_closes_client(adapter, capsys):
    _, requests, records = adapter
    records.append({"Region": "EMEA", "Revenue": 7.5, "PrivateExtra": "must not be returned"})
    await example.run("EMEA")
    assert json.loads(capsys.readouterr().out) == {
        "region": "EMEA",
        "row_count": 2,
        "revenue": 20.0,
    }
    assert requests[-1].url.params["$top"] == "100"
    assert requests[-1].url.params["$filter"] == "Region eq 'EMEA'"


@pytest.mark.parametrize("revenue", [None, "private malformed value", "NaN", "Infinity"])
async def test_example_rejects_invalid_revenue_without_leaking_records(adapter, capsys, revenue):
    adapter[2][0]["Revenue"] = revenue
    with pytest.raises(ReaderError, match="invalid revenue") as error:
        await example.run("EMEA")
    assert "private" not in str(error.value)
    assert capsys.readouterr().out == ""


async def test_mcp_schema_and_call_use_bounded_adapter_contract(adapter):
    _, requests, records = adapter
    records[0]["PrivateExtra"] = "hidden"
    tools = await mcp_server.mcp.list_tools()
    assert [tool.name for tool in tools] == ["read_region_revenue"]
    assert set(tools[0].inputSchema["properties"]) == {"region", "limit"}
    result = await mcp_server.mcp.call_tool("read_region_revenue", {"region": "EMEA", "limit": 1})
    assert len(result) == 1
    assert json.loads(result[0].text) == {
        "rows": [{"Region": "EMEA", "Revenue": "12.50"}],
        "source": "configured Datasphere revenue view",
        "limit": 1,
    }
    assert requests[-1].url.params["$top"] == "1"
    assert requests[-1].url.params["$select"] == "Region,Revenue"


@pytest.mark.parametrize("region,limit", [("", 1), ("x" * 129, 1), ("EMEA", 0), ("EMEA", 51)])
async def test_invalid_mcp_inputs_do_not_contact_backend(adapter, region, limit):
    with pytest.raises(Exception, match="region must contain"):
        await mcp_server.mcp.call_tool("read_region_revenue", {"region": region, "limit": limit})
    assert adapter[0] == []
    assert adapter[1] == []


@pytest.mark.parametrize("field", ["BDC_ODATA_BASE_URL", "BDC_TOKEN_URL"])
async def test_mcp_malformed_endpoint_error_does_not_disclose_authority(
    adapter, monkeypatch, caplog, field
):
    monkeypatch.setenv(
        field, "https://fixture-user:fixture-secret@private-tenant.example\uff0fSPACE"
    )
    with pytest.raises(Exception) as error:
        await mcp_server.mcp.call_tool("read_region_revenue", {"region": "EMEA", "limit": 1})
    visible_error = str(error.value) + caplog.text
    assert "endpoint is malformed" in visible_error
    assert not any(
        value in visible_error for value in ["fixture-user", "fixture-secret", "private-tenant"]
    )
    assert adapter[0] == []
    assert adapter[1] == []


def test_example_cli_reports_safe_failure(monkeypatch, capsys):
    async def failed(_):
        raise ReaderError("private fixture error")

    monkeypatch.setattr(example, "run", failed)
    monkeypatch.setattr(sys, "argv", ["example.py", "--region", "EMEA"])
    assert example.main() == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == ("Datasphere example failed. Check configuration and the selected view.\n")


async def test_documented_mcp_process_discovers_tools_and_returns_safe_backend_failure():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    # Discovery requires no tenant. The closed TLS loopback endpoint makes an
    # actual tool call fail without contacting an external service.
    env = {
        **os.environ,
        "MCP_HOST": "127.0.0.1",
        "MCP_PORT": str(port),
        "BDC_ODATA_BASE_URL": "https://127.0.0.1:1/SPACE",
        "BDC_TOKEN_URL": "https://127.0.0.1:1/token",
        "BDC_SPACE": "SPACE",
        "BDC_VIEW": "SALES",
        "BDC_SHAPE": "A",
        "BDC_CLIENT_ID": "fixture-id",
        "BDC_CLIENT_SECRET": "fixture-secret",
    }
    proc = subprocess.Popen(
        [sys.executable, "mcp_server.py"],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            assert proc.poll() is None, "MCP child exited before startup"
            with socket.socket() as sock:
                if sock.connect_ex(("127.0.0.1", port)) == 0:
                    break
            time.sleep(0.05)
        else:
            pytest.fail("MCP startup timed out")
        async with (
            sse_client(f"http://127.0.0.1:{port}/sse") as streams,
            ClientSession(*streams) as session,
        ):
            await session.initialize()
            assert [tool.name for tool in (await session.list_tools()).tools] == [
                "read_region_revenue"
            ]
            invalid = await session.call_tool(
                "read_region_revenue", {"region": "EMEA", "limit": 51}
            )
            assert invalid.isError
            failed = await session.call_tool("read_region_revenue", {"region": "EMEA", "limit": 1})
            assert failed.isError
            text = "\n".join(part.text for part in failed.content)
            assert "Datasphere network request failed" in text
            assert not any(value in text for value in ["fixture-secret", "127.0.0.1", "token"])
    finally:
        proc.terminate()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(5)
        assert proc.poll() is not None
        with socket.socket() as sock:
            assert sock.connect_ex(("127.0.0.1", port)) != 0
