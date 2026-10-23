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
