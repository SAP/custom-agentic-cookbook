# Datasphere reader

This sample reads one configured Datasphere view through OAuth and OData.
The adapter accepts selected fields, equality filters, and a row limit.
It refreshes expired tokens and retries an unauthorized read once.
It rejects continuation links outside the configured collection.
The sample closes its HTTP client on success and failure.
OAuth and OData responses are limited to one MiB each.
The client ignores ambient proxy settings and stops reading oversized responses.

## Local fixtures

From this directory, run:

```bash
uv sync --frozen
uv run --frozen pytest -q
```

The tests cover both endpoint shapes, pagination, string escaping, token expiry, errors, and closed connections.
They also exercise the example, MCP input bounds, service startup and discovery,
safe backend failure, and process cleanup.
They use synthetic OAuth responses and OData records.
They do not prove access to a real Datasphere tenant.

## Tenant configuration

Load the following variables from your approved secret store into the process environment.
Do not put credentials in commands, Git, tool arguments, or logs.

| Variable | Meaning |
| --- | --- |
| BDC_ODATA_BASE_URL | Shape A: service URL that ends in the space. Shape B: base URL that ends in relational. |
| BDC_SHAPE | A for a space service. B for a view service. |
| BDC_SPACE | Space technical name. |
| BDC_VIEW | View technical name. The example requires Region and Revenue fields. |
| BDC_TOKEN_URL | Approved OAuth token endpoint. |
| BDC_CLIENT_ID | OAuth client identifier. |
| BDC_CLIENT_SECRET | OAuth client secret. |

Use the tenant service document to identify the shape.
Shape A reads the view directly under the space service.
Shape B discovers one inner entity set under the view service.
Use the actual tenant endpoint. Do not derive an authentication URL from its region.
The technical user needs read access to the selected deployed view.
HTTPS and certificate validation remain enabled.

After you load the environment, run:

```bash
uv run --frozen python example.py --region EMEA
```

The example prints the region, row count, and revenue total for at most 100 rows.
It rejects missing, malformed, and nonfinite revenue values before printing a total.
Failed reads report a safe error without response records or endpoint addresses.
Compare the result with the same filter in Datasphere before recording real tenant acceptance.
A result at the row limit is bounded and does not claim a complete aggregate.

## MCP interface

Start the optional MCP service from this directory:

```bash
uv run --frozen python mcp_server.py
```

The read_region_revenue tool accepts a region and a limit from 1 to 50.
It receives no endpoint, credentials, or raw OData filter from a model.
Stop the process with Ctrl+C after the test.
This sample creates no tenant objects and requires no database cleanup.
A deployed A2A integration and real Datasphere acceptance remain separate checkpoints.

## Transport encoding

The reader requests identity encoding and rejects compressed OAuth and OData responses before it reads their bodies.
This rule preserves the one MiB response limit before decoding.


## Optional A2A consumer

The separate [revenue A2A guide](A2A.md) adds a deterministic, bounded consumer of this MCP tool.
Its public optional dependencies, local message and cross-process fixture tests are checked in.
Those fixtures prove local A2A/MCP business, failure, recovery and owned process cleanup only.
Real Datasphere access and deployed integration remain pending.

## Optional synthetic validation image

The [validation image guide](validation-image/README.md) packages the reader and
optional A2A consumer for synthetic loopback tests on Python 3.12, Linux amd64.
The default command starts the fixture. This image omits unused SQLite and NIS
modules and providers; it supplies the HTTP/OAuth/OData sample runtime only.
The normal `uv` commands and HTTPS tenant configuration above remain the
supported reader path. A local fixture does not prove deployed or tenant access.
