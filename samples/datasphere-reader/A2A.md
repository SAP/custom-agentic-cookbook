# Optional revenue A2A integration

The local reader, example and MCP service work without this extra.
This separate deterministic consumer calls only `read_region_revenue(region, limit=50)`.
It uses public A2A v1.0 and MCP dependencies. It needs no model or AI Core.
It accepts the command `revenue <region>` with a region of 1-128 characters.
It validates the returned fields and region before computing a decimal revenue total.
Each amount must be finite, at most 1e20 in absolute value and have at most 12 decimal places.
The answer is always bounded to 50 rows and does not claim a complete tenant aggregate.
No currency is inferred from the view.

## Controlled local proof

From this sample directory, run:

```bash
uv sync --frozen --extra a2a
uv run --frozen --extra a2a pytest -q tests a2a_tests
```

The optional cross-process test starts only loopback A2A/MCP processes and a synthetic OAuth/OData fixture.
It proves a completed A2A reply for both endpoint shapes, a safe denied-read failure,
recovery and exact owned process/port cleanup.
Its answer says `synthetic OAuth/OData fixture; no tenant proof`.
The test-only MCP wrapper permits HTTP only for its loopback fixture.
The normal reader and MCP entrypoint keep HTTPS certificate validation enabled.
No Datasphere tenant or BTP resource is contacted or created by this test.

## Use with approved access

First follow [the reader guide](README.md) and verify the selected deployed view.
Load approved credentials only into the MCP process from the runtime secret store.
The A2A process needs only the approved MCP SSE URL, never OAuth credentials or a model endpoint.
Start the reader's documented MCP service in one terminal.
In a separate terminal, from this directory, run:

```bash
uv run --frozen --extra a2a python a2a_server.py
```

The A2A server listens only on `127.0.0.1:8001`.
`PORT` changes its local port; `URL` sets the advertised Agent Card URL.
`MCP_SERVER_URL` defaults to `http://127.0.0.1:8091/sse` and permits only configured HTTPS or loopback HTTP SSE URLs.
`A2A_SOURCE_MODE` defaults to `datasphere`; the `fixture` value labels synthetic local exercises.
A source label describes the configured source, not independent tenant validation.
The MCP request has a ten-second total deadline. Each HTTP response is limited to 65,536
received bytes before SSE buffering and JSON decoding, including structured tool results.
The consumer requests identity encoding and refuses compressed responses before decompression.
Transport logs omit endpoint, session, response and exception details. Failed reads produce
a failed A2A task with a safe message.
The same log policy applies to the first call from an imported application.
The `httpcore` child loggers follow this policy with DEBUG enabled.
The local endpoints have no authentication and use in-memory task state.
Keep this exercise on loopback; public exposure, authentication and CF/Kyma packaging require separate review.

Send a real A2A message:

```bash
curl --fail-with-body http://127.0.0.1:8001/ \
  -H 'Content-Type: application/json' -H 'A2A-Version: 1.0' \
  -d '{"jsonrpc":"2.0","id":"1","method":"SendMessage","params":{"message":{"messageId":"revenue-1","role":"ROLE_USER","parts":[{"text":"revenue EMEA"}]}}}'
```

Require `TASK_STATE_COMPLETED` and a `revenue-summary` artifact with the selected region,
row count, decimal revenue string, source, `limit: 50` and `bounded: true`.
Compare that bounded answer with the same approved source records.
An Agent Card or fixture reply does not prove real Datasphere access or deployed acceptance.

Stop only the A2A and MCP processes that you started with Ctrl+C in their terminals.
Verify that their owned local ports close. This read-only path creates no tenant objects.
Deployed A2A business, failure/recovery and exact cleanup remain separate acceptance gates.

## Optional synthetic validation image

See the [validation image guide](validation-image/README.md) for the optional
Python 3.12, Linux amd64 fixture image. Its default command starts only the
synthetic OAuth/OData fixture on loopback. Start the optional A2A and MCP
processes separately using the commands above and in the reader guide.
SQLite and NIS modules and native providers are omitted.
The image supports this sample's HTTP/OAuth/OData contract. It does not establish
real Datasphere, deployed endpoint or complete Python standard-library support.
