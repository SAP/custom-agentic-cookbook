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

From this sample directory, assert the completed mock business reply:

```bash
uv run --frozen python scripts/smoke_a2a.py
```

Use this command with `DATA_MODE=mock` and `LLM_PROVIDER=mock`. It requires
both status records and operation numbers for order `1000000`. It exits with
an error if the task fails or those records are missing. To select a different
local A2A port, add `--base-url http://127.0.0.1:<port>`.

The manual request below shows the same message envelope.

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

Compose builds both processes with `Dockerfile.mock`, which installs only the
frozen core dependencies. The agent uses the mock summary provider. Compose
supplies the process commands and internal MCP URL:

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

Compose drops all Linux capabilities and prevents either service from gaining
new privileges. The image pins Python 3.12 Alpine and uv 0.13.5 by digest.
The `BASE_IMAGE` and `UV_IMAGE` build arguments accept complete image references.
An override requires a separate dependency and runtime assessment.

The builder uses uv to install frozen dependencies from wheels; uv and its
build cache stay outside the runtime image. Both Python stages use the same
base. Alpine uses musl instead of glibc, so additional native dependencies need
a compatibility check. The runtime removes the unused global pip installer and
ensurepip backup, and retains its operating-system package inventory for scanning.
Assess the complete image and Python dependencies before deployment; a base
change does not establish production readiness.

## Use the public SAP S/4HANA sandbox

Follow the [connect-data recipe](../../recipes/optional/connect-data/) for the
local production-order path and a repeatable comparison with backend records.
The recipe uses the existing connector and keeps the model provider in mock mode.

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

Store the downloaded service-key JSON outside the repository with owner-only
permissions, then install the optional SDK and configure your local profile
directly from that file:

```bash
chmod 600 /secure/path/aicore-service-key.json
uv sync --frozen --group dev --extra aicore
(
  set -e
  umask 077
  uv run --frozen --extra aicore aicore configure \
    --service-key-json /secure/path/aicore-service-key.json
  chmod 600 ~/.aicore/config.json
)
```

This avoids entering the client secret at an echoed terminal prompt. Delete the
downloaded service-key file when it is no longer needed, following your
organization's credential-retention policy.

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

Compose does not mount `~/.aicore/config.json` into the container.
Export `AICORE_AUTH_URL`, `AICORE_CLIENT_ID`, and `AICORE_CLIENT_SECRET` in the shell.
Export `AICORE_BASE_URL`, `AICORE_RESOURCE_GROUP`, and `MODEL_NAME` in the shell.
The AI Core override passes these values to the agent.
Make sure that `AICORE_BASE_URL` ends in `/v2`.

Select the [AI Core override](compose.aicore.yaml) explicitly:

```bash
docker compose -f compose.yaml -f compose.aicore.yaml up --build
```

This override builds only the agent with the optional model `Dockerfile` and
sets its provider to `aicore`. MCP keeps the core `Dockerfile.mock` image and
mock business records. The default Compose flow does not install the SDK.
Remove the optional stack with the same files:

```bash
docker compose -f compose.yaml -f compose.aicore.yaml down
```

The optional `sap-ai-sdk-gen` and `sap-ai-sdk-core` packages use Apache-2.0.
The `sap-ai-sdk-base` dependency uses the SAP Developer License Agreement 3.1.
The Cookbook license does not replace that agreement.
Before using the optional SDK, read its
[package license](https://pypi.org/project/sap-ai-sdk-base/3.4.0/). Redistribution of SDK-containing images requires a separate
license review. The core mock image does not include these SDK packages.

## Test

```bash
uv run --frozen --group dev pytest
uv run --frozen --group dev ruff check .
uv run --frozen --group dev ruff format --check .
```

The tests use mock transports and never require or contact SAP S/4HANA or SAP
AI Core.

The optional AI Core path uses `sap-ai-sdk-gen` 7.4.1 or newer, below version 8.
SDK 7 replaces the SDK 6 dependency constraints. The locked graph removes
langchain-community and its aiohttp dependencies. The native OpenAI client
interface remains unchanged in this sample.

To test the actual SDK client with synthetic HTTP responses, include the
`aicore` extra:

```bash
uv run --frozen --group dev --extra aicore pytest
```

These tests exercise model routing, supplied tool records, and rejection of
empty completion content. Without the extra, the SDK tests skip.
Mock transport tests do not establish live AI Core behavior or clear every
dependency advisory. Assess the full dependency graph before deployment.

## Boundaries

- Local, Compose, and experimental existing-cluster Kyma mock execution
- No Cloud Foundry or Joule deployment assets in this sample
- In-memory A2A task state
- No authentication on the A2A or MCP endpoints
- Read-only production-order tools
- No RAG, SAP-RPT-1, UI, or observability stack
- A date-based delay signal, not a production scheduling decision

## Deploy the mock sample to Kyma

Follow the [existing-cluster recipe](../../recipes/02-deploy-btp/) for the checked-in mock sample.
The [production-order chart](../../charts/production-order-agent/) runs the agent and its private MCP service with the same image digest.
The chart keeps one agent replica and prevents overlapping replicas during upgrades.
Its default services stay inside the cluster and provide no application authentication.
Approve image publication, deployment, optional public exposure, and cleanup separately.
This path does not deploy toolkit-generated projects or configure live data, model providers, HANA, or Joule.

## S/4 transport limits

The S/4 client limits both transferred and decoded response bodies to one MiB.
It requests identity encoding, but also accepts gzip and zlib-wrapped deflate if
an intermediary compresses the response. Decoding stops as soon as either limit
is exceeded. Unsupported encodings and malformed or truncated compression fail
with a safe diagnostic, and the response stream closes.
It ignores ambient proxy variables and returns safe errors for timeouts, failed requests, and malformed OData.
The MCP process omits endpoint addresses from HTTP transport logs.

## Optional custom AI Core model

Select LLM_PROVIDER=aicore-custom and MODEL_NAME=qwen2.5:1.5b for the separate custom-model consumer.
Build this consumer with `Dockerfile.model-consumer`, as shown in the
[custom-model recipe](../../recipes/optional/bring-your-own-model/#custom-deployment-consumer).
Its frozen base dependencies include the OAuth-aware HTTP client; the optional
SAP foundation-model SDK is required only for `LLM_PROVIDER=aicore`.
Supply its selected deployment URL, OAuth token URL, client credentials, and resource group through a private environment.
The consumer acquires a fresh token per summary, retries one inference HTTP 401, and closes each HTTP client.
It sends at most 200 records per tool and 64 KiB of business data.
A provider failure produces a failed A2A task without mock fallback.
For Compose, select `compose.custom-model.yaml` explicitly alongside `compose.yaml`;
the default stack retains its fixed mock provider.
See the [custom-model recipe](../../recipes/optional/bring-your-own-model/) and [serving sample](../custom-model-serving/) for the local image test, live gates, and cleanup.
