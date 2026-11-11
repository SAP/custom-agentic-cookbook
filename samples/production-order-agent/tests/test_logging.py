"""Direct MCP callers must not receive backend details in transport diagnostics."""

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


@pytest.mark.parametrize("status", [200, 503])
@pytest.mark.parametrize("tool", ["get_production_order_status", "get_production_order_operations"])
def test_completed_direct_mcp_request_hides_transport_details(status, tool):
    script = textwrap.dedent("""\
        import asyncio, json, logging, os, sys, threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from production_order_agent import mcp_server

        status, tool = int(sys.argv[1]), sys.argv[2]
        requests = []
        class Backend(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass
            def do_GET(self):
                assert self.headers['APIKey'] == 'fixture-api-key'
                requests.append(self.path)
                body = json.dumps({'value': [{'StatusName': 'Fixture Released'}]}).encode()
                self.send_response(status)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = ThreadingHTTPServer(('127.0.0.1', 0), Backend)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        os.environ.update({
            'DATA_MODE': 's4', 'S4_API_KEY': 'fixture-api-key',
            'S4_BASE_URL': f'http://127.0.0.1:{server.server_port}/fixture-service',
        })
        logging.getLogger().handlers = [logging.StreamHandler(sys.stderr)]
        logging.getLogger().setLevel(logging.DEBUG)
        service = mcp_server.create_mcp_server()
        logging.getLogger('cookbook.application').info('application-log-visible')

        async def call():
            try:
                result = await service.call_tool(tool, {'manufacturing_order': '7654321'})
                return {'record_returned': 'Fixture Released' in str(result)}
            except Exception as error:
                return {'error': str(error)}
        try:
            result = asyncio.run(call())
        finally:
            server.shutdown()
            server.server_close()
            worker.join(5)
            assert not worker.is_alive()
        print(json.dumps({'requests': len(requests), **result}))
        """)
    process = subprocess.run(
        [sys.executable, "-B", "-c", script, str(status), tool],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    )
    result = json.loads(process.stdout)
    assert result["requests"] == 1
    assert "application-log-visible" in process.stderr
    if status == 200:
        assert result["record_returned"]
    else:
        assert "HTTP 503" in result["error"]
        assert "fixture-" not in result["error"]
    for marker in [
        "fixture-service",
        "fixture-api-key",
        "7654321",
        "HTTP Request:",
        "connect_tcp.started",
        "send_request_headers.started",
    ]:
        assert marker not in process.stderr
