---
name: sap-kyma-cli
description: Use this skill for Kyma (BTP Kubernetes) deployment flows used by this cookbook — containerizing the agent template, applying k8s manifests, exposing via APIRule, and switching auth from noop to JWT/IAS. Complements the upstream `kyma-cli` skill at skills.cloud.sap.
---

# SAP Kyma CLI — agent-deploy patterns

The canonical agent template ships a `Containerfile` and `k8s/` directory. Kyma deployment is `podman build && podman push && kubectl apply -f k8s/`.

## Setup

```bash
# kubeconfig comes from BTP cockpit (kyma env instance → Kubeconfig URL)
export KUBECONFIG=/path/to/kubeconfig.yaml
kubectl get nodes              # smoke
```

## Build & push

```bash
podman build -f Containerfile -t my-first-agent:0.1.0 .
podman tag  my-first-agent:0.1.0 $REGISTRY/my-first-agent:0.1.0
podman push $REGISTRY/my-first-agent:0.1.0
```

In sovereign regions, $REGISTRY must be in-region — DockerHub is blocked. Use the customer's ACR / ECR / harbor.

## Deploy

```bash
# Provide AI Core credentials as a secret (NEVER bake into the image).
kubectl create secret generic aicore-credentials \
  --from-env-file=.env.aicore

kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/apirule.yaml

kubectl get apirule my-first-agent -o jsonpath='{.status.virtualService}'
```

## Switch to JWT/IAS auth

In `k8s/apirule.yaml` swap:

```yaml
accessStrategies:
  - handler: noop
```

to:

```yaml
accessStrategies:
  - handler: jwt
    config:
      trusted_issuers:
        - "https://<your-ias-tenant>.accounts.ondemand.com"
      jwks_urls:
        - "https://<your-ias-tenant>.accounts.ondemand.com/oauth2/certs"
```

The Agent Card and `/healthz` rules should stay `noop` — discovery and liveness must be public.

## Pitfalls

- ImagePullBackOff in sovereign region → registry not whitelisted; switch to in-region registry.
- APIRule pending → cluster's `kyma-system/kyma-gateway` not ready; wait, then check.
- Forgetting `envFrom: secretRef: aicore-credentials` → 401 from AI Core at runtime.
- HPA without resource requests on the deployment → no scaling.

## Verify

```bash
kubectl rollout status deployment/my-first-agent
curl -s https://my-first-agent.<cluster-domain>/.well-known/agent.json | jq .name
```

## Cross-references

- Upstream: `kyma-cli` skill at skills.cloud.sap
- Deploy walkthrough: [`recipes/01-deploy/00-deploy-cf-or-kyma/`](../../recipes/01-deploy/00-deploy-cf-or-kyma/) (covers both runtimes; the Kyma branch is what applies here)
