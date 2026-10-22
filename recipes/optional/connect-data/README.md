---
id: connect-data
title: Connect the agent to sandbox data
description: Read production-order records through the public SAP sandbox and compare the agent reply with those records.
prerequisites: []
est_time: 15 min
intended_platform: [local]
category: optional
status: experimental
---

# Connect the agent to sandbox data

> Guided: Ask your coding agent: "Connect the checked-in production-order sample to the public SAP sandbox."
> Input: The checked-in [production-order agent](../../../samples/production-order-agent/) and a personal sandbox API key.
> Output: The same agent answers from production-order records returned by the public sandbox.

The checked-in sample already contains the data connector.
You change its runtime configuration, then send a real A2A message.
A2A is the protocol that carries messages between agents.
The agent calls two MCP tools for status and scheduled operations.
MCP is the protocol that connects agents to tools.

This is a standalone path for the checked-in Python sample.
If checkpoint 1 uses that sample, continue with the same project here.
Older toolkit-generated projects need their own backend adapter.
This recipe does not modify those projects or provide their deployment handoff.

This recipe uses `API_PRODUCTION_ORDER_2_SRV` and `A_ProductionOrder_2`.
The sandbox returns synthetic demonstration records over a real HTTP API.
These records do not prove access to a customer tenant or live business data.
The model provider remains `mock`, which produces a deterministic summary.
You do not need BTP, AI Core, Joule, or a private toolkit for this path.

## Prerequisites

1. Install Python 3.12 or newer and [uv](https://docs.astral.sh/uv/).
2. Start from a clean public Cookbook clone.
3. Obtain your personal API key from [SAP Business Accelerator Hub](https://api.sap.com/api/API_PRODUCTION_ORDER_2_SRV/overview).

Use the terms shown on SAP Business Accelerator Hub for sandbox access.
The sandbox requires public internet access.
Air-gapped environments need a separate, approved connection to their own backend.
Customer authentication, BTP Destinations, and principal propagation are outside this recipe.

## Start the MCP data server

In the first terminal, change to the sample directory from the Cookbook root:

```bash
cd samples/production-order-agent
uv sync --frozen --group dev
```

Enter your API key without echoing it:

```bash
read -r -s S4_API_KEY
echo
export S4_API_KEY
export DATA_MODE=s4
export S4_BASE_URL=https://sandbox.api.sap.com/s4hanacloud/sap/opu/odata/sap/API_PRODUCTION_ORDER_2_SRV
MCP_HOST=127.0.0.1 MCP_PORT=8090 \
uv run --frozen python -m production_order_agent.mcp_server
```

Do not paste the key into chat, a command, source files, or an environment file.
The MCP server sends the key in the `APIKey` header.
The agent and model receive tool records, without the key.
`S4_BASE_URL` includes the full API service path.
The sample does not use `S4_USERNAME`, `S4_PASSWORD`, or `S4_APIKEY`.

## Start the A2A agent

In a second terminal, change to the same sample directory:

```bash
cd samples/production-order-agent
HOST=127.0.0.1 PORT=8000 URL=http://127.0.0.1:8000 \
LLM_PROVIDER=mock \
MCP_SERVER_URL=http://127.0.0.1:8090/sse \
uv run --frozen python -m production_order_agent
```

Keep both processes local to your workstation.
The sample provides no authentication on either local endpoint.

## Make sure that the data path works

In a third terminal, change to the same sample directory.
Enter your key again because separate terminals do not share exported variables:

```bash
cd samples/production-order-agent
read -r -s S4_API_KEY
echo
export S4_API_KEY
export S4_BASE_URL=https://sandbox.api.sap.com/s4hanacloud/sap/opu/odata/sap/API_PRODUCTION_ORDER_2_SRV
uv run --frozen python scripts/smoke_data.py --order-id 1000001
```

The command reads status and operations directly from the backend.
It then sends `Show the status and operations for order 1000001.` to the agent.
It compares the completed reply with the summary of those backend records.
The comparison ignores record order but retains every summary line and duplicate.
The command prints record counts and the comparison result.
It prints no API key, endpoint URL, or raw business records.

Choose a numeric order from the sandbox API explorer that returns both datasets.
Replace the example `1000001` if that order is absent in your sandbox.
The command rejects the built-in mock order `1000000`.
An absent order, unusable records, a failed task, or a different reply fails the command.
If the sandbox records change between reads, repeat the command.

The Agent Card is at `/.well-known/agent-card.json` on port 8000.
An Agent Card alone does not prove that the data path works.
The summary identifies an overdue operation only from its returned dates and confirmation state.
It does not establish the business cause of a delay.

## Troubleshooting

If the command fails, make sure that both processes still run.
Make sure that the MCP terminal uses `DATA_MODE=s4` and a valid `S4_API_KEY`.
Make sure that the agent uses `LLM_PROVIDER=mock` and the correct MCP URL.
Make sure that `S4_BASE_URL` includes the full production-order service path.
Use an order that exists in your sandbox and returns both datasets.
Keep API keys and raw responses out of logs that you share.

## Cleanup

Stop both server processes with Ctrl+C in their terminals.
In the first and third terminals, remove the connection variables:

```bash
unset S4_API_KEY S4_BASE_URL DATA_MODE
```

The recipe performs read-only requests and creates no SAP resource.
The sample keeps A2A task state in memory.
For the local demonstration, stop the servers after the test.
Choose a separately validated deployment recipe before exposing the agent outside your workstation.
