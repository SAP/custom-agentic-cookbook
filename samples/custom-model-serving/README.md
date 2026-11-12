# Pinned local model for the gateway smoke test

Build the checked-in Qwen2.5 1.5B CPU image from the Cookbook root:

```bash
docker build --platform linux/amd64 -t cookbook-qwen:local samples/custom-model-serving
docker build --platform linux/amd64 -f samples/production-order-agent/Dockerfile.model-consumer -t cookbook-gateway:local samples/production-order-agent
python3 samples/production-order-agent/scripts/smoke_gateway_bridge.py --model-image cookbook-qwen:local --consumer-image cookbook-gateway:local
```

Docker and Python 3.12 or newer are required. The model build downloads about
986 MB from public sources. Its checked-in manifest, blob sizes and SHA-256
digests pin the model. The Dockerfile pins the base images and llama.cpp source
commit and verifies its source archive. The runtime contains only the CPU
server, libraries, model and upstream licenses. Qwen uses Apache-2.0;
llama.cpp uses MIT. Review their licenses before redistribution.

The smoke command resolves both local image tags to immutable image IDs.
It starts uniquely owned non-root containers with CPU/memory limits, dropped
capabilities and no-new-privileges. All test traffic stays in their isolated
network namespace; the command publishes no host port and creates no cloud
resource. Runtime requires no model download.

The [gateway recipe](../../recipes/optional/sovereign-model-gateway/#validated-local-model-path)
describes the eight business, refusal and recovery checks. OAuth and S/4 data
are synthetic; model inference is real. The bridge rejects model output that
does not match the backend-derived status, operation and delay fields.

Direct free-text Qwen gateway summaries failed the business-accuracy check.
Use the structured bridge smoke above for this pinned small model. Generic
gateway transport support alone does not establish accuracy for another model.

The command stops and removes only its own containers and requires all helper
ports to close. Remove the two temporary build tags when they are no longer
needed:

```bash
docker image rm cookbook-qwen:local cookbook-gateway:local
```

This local validation does not prove AI Core deployment, real OAuth, sovereign
residency, managed capacity, deployed recovery or production readiness.
Cloud deployment belongs to a separately reviewed recipe and environment.

[llama.cpp server documentation](https://github.com/ggml-org/llama.cpp/blob/8642541b255bfb5dc39cd351a178be09013a55d6/tools/server/README.md)
defines the health and OpenAI-compatible inference routes used here.
