"""Completed loopback requests must not disclose transport details in diagnostics."""

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


@pytest.mark.parametrize("status", [200, 403])
def test_completed_mcp_requests_hide_endpoints_and_filters_in_stderr(status):
    script = textwrap.dedent("""\
        import asyncio, json, logging, os, sys, threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        import mcp_server
        from datasphere import DatasphereReader

        status = int(sys.argv[1])
        requests = []
        class Backend(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass
            def respond(self, code, payload):
                requests.append(self.path)
                body = json.dumps(payload).encode()
                self.send_response(code)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            def do_POST(self):
                self.respond(200, {'access_token': 'fixture-token', 'expires_in': 60})
            def do_GET(self):
                self.respond(status, {'value': [{'Region': 'fixture-region', 'Revenue': 12}]})

        server = ThreadingHTTPServer(('127.0.0.1', 0), Backend)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        address = f'http://127.0.0.1:{server.server_port}'
        os.environ.update({
            'BDC_ODATA_BASE_URL': address + '/fixture-data',
            'BDC_TOKEN_URL': address + '/fixture-auth',
            'BDC_SPACE': 'SPACE', 'BDC_VIEW': 'SALES', 'BDC_SHAPE': 'A',
            'BDC_CLIENT_ID': 'fixture-id', 'BDC_CLIENT_SECRET': 'fixture-secret',
        })
        mcp_server.DatasphereReader = lambda **kwargs: DatasphereReader(**kwargs, allow_http=True)
        logging.getLogger().handlers = [logging.StreamHandler(sys.stderr)]
        logging.getLogger().setLevel(logging.DEBUG)
        logging.getLogger('cookbook.application').info('application-log-visible')

        async def call():
            try:
                result = await mcp_server.mcp.call_tool(
                    'read_region_revenue', {'region': 'fixture-region', 'limit': 1}
                )
                return {'reply': json.loads(result[0].text)}
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
        [sys.executable, "-B", "-c", script, str(status)],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    )
    result = json.loads(process.stdout)
    assert result["requests"] == 2
    assert "application-log-visible" in process.stderr
    if status == 200:
        assert result["reply"]["rows"] == [{"Region": "fixture-region", "Revenue": 12}]
    else:
        assert "HTTP 403" in result["error"]
        assert "fixture-" not in result["error"]
    for marker in [
        "fixture-auth",
        "fixture-data",
        "fixture-region",
        "fixture-secret",
        "fixture-token",
        "HTTP Request:",
        "connect_tcp.started",
        "send_request_headers.started",
    ]:
        assert marker not in process.stderr
