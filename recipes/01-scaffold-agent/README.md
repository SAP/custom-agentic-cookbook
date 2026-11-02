---
title: "Run a local production-order agent"
sap-services: []
complexity: recipe
last-validated: 2026-10-22
validation-status: "Local and Docker Compose mock A2A-to-MCP flow passed on macOS. No BTP or live backend proof."
---

# 01 · Run your agent locally

This recipe starts the checked-in Python production-order agent. It answers a
production planner with mock order status and operations. No BTP account,
model endpoint, or credentials are required.

A2A carries messages between clients and agents. MCP connects the agent to its
business tools. This sample uses A2A v1.0 and two MCP tools.

The input is a clean Cookbook clone and the tools listed below. The output is
the production-order agent at `http://127.0.0.1:8000` with a working MCP server.
The reply for order `1000000` completes this local checkpoint.

## When to use it

Use this recipe to learn the agent-to-tool flow before selecting a model or
connecting business data. The checked-in starter works from a terminal or any
coding harness. It does not require a scaffold plugin or MCP harness driver.

This path uses Python and an in-memory task store. Start one agent process.
Task state disappears when that process stops. The protocol-only
[minimal sample](../../samples/fde-a2a-minimal/) remains a separate example.

## Prerequisites

Install Python 3.12 or newer, below Python 3.15. Install
[`uv`](https://docs.astral.sh/uv/getting-started/installation/).
Make sure that local ports `8000` and `8090` are available. Docker with Compose
is required only for the container path.

Use macOS or Linux for this tested path. On Windows, use a Linux environment
and these same shell commands. Native Windows behavior is outside this proof.

Clone the Cookbook:

```bash
git clone https://github.com/SAP/custom-agentic-cookbook.git
cd custom-agentic-cookbook
```

## Scaffold

Use the public [production-order starter](../../samples/production-order-agent/)
as the project. No code generation is required.

From the Cookbook root, install the locked sample dependencies:

```bash
cd samples/production-order-agent
uv sync --frozen --group dev
```

If you adapt the starter, keep the tool names and A2A protocol unchanged until
the smoke tests pass. Toolkit generation and deployment automation are outside
this recipe's tested scope.

## Configure

Keep `DATA_MODE=mock` and `LLM_PROVIDER=mock` for this checkpoint. The two tools
return synthetic records for order `1000000`. The agent calculates its summary
from those records. No model generates this baseline reply.

In a terminal at `samples/production-order-agent`, start the MCP server:

```bash
DATA_MODE=mock MCP_HOST=127.0.0.1 MCP_PORT=8090 \
  uv run --frozen python -m production_order_agent.mcp_server
```

In a second terminal at the same directory, start the A2A agent:

```bash
HOST=127.0.0.1 PORT=8000 URL=http://127.0.0.1:8000 \
MCP_SERVER_URL=http://127.0.0.1:8090/sse LLM_PROVIDER=mock \
  uv run --frozen python -m production_order_agent
```

Both endpoints remain on your workstation. Neither endpoint provides
application authentication. Do not expose them to other users or networks.

## Deploy

For an optional local container run, stop the two terminal processes first.
Keep the same working directory. Start the two Compose services in mock mode:

```bash
DATA_MODE=mock LLM_PROVIDER=mock docker compose up --build
```

Compose binds both ports to `127.0.0.1`. The agent calls the MCP service over
the Compose network. Both containers run as UID/GID `10001`.

BTP deployment is a separate checkpoint. The
[deployment recipe](../02-deploy-btp/) still contains paths that need separate
support and live evidence. Do not treat local container proof as BTP proof.

## Verify it works

In a third terminal at `samples/production-order-agent`, list the MCP tools:

```bash
uv run --frozen python scripts/smoke_mcp.py
```

The result contains exactly `get_production_order_status` and
`get_production_order_operations`.

Send a real A2A message and assert its business reply:

```bash
uv run --frozen python scripts/smoke_a2a.py
```

The command asks why production order `1000000` is delayed. It requires a
completed task with both status records and both operation numbers. The reply
shows `Released`, `Partially Confirmed`, `0010`, and `0020`. Operation `0020`
has a past scheduled end date and remains unconfirmed, so the reply reports a
potential delay.

A successful Agent Card request alone does not complete this checkpoint.
The smoke command exits with an error if the A2A task fails or the expected
business records are missing. It uses mock order `1000000`, so use it only
with `DATA_MODE=mock` and `LLM_PROVIDER=mock`.

If you use different local ports, pass both explicit URLs:

```bash
uv run --frozen python scripts/smoke_mcp.py --server-url http://127.0.0.1:8091/sse
uv run --frozen python scripts/smoke_a2a.py --base-url http://127.0.0.1:8001
```

Set `MCP_PORT` for the MCP server to the new port.
Set `MCP_SERVER_URL` for the agent to that port and `/sse` path.
Set `PORT` and `URL` for the agent to the new A2A port.

Run the sample tests and formatting checks:

```bash
uv run --frozen --group dev pytest
uv run --frozen --group dev ruff check .
uv run --frozen --group dev ruff format --check .
```

## Troubleshooting

If the agent returns a failed task, make sure that the MCP process is running.
Make sure that `MCP_SERVER_URL` matches its port and `/sse` path. Repeat the
MCP smoke command before repeating the A2A message.

If a process reports that its port is occupied, stop your earlier sample
process or select an unused port. Update all corresponding URLs. Do not stop
an unrelated process.

If the business smoke fails, make sure that both providers remain in mock
mode. The sample has one mock order, `1000000`. An unknown order returns a
failed task instead of invented records.

If model credentials are requested, make sure that `LLM_PROVIDER=mock` reaches
the agent process. Model integration is optional and outside this checkpoint.

## Cleanup or rollback

For terminal runs, press `Ctrl+C` in each server terminal. This stops the agent
and its MCP server. The virtual environment can remain for the next recipe.

For the container path, stop Compose and remove the sample containers:

```bash
docker compose down
```

No BTP resources, business records, or model deployments are created by this
recipe.

## Region-specific notes

The local mock flow has no regional service dependency. Before selecting
AI Core or deploying in an unfamiliar region, use
[region preflight](../optional/region-preflight/).

## Changes under BAIP

This local checkpoint makes no assumption about future platform services.
Retain the A2A endpoint and tool boundary when changing the model provider.
Test the new provider before describing it as supported.

## Next

Use [connect-data](../optional/connect-data/) when a live backend is required.
Its current instructions still describe a different sales-order example.
The [production-order sample guide](../../samples/production-order-agent/)
contains the existing public production-order sandbox path.

The [sovereign gateway recipe](../optional/sovereign-model-gateway/) requires a
provider path beyond this mock baseline. Public toolkit MCP drivers, CAP,
durable HANA state, and automatic project generation are outside this local
checkpoint.
