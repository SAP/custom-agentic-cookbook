# Minimal Python A2A v1.0 sample

> **Status:** Experimental reference. This sample is supporting
> evidence for the Cookbook's local-agent milestone; it does not replace the
> supported scaffold flow in [`recipes/01-scaffold-agent`](../../recipes/01-scaffold-agent/).

This credential-free sample exposes a Hello World agent through A2A v1.0. It
demonstrates the smallest useful server shape: an Agent Card, an in-memory task
store, and a synchronous `SendMessage` request that returns an artifact.

The sample intentionally excludes an LLM, business tools, authentication,
persistence, streaming, and push notifications. It includes a container and a
small Helm chart for deployment experiments, but it is not a production agent.

## Prerequisites

- Python 3.12 or newer
- [`uv`](https://docs.astral.sh/uv/)
- `curl` and `jq` for the manual smoke test
- Docker for the container path
- Helm 3 and access to a Kubernetes cluster for the deployment path

## Run locally

From this directory:

```bash
uv sync --frozen
uv run --frozen python -m app
```

The server listens on `http://127.0.0.1:8000`. Set `HOST`, `PORT`, or `URL` to
override the bind address, port, or public URL advertised by the Agent Card.

## Verify it works

In another terminal, set the base URL and fetch the Agent Card:

```bash
BASE_URL=http://127.0.0.1:8000
curl -s "$BASE_URL/.well-known/agent-card.json" | jq .name
```

Expected result:

```text
"Hello World Agent"
```

Then send a real A2A message:

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
        "parts": [{"text": "hi"}]
      }
    }
  }' | jq
```

The response should contain a completed task with a `Hello, World!` artifact.

## Run the tests

```bash
uv run --frozen --group dev pytest
```

## Build and run the container

Choose a registry-neutral image name and a descriptive tag, such as a Git
commit SHA:

```bash
IMAGE_REPOSITORY=registry.example.com/team/fde-a2a-minimal
IMAGE_TAG=git-0123456789ab

docker build -t "$IMAGE_REPOSITORY:$IMAGE_TAG" .
docker run --rm -p 8000:8000 "$IMAGE_REPOSITORY:$IMAGE_TAG"
```

Run the Agent Card and `SendMessage` checks above against
`http://127.0.0.1:8000`. The image runs as non-root UID and GID `999`, listens
on port `8000`, and accepts `HOST`, `PORT`, and `URL` overrides.

To publish a multi-architecture image to your chosen registry:

```bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --tag "$IMAGE_REPOSITORY:$IMAGE_TAG" \
  --push .

docker buildx imagetools inspect "$IMAGE_REPOSITORY:$IMAGE_TAG"
IMAGE_DIGEST=sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
```

Replace the example `IMAGE_DIGEST` with the top-level manifest digest printed
by `imagetools inspect`. The chart requires this digest and renders
`repository:tag@digest`, so the deployed image content cannot change even if
someone later reuses the tag. The chart also rejects `latest` to keep the
human-readable tag meaningful.

## Deploy with Helm

The [`hello-world` chart](../../charts/hello-world/) keeps the service
cluster-local by default. It is fixed at one replica because task state is held
in memory and is not shared between pods. From this sample directory, install
a public image with:

```bash
helm upgrade --install hello-world ../../charts/hello-world \
  --namespace fde-a2a-minimal --create-namespace \
  --set-string image.repository="$IMAGE_REPOSITORY" \
  --set-string image.tag="$IMAGE_TAG" \
  --set-string image.digest="$IMAGE_DIGEST"
```

For a private image, first create a `kubernetes.io/dockerconfigjson` Secret in
the target namespace from a registry-specific Docker configuration file. Keep
that file and its credentials out of source control:

```bash
kubectl create namespace fde-a2a-minimal

kubectl --namespace fde-a2a-minimal create secret generic registry-credentials \
  --type=kubernetes.io/dockerconfigjson \
  --from-file=.dockerconfigjson=/path/to/registry-specific-config.json

helm upgrade --install hello-world ../../charts/hello-world \
  --namespace fde-a2a-minimal \
  --set-string image.repository="$IMAGE_REPOSITORY" \
  --set-string image.tag="$IMAGE_TAG" \
  --set-string image.digest="$IMAGE_DIGEST" \
  --set-string 'imagePullSecrets[0]=registry-credentials'
```

Skip the namespace creation command if the namespace already exists.

The chart references existing pull Secrets by name and never accepts or
creates registry credentials.

### Verify the cluster-local deployment

Wait for the Deployment, then forward the Service to your workstation:

```bash
kubectl --namespace fde-a2a-minimal rollout status deployment/hello-world
kubectl --namespace fde-a2a-minimal port-forward service/hello-world 8000:8000
```

In another terminal, repeat the Agent Card and `SendMessage` checks above. The
Agent Card advertises the cluster-local Service URL even though port forwarding
is used for this verification.

### Optional public development endpoint

Kyma users can explicitly add an APIRule v2 endpoint to an existing release:

```bash
PUBLIC_HOST=fde-a2a-minimal.example.com

helm upgrade hello-world ../../charts/hello-world \
  --namespace fde-a2a-minimal --reuse-values \
  --set apirule.enabled=true \
  --set-string apirule.host="$PUBLIC_HOST" \
  --set apirule.noAuth=true
```

> **Security warning:** `apirule.noAuth=true` makes the agent publicly
> accessible without authentication. Use it only for a temporary development
> or smoke test, never for production. The chart requires that choice to be
> explicit and otherwise remains cluster-local.

The exposed Agent Card advertises `https://$PUBLIC_HOST`. Verify both the card
and a real A2A reply with the earlier commands after setting
`BASE_URL="https://$PUBLIC_HOST"`.

## Clean up

Remove the Helm release. If the namespace was created only for this sample,
delete it as well; that also removes any pull Secret in the namespace:

```bash
helm uninstall hello-world --namespace fde-a2a-minimal
kubectl delete namespace fde-a2a-minimal
```

Delete the pushed image tag from the registry using that registry's documented
deletion workflow.
