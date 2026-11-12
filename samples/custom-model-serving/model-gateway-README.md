# Private custom-model gateway

The [bridge](../production-order-agent/src/production_order_agent/model_bridge.py) adapts the public gateway client to the custom-model OAuth consumer.
It accepts POST /v1/chat/completions and one user message whose JSON content contains manufacturing_order, statuses, and operations.
The default bridge binds only to 127.0.0.1:8081.
It serves only the structured production-order contract.

The bridge ignores system prompts, caller dates, and unrelated fields.
It forwards only the numeric order ID and the two record lists to the custom-model adapter.
The adapter supplies the fixed prompt, current date, bounded business facts, and OAuth transport.
It makes sure that returned facts match the source records before the bridge returns OpenAI assistant JSON.

MODEL_NAME selects the approved model. Requests must match it exactly.
MODEL_GATEWAY_TOKEN supplies the bearer token, with 16 to 256 permitted token characters.
Token comparison uses a constant-time operation.
Total request bodies must be at most 128 KiB.
The structured record message must be at most 64 KiB and contain at most 200 records per tool.
Order IDs must contain 1 to 20 ASCII digits.
max_tokens must be an integer between 1 and 2048. Streaming is unsupported.
The adapter retains its fixed constrained-output token budget.
The bridge never forwards caller prompts or token-budget instructions.

Errors return generic 4xx or 5xx messages without upstream diagnostics.
The bridge closes each request connection, and the adapter closes each upstream HTTP client.
Body reads have a ten-second deadline.
The complete upstream call has a 300-second deadline.
The OAuth consumer bounds token replies to 32 KiB and inference replies to 128 KiB.
Its complete OAuth and inference call uses one configured deadline.

## Local verification

Start the pinned Qwen serving image with the loopback commands in the [serving README](README.md).
From the production-order sample directory, run:

```bash
uv sync --frozen --group dev
uv run --frozen --group dev pytest -q tests/test_model_bridge.py
uv run --frozen --group dev python scripts/smoke_model_bridge.py --model-url http://127.0.0.1:18086/v1
```

The smoke starts an owned bridge process and a controlled OAuth relay.
It sends real model inference through the bridge and requires its answer to equal the actual model reply.
It stops the exact process and relay.
It makes sure that their ports close.
The OAuth relay is a fixture. This proves local inference and protocol wiring.
Deployed AI Core authentication, A2A gateway consumption, and live cleanup remain separate gates.
Remove the exact Qwen container and temporary images using the serving README.

## Optional private Pod

[model-gateway-deployment.yaml](model-gateway-deployment.yaml) combines the gateway agent, mock MCP service, and loopback bridge in one private Pod.
Replace all placeholders in an ignored copy.
Use the approved gateway-agent image for agent and MCP, and the model-consumer image for the bridge.
Only the bridge receives AI Core credentials.
The agent receives only the shared gateway bearer token through a Secret reference.
The bridge and agent use the same token Secret key. Registry credentials remain in an existing pull Secret.
The bridge has no Service port. The agent Service uses ClusterIP and has no public endpoint.
This preserves the gateway client's external HTTPS validation and the fixed-mock chart contract.

From the Cookbook root, build the bridge and OAuth consumer from the core-only Dockerfile:

```bash
docker build --platform linux/amd64 -f samples/production-order-agent/Dockerfile.model-consumer -t cookbook-model-consumer:local samples/production-order-agent
```

This Dockerfile uses only the frozen core dependencies; the native AI Core SDK is unnecessary for OAuth HTTP inference.
The container command selects the bridge in the optional deployment.
Review the exact images, namespace, Secret references, resources, cost, and cleanup before live deployment approval.
After approval, send a real A2A question through the gateway agent and require the expected statuses, operations, confirmations, and delay assessment.
For cleanup, remove only the reviewed Deployment and Service, then make sure that those exact objects disappear.
Preserve the AI Core instance, shared registry, and pre-existing Secrets.
