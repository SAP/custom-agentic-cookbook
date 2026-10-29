---
id: deploy-btp
title: Deploy to an existing Kyma cluster
description: Deploy the mock production-order agent and its private MCP service.
prerequisites: [scaffold-agent]
intended_platform: [kyma]
category: checkpoint
status: experimental
---

# Deploy the sample to an existing Kyma cluster

> Guided: Ask your coding agent: "Prepare the production-order sample for my existing Kyma cluster."
> Input: The [Python sample](../../samples/production-order-agent/), an approved cluster, and a registry that the cluster can read.
> Output: A deployed mock agent and private MCP service that return a real business reply.

This recipe deploys the checked-in production-order sample from checkpoint 1.
Helm packages the Kubernetes resources in a chart.
The chart runs the agent on port 8000 and MCP on port 8090.
Both use the same image digest, which identifies immutable image content.
Both data and model providers stay `mock`.
The agent uses one replica because task state stays in memory.

This path requires an existing Kyma cluster.
It does not provision BTP, configure CF, or deploy toolkit-generated projects.
Model-enabled, HANA, and live-data deployments need separate configuration and tests.
The [minimal A2A sample](../../samples/fde-a2a-minimal/) remains the protocol reference.

Both services provide no application authentication.
Keep the default services inside the cluster.
ClusterIP limits exposure but does not authenticate callers within the cluster.
The optional public route is an explicit development test.
It does not provide production authentication.

## Prepare the local sample

Install Docker, Python 3.12 or newer, [uv](https://docs.astral.sh/uv/), kubectl, and Helm 3.
Start from a clean Cookbook clone.
From its root, install and test the sample:

```bash
cd samples/production-order-agent
uv sync --frozen --group dev
uv run --frozen pytest -q
docker build --platform linux/amd64 --file Dockerfile.mock --tag production-order-agent:kyma-smoke .
```

Use the sample's [Compose flow](../../samples/production-order-agent/) to start both processes locally.
Send a real A2A message:

```bash
uv run --frozen python scripts/smoke_a2a.py --base-url http://127.0.0.1:8000
```

Require `TASK_STATE_COMPLETED`, Released, Partially Confirmed, operations 0010 and 0020, and a potential delay for operation 0020.
An Agent Card alone does not prove this result.
Stop the local Compose processes after the test.

## Repeat the container acceptance test

From the sample directory, obtain the immutable local image ID:

```bash
docker image inspect production-order-agent:kyma-smoke --format '{{.Id}}'
```

Set `TEST_IMAGE_ID` to that output. Test the exact image:

```bash
uv run --frozen python scripts/verify_container.py --image "$TEST_IMAGE_ID"
```

The test starts the agent and MCP in separate containers.
Only the agent receives a loopback port.
The test requires the business reply and a failed task after MCP stops.
It also requires UID 10001, zero capabilities, and the default seccomp filter.
The test removes its exact containers and network, then requires the port to close.
It does not remove the image or change a cluster.
Use a separate image that matches the node architecture for other targets.

## Select and approve the target

Obtain the cluster context, delegated namespace, release name, and approved image repository.
Obtain the name of an existing image-pull Secret if the registry requires authentication.
Keep its credentials outside values files and chat.
Approve image publication, namespace creation, installation, public exposure, and cleanup as separate actions.
Do local preparation before requesting those approvals.
Do not reuse a shared namespace or release without its owner's approval.

Set the approved values in the terminal for the live steps:

```bash
export KYMA_CONTEXT=your-approved-context
export KYMA_NAMESPACE=your-approved-test-namespace
export KYMA_RELEASE=production-order-smoke
export KYMA_IMAGE_REPOSITORY=registry.example.com/your-team/production-order-agent
export KYMA_IMAGE_TAG=your-reviewed-build-tag
```

Replace every example with the approved value.
Select an image architecture supported by the cluster nodes.
The example registry is not a working publication target.
After image-push approval, publish the tested image:

```bash
docker tag production-order-agent:kyma-smoke "$KYMA_IMAGE_REPOSITORY:$KYMA_IMAGE_TAG"
docker push "$KYMA_IMAGE_REPOSITORY:$KYMA_IMAGE_TAG"
```

Record the registry digest from the successful push.
Set `KYMA_IMAGE_DIGEST` to that exact `sha256:` value.
From the Cookbook root, create the local deployment values:

```bash
cat > /tmp/production-order-kyma-values.yaml <<EOF
image:
  repository: "$KYMA_IMAGE_REPOSITORY"
  tag: "$KYMA_IMAGE_TAG"
  digest: "$KYMA_IMAGE_DIGEST"
imagePullSecrets: []
replicaCount: 1
apirule:
  enabled: false
EOF
helm lint charts/production-order-agent -f /tmp/production-order-kyma-values.yaml
helm template "$KYMA_RELEASE" charts/production-order-agent --namespace "$KYMA_NAMESPACE" -f /tmp/production-order-kyma-values.yaml > /tmp/production-order-kyma-rendered.yaml
```

For a private registry, put only the existing Secret name in `imagePullSecrets`.
The Secret must exist in the selected namespace.
Review the rendered image, namespace, commands, private MCP URL, and exposure before installation.
Both application containers run as UID/GID 10001, drop capabilities, and prevent privilege escalation.
They receive no service-account token.

## Install after approval

After read-only cluster access approval, inspect the selected namespace:

```bash
kubectl --context "$KYMA_CONTEXT" get namespace "$KYMA_NAMESPACE"
kubectl --context "$KYMA_CONTEXT" -n "$KYMA_NAMESPACE" get deployments,services
```

If the namespace is absent, obtain creation approval before proceeding.
Use the selected context in every cluster command.
After deployment approval, install the reviewed chart:

```bash
helm upgrade --install "$KYMA_RELEASE" charts/production-order-agent --kube-context "$KYMA_CONTEXT" --namespace "$KYMA_NAMESPACE" -f /tmp/production-order-kyma-values.yaml --wait --timeout 5m
kubectl --context "$KYMA_CONTEXT" -n "$KYMA_NAMESPACE" get deployments,pods,services -l "app.kubernetes.io/instance=$KYMA_RELEASE"
```

Agent readiness uses its Agent Card.
MCP readiness tests its TCP port because the service provides no health route.
These probes do not replace the business test.

## Test the deployed business reply

Find the agent Service name in the preceding output.
Forward that Service to loopback in one terminal:

```bash
export KYMA_AGENT_SERVICE=your-rendered-agent-service-name
kubectl --context "$KYMA_CONTEXT" -n "$KYMA_NAMESPACE" port-forward --address 127.0.0.1 "service/$KYMA_AGENT_SERVICE" 18000:8000
```

In a second terminal, run the smoke command from the sample directory:

```bash
cd samples/production-order-agent
uv run --frozen python scripts/smoke_a2a.py --base-url http://127.0.0.1:18000
```

Require the same completed business reply as the local test.
The deployed agent must call its deployed MCP service.
Keep MCP without an APIRule, LoadBalancer, or NodePort.
Stop port-forward with Ctrl+C after the test.

## Optional public development route

For a public test, require Kyma API Gateway and Istio.
Approve the exact hostname and unauthenticated public exposure before changing the values.
Set `apirule.enabled: true`, `apirule.host`, and `apirule.noAuth: true` in the local values file.
Use the approved gateway reference in `apirule.gateway`.
Render and review the change before repeating the approved Helm deployment.

The chart exposes only the agent through APIRule v2 at `/{**}`.
It permits GET and POST for the Agent Card and A2A messages.
MCP stays inside the cluster.
After the APIRule becomes ready, run the business smoke command against its HTTPS URL.
Record its completed task and business artifact.
A port-forward result does not prove the public checkpoint.

## Troubleshooting and cleanup

If the image cannot start, make sure that its architecture matches the cluster nodes.
Make sure that the repository, tag, digest, and pull-Secret name match the approved image.
If the business test fails, inspect both deployments and their private MCP URL.
Use the selected context and namespace when reading pod status or logs.
Do not share credentials or complete environment files.
If the APIRule fails, make sure that the gateway, host, API Gateway, and Istio support APIRule v2.

Approve removal of the exact test release before uninstalling it:

```bash
helm uninstall "$KYMA_RELEASE" --kube-context "$KYMA_CONTEXT" --namespace "$KYMA_NAMESPACE" --wait
kubectl --context "$KYMA_CONTEXT" -n "$KYMA_NAMESPACE" get deployments,services,apirules -l "app.kubernetes.io/instance=$KYMA_RELEASE"
```

Make sure that the release resources and optional public route are absent.
Preserve existing namespaces, pull Secrets, and shared services.
Delete a new test namespace or registry image only after separate approval for that exact resource.
Remove the local values and rendered files after the test.

This recipe remains experimental until the selected live path and cleanup pass.
Joule, HANA, model-enabled deployment, Cloud Logging, and GitOps require their own implementation and tests.
