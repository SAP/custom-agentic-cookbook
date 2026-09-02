# Production Order Agent

> **Status:** Experimental business example. It is designed for local and
> container demonstrations, not production use.

This sample answers a production planner's question such as **“Why is
production order 1000000 delayed?”**. An A2A v1.0 agent calls two MCP tools,
combines the returned SAP S/4HANA records, and reports status, scheduled
operations, and any overdue operation that is not finally confirmed.

```text
A2A client -> Production Order Agent -> MCP server -> mock records (default)
                                      |            -> S/4 public sandbox
                                      -> deterministic summary (default)
                                      -> SAP AI Core summary (optional)
```

The sample is mock-safe by default: no BTP account, S/4 tenant, LLM, or
credentials are needed. The public SAP Business Accelerator Hub sandbox and SAP
AI Core are independent opt-ins.

## What it demonstrates

- A2A v1.0 Agent Card at `/.well-known/agent-card.json` and JSON-RPC at `/`
- A standalone MCP server exposing exactly:
  - `get_production_order_status`
  - `get_production_order_operations`
- OData v2 and v4 response-envelope handling
- `APIKey` authentication for the public SAP S/4HANA sandbox
- Optional result synthesis through SAP AI Core using `sap-ai-sdk-gen`
- A non-root container and a two-service Docker Compose setup

The agent always fetches both business datasets itself. The model, when
enabled, receives only those tool results and summarizes them; it never receives
the S/4 API key.

## Prerequisites

- Python 3.12 or newer
- [`uv`](https://docs.astral.sh/uv/)
- `curl` and `jq` for the A2A smoke test
- Docker with Compose for the container path

## Run locally with mock data

Install the locked dependencies:

```bash
uv sync --frozen --group dev
```

Start the MCP server in the first terminal:

```bash
DATA_MODE=mock uv run --frozen python -m production_order_agent.mcp_server
```

Start the A2A agent in a second terminal:

```bash
LLM_PROVIDER=mock \
MCP_SERVER_URL=http://127.0.0.1:8090/sse \
uv run --frozen python -m production_order_agent
```

Confirm that the MCP server exposes only the two expected tools:

```bash
uv run --frozen python scripts/smoke_mcp.py
```

## Verify the A2A business flow

Fetch the Agent Card:

```bash
BASE_URL=http://127.0.0.1:8000
curl -s "$BASE_URL/.well-known/agent-card.json" | jq .name
```

Expected result:

```text
"Production Order Agent"
```

Send a real A2A v1.0 message:

```bash
curl -s -X POST "$BASE_URL/" \
  -H 'Content-Type: application/json' \
  -H 'A2A-Version: 1.0' \
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
    "method": "SendMessage",
    "params": {
      "message": {
        "messageId": "msg-1",
        "role": "ROLE_USER",
        "parts": [{"text": "Why is production order 1000000 delayed?"}]
      }
    }
  }' | jq
```

The completed task artifact contains the `Released` and `Partially Confirmed`
statuses, operations `0010` and `0020`, and a potential-delay signal for the
overdue, unconfirmed operation `0020`.

## Run in containers

The same image runs either process; Compose supplies the process command and
the internal MCP URL:

```bash
docker compose up --build
```

Repeat the A2A checks against `http://127.0.0.1:8000`, then stop and remove the
sample containers:

```bash
docker compose down
```

The containers run as UID/GID `10001`. Neither service exposes authentication,
so keep ports `8000` and `8090` local to your workstation.

## Use the public SAP S/4HANA sandbox

The workshop's pro-code path used organizer-managed runtime credentials rather
than asking each participant to obtain them. For this self-contained sample,
obtain your own free SAP Business Accelerator Hub API key:

1. Open the [Production Order (Version 2) API
   overview](https://api.sap.com/api/API_PRODUCTION_ORDER_2_SRV/overview).
2. Sign in to SAP Business Accelerator Hub.
3. Copy your personal API key from the API-key control on the site. Do not add
   it to `.env`, source control, shell history, or a container image.
4. Enter it into the current shell without echoing it:

   ```bash
   read -rsp "SAP Business Accelerator Hub API key: " S4_API_KEY
   echo
   export S4_API_KEY
   export DATA_MODE=s4
   export S4_BASE_URL=https://sandbox.api.sap.com/s4hanacloud/sap/opu/odata/sap/API_PRODUCTION_ORDER_2_SRV
   ```

5. Restart the MCP server and ask about a sandbox order such as `1000001`.

You can isolate the data connection before starting the agent:

```bash
curl -s --compressed \
  "$S4_BASE_URL/A_ProductionOrder_2('1000001')/to_ProductionOrderStatus?\$format=json" \
  -H "APIKey: $S4_API_KEY" \
  -H 'Accept: application/json' \
  | jq '.d.results // .value'
```

For containers, export the same variables and run `docker compose up --build`;
Compose forwards them to the MCP service without storing their values in the
file. The sandbox contains synthetic demonstration data and is subject to the
terms shown on SAP Business Accelerator Hub.

## Optionally summarize with SAP AI Core

Mock mode already provides the complete A2A-to-MCP business flow. AI Core is
needed only if you want a model-written summary.

You need an SAP BTP subaccount with an SAP AI Core `extended` service instance,
a service key, a resource group, and a running foundation-model deployment in
that resource group. If these do not exist, an administrator can create the
entitlement and instance in **BTP Cockpit → Services → Service Marketplace**,
then create a service key under the instance. Never commit or paste the service
key into source files.

Install the optional SDK and configure your local profile:

```bash
uv sync --frozen --group dev --extra aicore
(
  set -e
  umask 077
  uv run --frozen --extra aicore aicore configure
  chmod 600 ~/.aicore/config.json
)
```

Use these service-key fields when prompted:

| `aicore configure` prompt | Service-key value |
| --- | --- |
| Auth URL | `url` plus `/oauth/token` |
| Client ID | `clientid` |
| Client secret | `clientsecret` |
| Base URL | `serviceurls.AI_API_URL`, ending in `/v2` |
| Resource group | The group containing the running model deployment |

Select an available deployed model at runtime; the sample deliberately does
not hardcode one:

```bash
export LLM_PROVIDER=aicore
export MODEL_NAME=<model-name-available-in-your-resource-group>
uv run --frozen python -m production_order_agent
```

The Cookbook's [`sap-ai-core`](../../skills/sap-ai-core/) skill contains the
broader bootstrap and verification workflow. Run the
[`region-preflight`](../../recipes/optional/region-preflight/) before selecting
AI Core in a sovereign or unfamiliar region.

For Compose, `~/.aicore/config.json` is not mounted into the container. Export
`AICORE_AUTH_URL`, `AICORE_CLIENT_ID`, `AICORE_CLIENT_SECRET`,
`AICORE_BASE_URL`, and `AICORE_RESOURCE_GROUP` in the shell instead; Compose
passes them through. Ensure `AICORE_BASE_URL` ends in `/v2`.

## Test

```bash
uv run --frozen --group dev pytest
uv run --frozen --group dev ruff check .
uv run --frozen --group dev ruff format --check .
```

The tests use mock transports and never require or contact SAP S/4HANA or SAP
AI Core.

## Boundaries

- Local and container execution only; no Cloud Foundry, Kyma, or Joule assets
- In-memory A2A task state
- No authentication on the A2A or MCP endpoints
- Read-only production-order tools
- No RAG, SAP-RPT-1, UI, or observability stack
- A date-based delay signal, not a production scheduling decision
