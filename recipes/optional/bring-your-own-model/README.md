# Custom model on SAP AI Core

This recipe includes a pinned llama.cpp CPU serving image, a Qwen2.5 1.5B model, and an OAuth-aware production-order consumer.
Local tests remain separate from AI Core deployment proof.
Keep the recipe partial until the selected AI Core deployment and deployed A2A application pass the live tests.

Use the public [production-order starter](../../../samples/production-order-agent/) and the separate [serving assets](../../../samples/custom-model-serving/).
The default mock provider and A2A v1 interface remain compatible.
Select LLM_PROVIDER=aicore-custom only for this custom deployment path.
The foundation-model provider remains a separate integration.

The [Kyma mock recipe](../../02-deploy-btp/) deploys the fixed mock sample.
Use the separate consumer manifests below for this model-enabled path.

Use this recipe only where AI Core is available and entitled. For regions without
AI Core, assess the [sovereign model gateway](../sovereign-model-gateway/) and an
approved OpenAI-compatible endpoint. Custom serving does not bypass regional availability.

## Prerequisites

Complete [regional preflight](../region-preflight/) for the selected AI Core target.
Use the AI Core extended plan for the test deployment.
Review the model license, image digest, resource plan, registry, watched Git path, and estimated service cost before live changes.
Keep each test in its own resource group.
Use an existing approved credential Secret for the consuming application.

## Local serving

From the Cookbook root, build the reviewed amd64 image:

```bash
docker build --platform linux/amd64 -t cookbook-qwen:local samples/custom-model-serving
```

The build loads qwen2.5:1.5b and requires its exact manifest digest.
Runtime uses that model from the image and requires no model download.
The image runs as UID/GID 10001 and listens on port 8080.
Read the serving README for the loopback test and exact cleanup commands.

## Custom deployment consumer

From the Cookbook root, build the separate consumer image:

```bash
docker build --platform linux/amd64 \
  --file samples/production-order-agent/Dockerfile.model-consumer \
  --tag cookbook-custom-consumer:local \
  samples/production-order-agent
```

`Dockerfile.model-consumer` installs the frozen base dependencies used by
`LLM_PROVIDER=aicore-custom` and the mock MCP server. This OAuth-aware custom
provider uses `httpx` and does not require the optional SAP foundation-model SDK.
The standard `Dockerfile` includes that SDK for `LLM_PROVIDER=aicore`.

For a local two-service consumer and MCP stack, export the custom-model variables
below and select the explicit override from the sample directory:

```bash
docker compose -f compose.yaml -f compose.custom-model.yaml up --build
```

Stop its exact stack with the same files:

```bash
docker compose -f compose.yaml -f compose.custom-model.yaml down
```

The override builds only the agent with `Dockerfile.model-consumer`. The default
Compose flow retains the fixed mock provider, and MCP retains `Dockerfile.mock`.
The standard SDK image remains optional; redistribution requires a separate
review of the [SAP Developer License Agreement](https://pypi.org/project/sap-ai-sdk-base/3.4.0/).

For the local consumer tests, install the frozen starter dependencies:

```bash
cd samples/production-order-agent
uv sync --frozen --group dev
uv run --frozen --group dev pytest -q tests/test_custom_model.py
```

Set these variables through the approved application Secret or an owner-only local environment:

```text
LLM_PROVIDER=aicore-custom
MODEL_NAME=qwen2.5:1.5b
AICORE_TOKEN_URL=<exact-OAuth-token-endpoint>
AICORE_CUSTOM_DEPLOYMENT_URL=<deployment-response-deploymentUrl>
AICORE_RESOURCE_GROUP=<test-resource-group>
AICORE_CLIENT_ID=<approved-client-id>
AICORE_CLIENT_SECRET=<approved-client-secret>
```

Use deploymentUrl from the AI Core deployment response.
The consumer appends /v1/chat/completions to that URL.
The status API under /v2/lm/deployments is not an inference endpoint.
The consumer acquires a fresh OAuth token for each summary and retries once after an inference HTTP 401.
It disables redirects and ambient proxies and keeps TLS enabled.
It closes each HTTP client after the request.
The default timeout is 180 seconds. AICORE_CUSTOM_TIMEOUT_SECONDS accepts an explicit value from 1 to 300 seconds.
Model input contains at most 200 records per tool and 64 KiB of serialized business data.
The consumer normalizes status, confirmation, and delay facts with the existing deterministic summary rules.
A JSON schema defines JSON fields and types.
The consumer requires all statuses, operation IDs, confirmation labels, and delayed operation IDs in the model reply.
It rejects a reply that omits or changes those source facts.
The A2A artifact contains that structured model reply.
This path proves constrained inference. Open-ended model reasoning remains outside its acceptance result.
Credentials stay in transport headers or the OAuth exchange.
A failed request produces a failed A2A task without a mock fallback.

After reviewing and publishing the consumer image to your registry, record its
immutable registry manifest digest. In an ignored copy of
`samples/custom-model-serving/consumer-deployment.yaml`, replace both
`REPLACE_WITH_REVIEWED_AGENT_IMAGE_DIGEST` entries with that same
`<repository>@sha256:<digest>` reference. The agent and mock MCP process use the
same consumer image. Keep application and registry credentials in the referenced
Secrets, and review the complete manifest before deployment approval.

## AI Core preparation

Copy serving-template.yaml from the serving assets into an ignored local directory.
Replace its registry Secret name and image placeholder with the approved values.
Use the tested image digest and the reviewed infer.s plan.
The template requests one replica.

After separate approval for each live operation, register the image credentials, watched repository, and application in AI Core.
Create the configuration for scenario cookbook-custom-model and executable cookbook-qwen-small.
After deployment approval, create its deployment and wait for RUNNING with a deploymentUrl.
The image already contains the model. Do not pull a different model into the running deployment.

## Verification

Send an authenticated inference request through the selected deploymentUrl.
Require a nonempty answer from qwen2.5:1.5b in the selected resource group.
Then deploy the separate consumer assets after deployment approval.
Send a real A2A question about order 1000000 through both mock MCP tools.
Require Released, Partially Confirmed, operations 0010 and 0020, and a delay assessment for unconfirmed operation 0020.
Compare the model response with the completed A2A artifact.
Record the final commit, model digest, image digest, resource group, deployment state, inference result, and cleanup result separately.
Local protocol tests do not satisfy this live gate.

## Cleanup

Obtain approval for the exact live resources first.
Remove only the test deployment, configuration, watched application, consumer release, and test-owned credential references.
Make sure that those exact resources disappear.
Preserve shared instances, registries, and credentials.
The serving README lists exact local container cleanup.

## Sources

[llama.cpp OpenAI compatibility](https://github.com/ggml-org/llama.cpp/blob/8642541b255bfb5dc39cd351a178be09013a55d6/tools/server/README.md) defines the inference route.
[Qwen2.5 1.5B Instruct](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct) supplies the upstream model and license.
[SAP custom-model tutorial](https://developers.sap.com/tutorials/ai-core-custom-llm.html) describes AI Core serving integration.
