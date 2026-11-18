---
id: sovereign-model-gateway
title: Use an approved model gateway
description: Summarize production-order tool records through an approved OpenAI-compatible model endpoint.
prerequisites: []
est_time: 15 min
intended_platform: [local]
category: optional
status: experimental
---

# Use an approved model gateway

> Guided: Ask your coding agent: "Run the checked-in production-order sample with my approved model gateway."
> Input: The [Python production-order sample](../../../samples/production-order-agent/) and an approved gateway, model name, and access key.
> Output: The local agent summarizes its tool records with the selected model.

This recipe uses the checked-in Python sample.
It does not scaffold a CAP project or change a toolkit-generated agent.
If checkpoint 1 uses this sample, continue with the same project.
Generated projects need a separately tested provider and deployment path.

An OpenAI-compatible gateway accepts the chat completion request defined below.
The agent first calls both production-order MCP tools.
It then sends their records to the selected model.
The model receives no S/4 API key or AI Core credentials.
The default data mode stays `mock` and uses synthetic records.

Use this path when your organization approves the selected gateway.
API compatibility does not prove regional residency, retention, routing, or data-access approval.
Before an external call, obtain approval to send the selected records to that provider.
Use [region preflight](../region-preflight/) for current regional service context.
A region name alone does not select or approve a provider.

## Prerequisites

1. Install Python 3.12 or newer and [uv](https://docs.astral.sh/uv/).
2. Start from a clean public Cookbook clone.
3. Obtain the approved gateway base URL, model identifier, and bearer key.

The gateway must accept `POST <base-url>/chat/completions`.
Set the base URL to the API prefix, such as `https://gateway.example.com/v1`.
Use HTTPS for an external gateway.
HTTP is accepted only on loopback for a local test.
Embedded credentials, query parameters, fragments, and redirects are unsupported.

The request includes `model`, `messages`, `temperature: 0`, and `stream: false`.
The response must contain a nonempty string at `choices[0].message.content` and the role `assistant`.
This recipe does not require `/models`, embeddings, streaming, BTP, HANA, or the optional AI Core SDK.

## Start the local tools

In the first terminal, change to the sample directory from the Cookbook root:

```bash
cd samples/production-order-agent
uv sync --frozen --group dev
DATA_MODE=mock MCP_HOST=127.0.0.1 MCP_PORT=8090 \
uv run --frozen python -m production_order_agent.mcp_server
```

Keep the process local to your workstation.
The local MCP endpoint provides no authentication.
The tool records stay synthetic for this demonstration.

## Select the gateway

In the second terminal, change to the sample directory.
Set your approved URL and model name:

```bash
cd samples/production-order-agent
export MODEL_GATEWAY_URL=https://gateway.example.com/v1
export MODEL_NAME=approved-model-id
read -r -s MODEL_GATEWAY_API_KEY
echo
export MODEL_GATEWAY_API_KEY
HOST=127.0.0.1 PORT=8000 URL=http://127.0.0.1:8000 \
LLM_PROVIDER=openai-compatible MCP_SERVER_URL=http://127.0.0.1:8090/sse \
uv run --frozen python -m production_order_agent
```

Replace the URL and model example with the approved values.
The example URL is not a working provider.
Do not put the key in chat, command arguments, files, or logs that you share.
The agent sends the key in the gateway `Authorization` header.
It uses a bounded timeout and keeps TLS certificate validation enabled.
It does not follow redirects or use proxy environment variables.

## Make sure that the provider path works

In a third terminal, send a real A2A message to the agent:

```bash
curl -fsS http://127.0.0.1:8000/ \
  -H 'Content-Type: application/json' \
  -H 'A2A-Version: 1.0' \
  -d '{
    "jsonrpc": "2.0",
    "id": "gateway-demo",
    "method": "SendMessage",
    "params": {
      "message": {
        "messageId": "gateway-demo-message",
        "role": "ROLE_USER",
        "parts": [{"text": "Show the status and operations for order 1000000."}]
      }
    }
  }'
```

Make sure that the task state is `TASK_STATE_COMPLETED`.
Read the text in its artifact.
Make sure that it describes the returned statuses and operations.
The synthetic order includes Released, Partially Confirmed, and operations 0010 and 0020.
The answer must not invent a business cause for a delay.
Model wording can vary, so inspect the business meaning.

An Agent Card or HTTP 200 alone does not prove this result.
If the provider request fails, the task must report `TASK_STATE_FAILED`.
The public error text must omit the key, endpoint, and provider response body.
Local synthetic tests prove the request contract, without proof of an external provider or sovereign residency.

## Container path

To run the same provider path in containers, set the approved gateway variables
from the selection step, then use the explicit gateway override from the sample
directory:

```bash
docker compose -f compose.yaml -f compose.gateway.yaml up --build
```

The override selects the core model-consumer image and requires an explicit
model, URL, and bearer key. The gateway must be reachable from the agent
container. Use HTTPS for a gateway outside its loopback network. The published
agent and MCP ports remain bound to your workstation's loopback interface.

Send the A2A message from the verification step. Stop these local containers
with:

```bash
docker compose -f compose.yaml -f compose.gateway.yaml down
```

## Repeatable controlled test

From the sample directory, test the provider against controlled responses:

```bash
uv run --frozen --group dev pytest -q tests/test_gateway.py
uv run --frozen --group dev python scripts/smoke_gateway.py
```

The smoke command starts owned loopback gateway, MCP, and A2A processes.
It compares both backend datasets with the gateway request and the response with the completed A2A artifact.
It requires the expected statuses, operation numbers, and delay assessment.
It stops only its owned processes and requires their ports to close.
The fixture does not prove external model inference.
The optional `--model-url` flag is a diagnostic for a separately approved
loopback gateway. Direct free-text Qwen2.5 1.5B replies failed the required
business-accuracy check; that route is not a validated model path.
For this pinned model, use the structured bridge path below.
Gateway input is bounded to 200 records per tool and 64 KiB of serialized business data.
The completion request sets max_tokens to 2048. The gateway must support that
field and a nonstreaming JSON response with identity encoding. The client
stops reading above 128 KiB, rejects assistant text above 16 KiB, and limits
the complete request to 30 seconds. Over-limit responses close the connection
and return a safe failure; they never become a mock answer.

## Validated local model path

The checked-in private bridge converts the gateway's business records into a
schema-constrained model request. It validates every returned status name,
operation identifier, confirmation and potential-delay identifier against the
backend-derived values. A missing or changed fact fails the request without a
mock answer. Caller prompts and gateway bearer keys do not reach the model.

Build and run the local path from the Cookbook root:

```bash
docker build --platform linux/amd64 -t cookbook-qwen:local samples/custom-model-serving
docker build --platform linux/amd64 -f samples/production-order-agent/Dockerfile.model-consumer -t cookbook-gateway:local samples/production-order-agent
python3 samples/production-order-agent/scripts/smoke_gateway_bridge.py --model-image cookbook-qwen:local --consumer-image cookbook-gateway:local
```

The [local serving sample](../../../samples/custom-model-serving/) includes all
model build sources and upstream license details. Docker and Python 3.12 or
newer are required. Building downloads about 986 MB of public model data;
running the test makes no external request and publishes no host port.

The command starts an owned local model, structured bridge, MCP server and A2A
agent. It verifies eight phases with non-default synthetic order 7654321:

- Gzip and deflate S/4 responses produce exact status and operation results.
- Data, OAuth and inference refusals produce safe failed A2A tasks, skip the
  appropriate downstream calls and never return a mock answer.
- Restoring each failed boundary produces the exact result in the same
  running agent, without restarting its MCP or bridge process.

Actual Qwen inference generates the accepted structured replies. S/4 records
and OAuth remain synthetic fixtures. The gateway retains its 30-second total
request deadline; this local bridge uses the existing custom-adapter timeout
setting at 25 seconds. CPU emulation or constrained hosts can exceed that
budget, in which case the test must fail rather than weaken the deadline.

The command reaps its helper processes, verifies their ports close, and removes
only its uniquely owned containers. The normal Compose gateway path above
still requires your approved external gateway; the smoke command does not
silently reconfigure it. This local result does not prove cloud OAuth,
deployment, sovereign residency or production readiness.

## Troubleshooting

If the task fails, make sure that both local processes still run.
Make sure that the model identifier belongs to the selected gateway.
Make sure that the URL includes the API prefix and excludes `chat/completions`.
Make sure that the key uses the approved bearer authentication method.
Make sure that the gateway supports nonstreaming chat completions with the required fields.
Read local diagnostic types without sharing raw provider responses or secrets.

## Cleanup

Stop both server processes with Ctrl+C in their terminals.
Remove the gateway variables from the second terminal:

```bash
unset MODEL_GATEWAY_API_KEY MODEL_GATEWAY_URL MODEL_NAME
```

This recipe creates no BTP or gateway resource.
The local agent keeps task state in memory.
The gateway can bill or retain requests according to its approved service terms.
Choose a separately tested deployment recipe before exposing the agent outside your workstation.
