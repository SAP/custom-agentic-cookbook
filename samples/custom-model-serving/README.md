# Qwen custom serving sample

This sample uses llama.cpp v0.8.0 (b11960) and qwen2.5:1.5b.
The Dockerfile builds the CPU server from commit 8642541b255bfb5dc39cd351a178be09013a55d6, verifies its archive hash, and pins both build and runtime image digests.
The runtime contains only the server, its Alpine libraries, and the selected model.
It replaces Ollama serving while retaining the same Qwen GGUF blob and OpenAI-compatible inference route.
The model manifest digest is 65ec06548149b04c096a120e4a6da9d4017ea809c91734ea5631e89f96ddc57b.
The model is about 986 MB. Its upstream license is Apache-2.0.
The build requires network access to public images, Alpine packages, the upstream source archive, and the Ollama model registry.
The checked-in manifest preserves the selected model even if the upstream tag changes.
The build verifies its digest and every downloaded blob hash and size before installation.
Runtime requires no model download.
The build downloads at most 8 MiB per fresh signed redirect and validates every byte-range response.
Each socket has a 120-second timeout, and each blob has a 30-minute download budget with no automatic retries.
A later build can resume a partial cache entry; complete entries always pass size and SHA-256 verification before use.

## Local test

From the Cookbook root, build the image:

```bash
docker build --platform linux/amd64 -t cookbook-qwen:local samples/custom-model-serving
```

Start only this owned container on a free loopback port:

```bash
docker run --detach --name cookbook-qwen-local --platform linux/amd64 --cap-drop ALL --security-opt no-new-privileges --memory 4g --cpus 4 --publish 127.0.0.1:18086:8080 cookbook-qwen:local
```

Wait until the loaded model reports healthy:

```bash
curl --fail --silent http://127.0.0.1:18086/health
```

Send the production-order question through a real A2A process, MCP process, controlled OAuth exchange, and this model:

```bash
cd samples/production-order-agent
uv sync --frozen --group dev
uv run --frozen --group dev python scripts/smoke_custom_model.py --model-url http://127.0.0.1:18086/v1
```

The command selects a 300-second timeout for local CPU emulation.
The command compares the model input with both mock MCP datasets.
It requires a completed A2A artifact equal to the actual model response and the expected business fields.
It stops its exact A2A, MCP, and gateway processes and requires their ports to close.
The OAuth exchange is a local fixture. It does not prove AI Core authentication.
AI Core inference and deployed consumption remain separate live gates.

The consumer reserves space for every required status and operation in the JSON reply.
Its completion allowance grows with those output fields. A conservative UTF-8 byte
bound covers the prompt, response schema, full reply, and chat-template overhead
inside the pinned server's 4096-token context. Inputs that exceed this budget fail
before the OAuth or inference call. The 200-record and 64-KiB limits are additional
upper bounds; they do not promise that every order within them fits this small model.

## Local cleanup

Remove only the named sample container:

```bash
docker stop cookbook-qwen-local
docker rm cookbook-qwen-local
```

Make sure that port 18086 closes and the exact container is absent.
Remove the temporary image only after all owned containers stop:

```bash
docker image rm cookbook-qwen:local
```

## AI Core assets

serving-template.yaml listens on port 8080 with one infer.s replica.
Replace both placeholders in an ignored copy before review.
Review paid configuration and cost before provisioning approval.
consumer-deployment.yaml supplies a separate private Kyma consumer and mock MCP workload.
Build their shared image with the checked-in
[Dockerfile.model-consumer](../production-order-agent/Dockerfile.model-consumer)
using the [custom-model recipe's consumer build command](../../recipes/optional/bring-your-own-model/#custom-deployment-consumer).
It installs the frozen base dependencies for the OAuth-aware `aicore-custom`
provider; the optional foundation-model SDK belongs to the standard Dockerfile.
Use the reviewed registry manifest digest of this consumer image in both agent
and MCP image placeholders in an ignored copy of consumer-deployment.yaml.
It references an existing application Secret and an existing registry Secret.
It changes no shared chart, backend, namespace, or public endpoint.
Replace every placeholder and review its exact objects before deployment approval.
See the [custom-model recipe](../../recipes/optional/bring-your-own-model/) for the live gates and cleanup boundaries.

## Serving boundary

The server exposes only a private development endpoint or the AI Core authenticated ingress.
The image disables the web UI, remote HTTPS downloads, and subprocess support.
It loads the verified 986048512-byte GGUF at runtime without a download.
The server implements `/v1/chat/completions`; it does not implement Ollama management routes.
[llama.cpp server documentation](https://github.com/ggml-org/llama.cpp/blob/8642541b255bfb5dc39cd351a178be09013a55d6/tools/server/README.md) defines the health and inference routes.
