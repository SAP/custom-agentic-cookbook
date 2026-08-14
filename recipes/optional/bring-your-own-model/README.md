# Optional: Bring Your Own Model on SAP AI Core

> **Flow:** model-tier **branch** — replaces the default catalog model behind `--llm-provider aicore`. Requires the `aicore` path confirmed for the region ([02-deploy-btp step 0](../../02-deploy-btp/) or [region-preflight](../region-preflight/)). Rejoins the happy path at **[02-deploy-btp](../../02-deploy-btp/)**.
> **Input:** the `--llm-provider aicore` decision + AI Core entitlement confirmation (from **[optional/region-preflight](../region-preflight/)** or **02-deploy-btp** step 0), plus a container registry reachable from AI Core and a Git repo connected to AI Core for ServingTemplate manifests.
> **Output:** a `byom-agent/` CAP + HANA task-store scaffold pointed at a RUNNING AI Core deployment (custom `ollama.yaml` ServingTemplate, `<registry>/<namespace>/ollama:ai-core` image, reachable via `AICORE_BASE_URL/v2/lm/deployments/<deployment-id>`) — consumed by **[02-deploy-btp](../../02-deploy-btp/)** for deploy.
> **Toolkit command:** `/sap-a2a-agent-toolkit:create-agent byom-agent --framework cap --taskstore hana --llm-provider aicore`.

Use this when a customer wants to host a custom LLM behind SAP AI Core, for example Ollama serving Gemma, and the target subaccount already has SAP AI Core entitlement and quota.

> ⚠ Region: This is an SAP AI Core recipe. Use it only where AI Core is listed and entitled, such as commercial regions or KSA regulated after preflight. For China Landing, NS2, and KSA non-regulated, use [`recipes/optional/sovereign-model-gateway/`](../sovereign-model-gateway/) with `--llm-provider openai-compatible` against a customer-approved gateway.

## When to use it

- You need to serve a model that is not available in the foundation-model catalog.
- The customer accepts running the model as an AI Core custom serving deployment.
- The image registry, model source, and runtime path are approved for the target region.

Do not use this to bypass regional availability. If AI Core is not in-region, keep the agent on `openai-compatible` instead.

## Prerequisites

- SAP AI Core standard or extended plan entitlement and quota.
- SAP AI Launchpad access for repository, application, configuration, and deployment setup.
- Container registry reachable from SAP AI Core.
- Docker access token or customer-approved registry credentials stored as an AI Core Docker registry secret.
- Git repository connected to AI Core for workflow templates.
- Region preflight completed: [`recipes/optional/region-preflight/`](../region-preflight/).

## Scaffold

Create the consuming A2A agent with the AI Core provider only after preflight confirms AI Core for the subaccount:

```bash
/sap-a2a-agent-toolkit:create-agent byom-agent \
  --framework cap \
  --taskstore hana \
  --landscape <landscape> \
  --llm-provider aicore
```

Fallback for sovereign regions without AI Core:

```bash
/sap-a2a-agent-toolkit:create-agent byom-agent \
  --framework cap \
  --taskstore hana \
  --landscape <landscape> \
  --llm-provider openai-compatible
```

## Configure

Add a serving template to the repository path that AI Core watches, for example `LearningScenarios/ollama.yaml`:

```yaml
apiVersion: ai.sap.com/v1alpha1
kind: ServingTemplate
metadata:
  name: ollama
  annotations:
    scenarios.ai.sap.com/description: "Run an Ollama server on SAP AI Core"
    scenarios.ai.sap.com/name: "ollama"
    executables.ai.sap.com/description: "ollama service"
    executables.ai.sap.com/name: "ollama"
  labels:
    scenarios.ai.sap.com/id: "ollama"
    ai.sap.com/version: "0.0.1"
spec:
  template:
    apiVersion: "serving.kserve.io/v1beta1"
    metadata:
      annotations: |
        autoscaling.knative.dev/metric: concurrency
        autoscaling.knative.dev/target: 1
        autoscaling.knative.dev/targetBurstCapacity: 0
      labels: |
        ai.sap.com/resourcePlan: infer.s
    spec: |
      predictor:
        imagePullSecrets:
          - name: <docker-secret-name>
        minReplicas: 1
        maxReplicas: 1
        containers:
          - name: kserve-container
            image: <registry>/<namespace>/ollama:ai-core
            ports:
              - containerPort: 8080
                protocol: TCP
```

Build and push the Ollama image from the SAP tutorial, substituting the customer-approved registry:

```bash
docker login <registry>
docker build --platform=linux/amd64 -t <registry>/<namespace>/ollama:ai-core .
docker push <registry>/<namespace>/ollama:ai-core
```

In SAP AI Launchpad:

1. Add the Docker registry secret.
2. Add the Git repository path that contains `LearningScenarios/ollama.yaml`.
3. Create an AI Core application from that path.
4. Create a configuration with `scenario_id=ollama` and `executable_id=ollama`.

## Deploy

Create the deployment from the AI Core configuration and wait until it is `RUNNING`.

Then pull the model into the Ollama deployment using the AI API endpoint exposed for that deployment. The SAP tutorial uses Gemma as the example model; choose the model only after customer approval of model license, residency, and quality.

## Verify it works

Confirm the deployment is running:

```bash
curl -s "$AICORE_BASE_URL/v2/lm/deployments/<deployment-id>" \
  -H "Authorization: Bearer $TOKEN" \
  -H "AI-Resource-Group: $AICORE_RESOURCE_GROUP" \
  | jq -r .status
```

Expect:

```text
RUNNING
```

Then send a minimal inference request through the deployment endpoint and confirm the A2A agent can call the configured AI Core deployment without falling back to a local `localhost` endpoint.

## Troubleshooting

- `ImagePullBackOff`: check the AI Core Docker registry secret, registry host, image tag, and whether the registry is reachable from the region.
- `403` from AI API: check `AI-Resource-Group`, token audience, service binding, and whether the application/configuration belongs to the same resource group.
- Deployment starts but inference fails: confirm Ollama listens on port `8080` through the reverse proxy and the model was pulled into the running deployment.

## Cleanup or rollback

- Stop or delete the AI Core deployment when not in active use.
- Delete unused configurations and applications from SAP AI Launchpad.
- Remove registry credentials that were created only for the pilot.
- Keep the A2A agent source; switch it back to `--llm-provider openai-compatible` if the region cannot run AI Core.

## Region-specific notes

- Commercial: use this when AI Core entitlement, quota, and customer residency approval are in place.
- KSA regulated: viable only after preflight confirms AI Core in the customer subaccount; validate NDMO residency and Arabic-language quality.
- China Landing, NS2, KSA non-regulated: use [`recipes/optional/sovereign-model-gateway/`](../sovereign-model-gateway/) instead.

## Changes under BAIP

When BAIP is available in the target region, replace the custom AI Core deployment path with the BAIP-native model onboarding path. Keep the A2A endpoint, HANA task store, tool APIs, and regional preflight workflow.

## Source

- SAP Developers tutorial: [Using Custom models on SAP AI Core VIA ollama](https://developers.sap.com/tutorials/ai-core-custom-llm..html).
- Regional availability guardrail: run [`recipes/optional/region-preflight/`](../region-preflight/) against the target subaccount.
