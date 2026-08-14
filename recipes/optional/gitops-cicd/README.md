---
title: "Reproducible Kyma GitOps CI/CD"
sap-services: [BTP Kyma runtime, SAP BTP Operator, SAP Credential Store, Destination Service, XSUAA, HANA Cloud]
region-availability:
  - region: commercial
    kyma: yes
  - region: china-kyma
    kyma: yes
    notes: "China Shanghai and China North 3 list Kyma; validate tenant entitlement before choosing the Kyma route."
  - region: ns2
    kyma: yes
    notes: "Use tenant-issued API and domain names; do not hardcode commercial hostnames."
  - region: ksa
    kyma: yes
complexity: recipe
last-validated: draft
changes-under-baip: "The GitOps, image-tag, namespace, and service-boundary patterns should survive; model and service bindings may move to BAIP-native resources."
---

# Optional: Reproducible Kyma GitOps CI/CD

> **Flow:** GitOps **replacement** for **[02-deploy-btp](../../02-deploy-btp/)**'s manual `cf push` / `helm upgrade` — same input project, reconciled by Argo CD instead of pushed by hand. Downstream [03-joule](../../03-joule/) and wip/observe-and-eval still apply against the Argo-managed URL.
> **Input:** the agent repo from **[01-scaffold-agent](../../01-scaffold-agent/)** (or a branch: optional/connect-data / optional/sovereign-model-gateway / wip/hana-vector-store / wip/hana-kg-triple-store / optional/bring-your-own-model) — the same Output that 02-deploy-btp would consume — plus a Kyma cluster with API Gateway + Istio + BTP Operator.
> **Output:** a platform repo (`clusters/<cluster-id>/`) with Sealed Secrets, ARC, Argo CD, AppProjects, and BTP Operator bindings; an app repo with Helm/Kustomize deploy state, `.github/workflows/ci.yml` + `deploy.yml`, and an Argo CD `Application` per environment — reconciled agent URL feeds **03-joule and wip/observe-and-eval**.
> **Toolkit command:** none — this recipe wraps the artifact emitted by `/sap-a2a-agent-toolkit:create-agent` (upstream) and substitutes for `/sap-a2a-agent-toolkit:deploy-agent` from 02-deploy-btp.

Use this recipe when a regional team needs a reproducible Kyma deployment path
for an A2A agent repository: pull request checks, container smoke, immutable
image push, Git deployment-state update, and Argo CD reconciliation.

This recipe is designed to be copied into a customer-owned delivery setup. It
uses placeholders for cluster IDs, Git organizations, repository URLs, and
project names so the same structure can be applied without exposing
environment-specific details.

> ⚠ Region: Kyma is not universal across all BTP landscapes, but it is listed
> for both China Shanghai (`cn40`) and China North 3 (`cn41`) in the
> 2026-07-07 Discovery Center check. SAP AI Core is listed for KSA regulated
> only among the sovereign targets in scope. Run
> [`recipes/optional/region-preflight/`](../region-preflight/) to confirm both
> against the customer's actual subaccount before choosing `kyma` or `aicore`.

## When to use it

Use this recipe when:

- the target runtime is Kyma
- the team wants GitOps rather than direct `kubectl apply` from a laptop
- application code and deployment manifests live in the application repository
- a platform team owns shared prerequisites such as namespaces, registry access,
  Argo CD project policy, and secret backends

Use `recipes/02-deploy-btp/` first if the team only needs a manual
Cloud Foundry or Kyma deployment. Use this recipe once the deployment should be
repeatable through CI/CD.

## Prerequisites

Bootstrap prerequisites:

- Kyma runtime enabled and reachable with `kubectl`
- Kyma API Gateway and Istio modules available if anything will be exposed with
  `gateway.kyma-project.io/v2` APIRule
- local tools: `kubectl`, `helm`, `kubeseal`, `gh`, `jq`, and `curl`
- a known cluster domain, such as `<cluster-domain>`
- a platform Git repository for cluster bootstrap and ongoing GitOps state
- a GitHub App, bot, or equivalent credential that lets Actions Runner
  Controller register self-hosted runners
- a Git read credential for Argo CD, preferably a GitHub App or equivalent
- container registry reachable from the Kyma cluster
- registry push credentials available to CI/CD workflows
- registry pull credentials available to Kyma namespaces that run private images
- BTP Operator and Credential Store entitlement if the platform will create
  `ServiceInstance` and `ServiceBinding` resources for runtime secrets
- access to approved Helm chart and container image sources. If the landscape
  cannot pull from public chart/image registries, mirror the ARC, Argo CD,
  Sealed Secrets, and smoke-test images first.

Repository prerequisites:

- A2A agent exposes an Agent Card endpoint
- Dockerfile builds the agent image
- deployment state lives under one path, such as `deploy/helm/` or
  `deploy/k8s/overlays/dev/`
- runtime secrets are referenced by Kubernetes Secret names, not committed
- PR CI can run without real customer credentials by using mock or safe mode

## Platform repository layout

Use one platform repository as the source of truth for cluster-owned resources.
Keep the cluster name generic and region-specific:

```text
platform-repo/
clusters/<cluster-id>/
  arc/
    controller-values.yaml
    runner-scale-set-values.yaml
  argocd/
    root-application.yaml
    app-projects.yaml
    applicationsets/
      dev-apps.yaml
  namespaces/
    <agent-namespace>.yaml
  credential-store/
    catalog.yaml
    service-instance.yaml
    <project>-bindings.yaml
  sealed-secrets/
    certs/pub-cert.pem
    arc-runners/arc-runner-auth.yaml
    argocd/repo-creds.yaml
    namespaces/<agent-namespace>/<image-pull-secret>.yaml
  kustomization.yaml
```

The platform repository owns namespaces, Argo CD, Argo AppProjects,
ApplicationSets, image-pull credentials, and shared secret backends. The app
repository owns the application Deployment, Service, optional APIRule, tests,
Dockerfile, and CI/CD workflows.

## Application repository layout

Helm option:

```text
Dockerfile
.github/workflows/ci.yml
.github/workflows/deploy.yml
.github/scripts/smoke-a2a.py
src/
deploy/helm/
  Chart.yaml
  values.yaml
  references/
```

Kustomize option:

```text
Dockerfile
.github/workflows/ci.yml
.github/workflows/deploy.yml
.github/scripts/smoke-a2a.py
src/
deploy/k8s/base/
  deployment.yaml
  service.yaml
  kustomization.yaml
deploy/k8s/overlays/dev/
  deployment-patch.yaml
  kustomization.yaml
```

The application repository owns only application resources: Deployment, Service,
APIRule if it is part of the app contract, and optional ServiceInstance /
ServiceBinding resources when the platform allows app-owned BTP services.

The platform repository or platform automation should own cluster-wide policy,
namespaces, Argo CD installation, Argo CD AppProjects, repository credentials,
registry pull credentials, and shared secret backends.

## Platform Step 0 - Verify Kyma Modules

Before installing the CI/CD platform, confirm the cluster has the Kyma APIs this
recipe depends on:

```bash
kubectl get crd apirules.gateway.kyma-project.io
kubectl get ns kyma-system
kubectl get svc -n kyma-system kyma-gateway
```

If these fail, enable the Kyma API Gateway and Istio modules through the
customer's Kyma administration process before continuing. APIRule v2 is the
expected API shape:

```bash
kubectl explain apirule.spec.rules.noAuth
```

## Platform Step 1 - Install Sealed Secrets

Use Sealed Secrets for bootstrap credentials, image-pull credentials, and any
simple or legacy Kubernetes Secret path. For runtime app secrets, prefer SAP
Credential Store or the customer's standard secret backend.

```bash
helm repo add sealed-secrets https://bitnami-labs.github.io/sealed-secrets
helm repo update

helm upgrade --install sealed-secrets sealed-secrets/sealed-secrets \
  --namespace kube-system \
  --version <sealed-secrets-chart-version> \
  --wait \
  --timeout 5m
```

Fetch only the public sealing certificate into the platform repo. Back up the
controller private key securely outside Git.

```bash
mkdir -p clusters/<cluster-id>/sealed-secrets/certs
kubectl get secret \
  -n kube-system \
  -l sealedsecrets.bitnami.com/sealed-secrets-key \
  -o jsonpath='{.items[0].data.tls\.crt}' \
  | base64 -d > clusters/<cluster-id>/sealed-secrets/certs/pub-cert.pem
```

A SealedSecret is bound to the controller key and, by default, the target
Secret namespace/name. Reseal bootstrap, repo-credential, and image-pull secrets
whenever the cluster, Sealed Secrets controller key, namespace, or Secret name
changes.

## Platform Step 2 - Install Actions Runner Controller

Install the ARC scale-set controller and one shared runner scale set. Regional
teams can start with one shared runner label and split later if isolation,
capacity, or ownership requires it.

Create the runner auth Secret manifest from the approved Git registration
credential, seal it with the cluster public certificate, and commit only the
SealedSecret. If the credential is a token, make sure the token value does not
include a trailing newline before sealing it.

```bash
kubectl create namespace arc-systems --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace arc-runners --dry-run=client -o yaml | kubectl apply -f -

mkdir -p clusters/<cluster-id>/sealed-secrets/arc-runners
kubectl create secret generic arc-runner-auth \
  --namespace arc-runners \
  --from-literal=github_app_id=<runner-github-app-id> \
  --from-literal=github_app_installation_id=<runner-github-app-installation-id> \
  --from-file=github_app_private_key=<path-to-runner-github-app-private-key.pem> \
  --dry-run=client -o yaml \
  | kubeseal \
      --cert clusters/<cluster-id>/sealed-secrets/certs/pub-cert.pem \
      --format yaml \
  > clusters/<cluster-id>/sealed-secrets/arc-runners/arc-runner-auth.yaml

kubectl apply -f clusters/<cluster-id>/sealed-secrets/arc-runners/arc-runner-auth.yaml
kubectl get secret arc-runner-auth -n arc-runners
```

Install the controller and runner scale set:

```bash
helm upgrade --install arc \
  oci://ghcr.io/actions/actions-runner-controller-charts/gha-runner-scale-set-controller \
  --namespace arc-systems \
  --version <arc-chart-version> \
  --set replicaCount=1 \
  --wait \
  --timeout 5m

helm upgrade --install <runner-label> \
  oci://ghcr.io/actions/actions-runner-controller-charts/gha-runner-scale-set \
  --namespace arc-runners \
  --version <arc-chart-version> \
  --set githubConfigUrl=<github-org-or-enterprise-url> \
  --set githubConfigSecret=arc-runner-auth \
  --set minRunners=1 \
  --set maxRunners=3 \
  --set containerMode.type=dind \
  --set controllerServiceAccount.namespace=arc-systems \
  --set controllerServiceAccount.name=arc-gha-rs-controller \
  --wait \
  --timeout 5m
```

Validate:

```bash
kubectl get autoscalingrunnersets,ephemeralrunnersets,ephemeralrunners -n arc-runners
```

## Platform Step 3 - Install Argo CD

Install Argo CD into `argocd`. Label the namespace for Istio injection before
creating APIRules.

```bash
helm repo add argo https://argoproj.github.io/argo-helm
helm repo update

kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -
kubectl label namespace argocd istio-injection=enabled --overwrite

helm upgrade --install argocd argo/argo-cd \
  --namespace argocd \
  --version <argo-cd-chart-version> \
  --wait \
  --timeout 10m
```

Start with `kubectl port-forward` for bootstrap access:

```bash
kubectl port-forward -n argocd svc/argocd-server 8080:80
```

If the platform team deliberately exposes Argo CD through Kyma, create an
APIRule only with the customer's approved access policy. A temporary no-auth
APIRule may be acceptable for a restricted bootstrap network, but do not copy it
as an app-service default.

## Platform Step 4 - Give Argo CD Git Read Access

Argo CD needs read access to the platform repo and every app repo it will sync.
For GitHub Enterprise, a GitHub App repo-credential Secret keeps this reusable
across repositories in the same organization or URL prefix.

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: argocd-repo-creds
  namespace: argocd
  labels:
    argocd.argoproj.io/secret-type: repo-creds
stringData:
  type: git
  url: <git-url-prefix>
  githubAppID: "<argocd-github-app-id>"
  githubAppInstallationID: "<argocd-github-app-installation-id>"
  githubAppPrivateKey: |
    <argocd-github-app-private-key>
  githubAppEnterpriseBaseUrl: <github-enterprise-api-base-url>
```

For a fresh cluster, create the Secret manifest client-side, add the Argo CD
repo-credential label, then seal it. Do not commit the plaintext Secret:

```bash
mkdir -p clusters/<cluster-id>/sealed-secrets/argocd

kubectl create secret generic argocd-repo-creds \
  --namespace argocd \
  --from-literal=type=git \
  --from-literal=url=<git-url-prefix> \
  --from-literal=githubAppID=<argocd-github-app-id> \
  --from-literal=githubAppInstallationID=<argocd-github-app-installation-id> \
  --from-literal=githubAppEnterpriseBaseUrl=<github-enterprise-api-base-url> \
  --from-file=githubAppPrivateKey=<path-to-argocd-github-app-private-key.pem> \
  --dry-run=client -o yaml \
  | kubectl label --local -f - \
      argocd.argoproj.io/secret-type=repo-creds \
      -o yaml \
  | kubeseal \
      --cert clusters/<cluster-id>/sealed-secrets/certs/pub-cert.pem \
      --format yaml \
  > clusters/<cluster-id>/sealed-secrets/argocd/repo-creds.yaml

kubectl apply -f clusters/<cluster-id>/sealed-secrets/argocd/repo-creds.yaml
kubectl get secret -n argocd -l argocd.argoproj.io/secret-type=repo-creds
```

Before relying on ApplicationSet sync, verify the GitHub App, bot, or deploy key
behind this credential can read the platform repo and every application repo it
will sync. A valid Argo CD repo-credential Secret is not enough if the
credential has not been granted access to a specific repository.

## Platform Step 5 - Create Argo Projects And Root App

Create one AppProject for platform-owned resources and one for application
repos. The platform project may manage cluster-scoped resources such as
Namespaces. The application project should usually stay namespace-scoped.

```yaml
apiVersion: argoproj.io/v1alpha1
kind: AppProject
metadata:
  name: <platform-project>
  namespace: argocd
spec:
  sourceRepos:
    - <platform-repo-url>
  destinations:
    - namespace: "*"
      server: https://kubernetes.default.svc
  clusterResourceWhitelist:
    - group: ""
      kind: Namespace
  namespaceResourceWhitelist:
    - group: "*"
      kind: "*"
---
apiVersion: argoproj.io/v1alpha1
kind: AppProject
metadata:
  name: <apps-project>
  namespace: argocd
spec:
  sourceRepos:
    - <app-repo-url-prefix>/*
  destinations:
    - namespace: "*"
      server: https://kubernetes.default.svc
  clusterResourceBlacklist:
    - group: "*"
      kind: "*"
  namespaceResourceWhitelist:
    - group: "*"
      kind: "*"
```

Then create the root Application that lets Argo reconcile the platform repo:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: <platform-root-app>
  namespace: argocd
spec:
  project: <platform-project>
  source:
    repoURL: <platform-repo-url>
    targetRevision: main
    path: clusters/<cluster-id>
  destination:
    server: https://kubernetes.default.svc
    namespace: argocd
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=false
```

Save the AppProjects and root Application under `clusters/<cluster-id>/argocd/`,
apply them once, then let the root Application keep the platform state in sync:

```bash
kubectl apply -f clusters/<cluster-id>/argocd/app-projects.yaml
kubectl apply -f clusters/<cluster-id>/argocd/root-application.yaml
```

## Platform Step 6 - Add ApplicationSet Entries

ApplicationSet is the platform-owned routing table from app repo path to Kyma
namespace. It should stay boring: repo URL, branch, deploy path, namespace, and
Argo project.

```yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: <mode>-apps
  namespace: argocd
spec:
  generators:
    - list:
        elements:
          - name: <agent-name>-dev
            repo: <agent-repo-url>
            branch: main
            path: deploy/k8s/overlays/dev
            namespace: <namespace>
  template:
    metadata:
      name: "{{name}}"
    spec:
      project: <apps-project>
      source:
        repoURL: "{{repo}}"
        targetRevision: "{{branch}}"
        path: "{{path}}"
      destination:
        server: https://kubernetes.default.svc
        namespace: "{{namespace}}"
      syncPolicy:
        automated:
          prune: true
          selfHeal: true
        syncOptions:
          - CreateNamespace=false
          - PruneLast=true
```

Use `path: deploy/helm` for Helm-based app repos.

Add the ApplicationSet manifest to the platform repo and list it in
`clusters/<cluster-id>/kustomization.yaml` so the root Application owns it.

## Platform Step 7 - Create Namespaces And Image Pull Secrets

Create app namespaces in the platform repo, not in app overlays, unless the
platform explicitly delegates namespace ownership.

```bash
kubectl create namespace <namespace> --dry-run=client -o yaml \
  > clusters/<cluster-id>/namespaces/<namespace>.yaml
```

If the registry is private, create one image-pull Secret per namespace and seal
it into the platform repo:

```bash
mkdir -p clusters/<cluster-id>/sealed-secrets/namespaces/<namespace>
kubectl create secret docker-registry <image-pull-secret> \
  --namespace <namespace> \
  --docker-server=<registry-server> \
  --docker-username=<registry-username> \
  --docker-password=<registry-password> \
  --dry-run=client -o yaml \
  | kubeseal \
      --cert clusters/<cluster-id>/sealed-secrets/certs/pub-cert.pem \
      --format yaml \
  > clusters/<cluster-id>/sealed-secrets/namespaces/<namespace>/<image-pull-secret>.yaml
```

Application Deployments should reference the image-pull Secret explicitly:

```yaml
imagePullSecrets:
  - name: <image-pull-secret>
```

Do not patch the namespace default ServiceAccount by default. Use explicit
`imagePullSecrets` on each Deployment, or create a dedicated runtime
ServiceAccount only when many workloads in the namespace need the same registry
credential.

If an app in the namespace deliberately uses APIRule, label the namespace before
the app Deployment is created or roll the Deployment after labeling:

```bash
kubectl label namespace <namespace> istio-injection=enabled --overwrite
```

## Platform Step 8 - Configure Runtime Secret Backend

For SAP Credential Store with BTP Operator, create one shared or platform-owned
Credential Store instance and per-project bindings. The operator-generated
binding Secrets are Kubernetes objects; the secret values live in Credential
Store and are imported through the customer's approved process. The recommended
default is direct mTLS:

```text
ServiceBinding creates mTLS binding credentials
operator or approved secret tool uses admin binding to write values
runtime pod mounts read-only runtime binding
application helper reads required keys from Credential Store at startup
```

First verify the BTP Operator CRDs are present:

```bash
kubectl get crd serviceinstances.services.cloud.sap.com
kubectl get crd servicebindings.services.cloud.sap.com
```

If these CRDs are missing, install or enable BTP Operator through the regional
platform process before applying the objects below.

```yaml
apiVersion: services.cloud.sap.com/v1
kind: ServiceInstance
metadata:
  name: <credstore-instance>
  namespace: <platform-namespace>
spec:
  serviceOfferingName: credstore
  servicePlanName: standard
  parameters:
    authentication:
      type: mtls
---
apiVersion: services.cloud.sap.com/v1
kind: ServiceBinding
metadata:
  name: <project>-<mode>-credstore-admin
  namespace: <platform-namespace>
spec:
  serviceInstanceName: <credstore-instance>
  secretName: <project>-<mode>-credstore-admin
  secretRootKey: credentials
  credentialsRotationPolicy:
    enabled: true
    rotationFrequency: 600h
    rotatedBindingTTL: 48h
  parameters:
    authorization:
      namespace_permissions:
        <project>-<mode>:
          - create
          - read
          - update
          - delete
          - list
---
apiVersion: services.cloud.sap.com/v1
kind: ServiceBinding
metadata:
  name: <project>-credstore-runtime
  namespace: <namespace>
spec:
  serviceInstanceName: <credstore-instance>
  serviceInstanceNamespace: <platform-namespace>
  secretName: <project>-credstore-runtime
  secretRootKey: credentials
  credentialsRotationPolicy:
    enabled: true
    rotationFrequency: 600h
    rotatedBindingTTL: 48h
  parameters:
    authorization:
      namespace_permissions:
        <project>-<mode>:
          - read
          - list
```

Keep a non-secret project catalog in the platform repo so operators and tools do
not have to infer names from manifests. This is a config file consumed by the
team's scripts or secret-management tooling; it is not a Kubernetes object unless
the team deliberately builds a controller for it.

```yaml
defaults:
  serviceInstance:
    namespace: <platform-namespace>
    name: <credstore-instance>
  authMode: mtls
projects:
  - name: <project>
    owner: <owning-team>
    modes:
      - name: <mode>
        kubernetesNamespace: <namespace>
        credentialStoreNamespace: <project>-<mode>
        adminBinding:
          namespace: <platform-namespace>
          name: <project>-<mode>-credstore-admin
          secretName: <project>-<mode>-credstore-admin
        runtimeBinding:
          namespace: <namespace>
          name: <project>-credstore-runtime
          secretName: <project>-credstore-runtime
```

Human or automation access to manage secret values should be gated by Kubernetes
RBAC on the admin binding Secret. Validate that boundary before importing
values:

```bash
kubectl auth can-i get secret <project>-<mode>-credstore-admin \
  -n <platform-namespace>
```

The approved secret-management tool should use the catalog and the admin binding
Secret to perform these operations without printing secret values:

```text
list project/mode entries the current user can administer
import selected keys from an env file into <project>-<mode>
put one key from stdin, with explicit replace semantics
list key names in a Credential Store namespace without values
delete one key after confirmation
```

Application secret rotation is a backend update plus an app rollout if the app
loads values only at startup:

```bash
# Update the value through the approved Credential Store tool or API.
kubectl rollout restart deployment/<agent-name> -n <namespace>
```

If the app expects simple environment variables instead of calling Credential
Store directly, have the platform backend produce a Kubernetes Secret such as
`<agent-name>-llm` with the model gateway keys used below.

## Platform Step 9 - Validate The Platform

Validate the platform before onboarding app teams:

```bash
helm list -A | grep -E 'argocd|sealed-secrets|arc|<runner-label>'
kubectl get deploy sealed-secrets-controller -n kube-system
kubectl get autoscalingrunnersets,ephemeralrunnersets,ephemeralrunners -n arc-runners
kubectl get deploy,svc -n argocd
kubectl get appprojects,applicationsets,applications -n argocd
kubectl get ns <namespace>
kubectl get sealedsecret,secret -n <namespace>
```

Run a tiny workflow in an app repo with `runs-on: <runner-label>` and confirm an
ephemeral runner appears. Then deploy one starter app end to end before adding
customer workloads.

Starter validation should prove the platform path separately from application
logic:

```text
GitHub Actions run starts on an ARC ephemeral runner
runner can build and run containers
runner can log in to the registry and push an image
Git image tag update lands on the deployment branch
Argo root app syncs ApplicationSet changes
ApplicationSet creates the app Application
Argo can read the app repo
Argo syncs the watched path
namespace and image-pull Secret exist
Deployment rolls out
Service exists
internal Service check succeeds
no APIRule exists unless explicitly requested
```

## App Step 1 - Add deployment templates

Pick one deployment format.

Helm:

```bash
cd <agent-repo>
mkdir -p deploy
cp -R <cookbook-root>/references/kyma-deployment deploy/helm
```

Kustomize:

```bash
cd <agent-repo>
mkdir -p deploy/k8s
cp -R <cookbook-root>/references/kustomize-deployment/base deploy/k8s/base
cp -R <cookbook-root>/references/kustomize-deployment/overlays deploy/k8s/overlays
```

Replace all placeholders before committing:

```text
<cookbook-root>
<agent-repo>
<agent-name>
<namespace>
<registry>
<image-pull-secret>
<kyma-cluster-domain>
<model-gateway>
<model-name>
```

### A2A Agent Toolkit starter notes

If the agent repository starts from the A2A Agent Toolkit Python scaffold, verify
these points before enabling CI/CD:

1. Add a Dockerfile if the scaffold produced source files, `manifest.yml`, and a
   `Procfile` but no container image definition:

   ```Dockerfile
   FROM python:3.12-slim

   WORKDIR /app

   COPY requirements.txt .
   RUN python -m pip install --no-cache-dir --upgrade pip \
       && python -m pip install --no-cache-dir -r requirements.txt

   COPY app ./app

   ENV HOST=0.0.0.0 \
       PORT=8080

   CMD ["python", "-m", "app"]
   ```

2. Run the generated app with the A2A SDK version line it declares. If
   `a2a-sdk>=0.2.7` resolves to a 1.x package and the app fails on older imports
   such as `TextPart`, pin the generated app to a compatible pre-1.0 line, for
   example:

   ```text
   a2a-sdk>=0.3,<1.0
   ```

3. Build and run the container with placeholder runtime variables. Do not bake
   real API keys into the image:

   ```bash
   docker build -t <agent-name>:local .
   docker run --rm -p 8080:8080 \
     -e LLM_PROVIDER=openai-compatible \
     -e OPENAI_BASE_URL=http://127.0.0.1:9999/v1 \
     -e OPENAI_API_KEY=ci-placeholder \
     -e MODEL_GATEWAY_URL=http://127.0.0.1:9999/v1 \
     -e MODEL_GATEWAY_API_KEY=ci-placeholder \
     -e MODEL_NAME=ci-placeholder \
     -e LLM_MOCK=true \
     <agent-name>:local
   ```

4. Confirm the Agent Card route and use that same route everywhere: workflow
   `AGENT_CARD_PATH`, Helm `a2a.agentCardPath`, and readiness/liveness probe
   paths. A2A v1-style apps often use `/.well-known/agent-card.json`; tested
   Python scaffold output using `a2a-sdk 0.3.x` exposed `/agent-card`.

## App Step 2 - Add CI/CD workflows

Copy the workflow templates into the agent repository:

```bash
cd <agent-repo>
mkdir -p .github/workflows .github/scripts
cp <cookbook-root>/references/gitops-workflows/ci.yml .github/workflows/ci.yml
cp <cookbook-root>/references/gitops-workflows/deploy.yml .github/workflows/deploy.yml
cp <cookbook-root>/references/gitops-workflows/scripts/smoke-a2a.py .github/scripts/smoke-a2a.py
```

Edit the placeholders in both workflow files:

```text
<runner-label>
<registry-namespace>
<agent-image-name>
python:3.12-slim    # replace with a customer-approved mirror if required
```

Set `AGENT_CARD_PATH` in both workflow files to the verified Agent Card route for
the app image.

Set repository or organization secrets:

```text
REGISTRY_SERVER
REGISTRY_USERNAME
REGISTRY_PASSWORD
```

If the regional environment uses another registry authentication mechanism,
replace the login step but keep the rest of the flow: build, smoke, push,
update deployment state in Git.

## App Step 3 - Configure runtime secrets

Use the same split as the platform bootstrap above:

```text
platform repo or platform automation:
  owns the secret backend, service instance, bindings, RBAC, and namespace

agent repo:
  documents the required keys
  references the runtime Secret or binding name
  never commits secret values
```

For a simple OpenAI-compatible model gateway, the running pod needs these keys:

```text
LLM_PROVIDER=openai-compatible
OPENAI_BASE_URL=https://<model-gateway>/v1
OPENAI_API_KEY=<secret>
MODEL_GATEWAY_URL=https://<model-gateway>/v1
MODEL_GATEWAY_API_KEY=<secret>
MODEL_NAME=<model-name>
```

Use the key names the application code actually reads. Keeping both `OPENAI_*`
and `MODEL_GATEWAY_*` during initial smoke testing lets cookbook-style agents and
A2A Agent Toolkit generated agents start from the same Secret; remove unused keys
once the app contract is finalized.

Production path:

1. The platform team creates or selects the secret backend for the namespace.
2. The platform team provisions a runtime binding or produced Kubernetes Secret,
   such as `<agent-name>-llm`, in the application namespace.
3. The agent Deployment references that Secret by name through
   `envFromSecrets` in Helm or `envFrom.secretRef` in Kustomize.
4. Secret values are loaded into the backend out of band, through the customer's
   approved process.

For SAP Credential Store with the BTP Operator, the platform-owned shape is:

```text
shared or platform-owned ServiceInstance
admin ServiceBinding for operators in a platform namespace
runtime ServiceBinding in the app namespace with read/list permission
runtime binding Secret mounted or referenced by the app Deployment
```

If the app reads Credential Store directly, mount the runtime binding and set the
helper contract explicitly. The helper must load required values before settings
objects or model clients are initialized:

```yaml
spec:
  template:
    spec:
      containers:
        - name: agent
          env:
            - name: CREDSTORE_ENABLED
              value: "true"
            - name: CREDSTORE_REQUIRED
              value: "true"
            - name: CREDSTORE_BINDING_FILE
              value: "/etc/secrets/credential-store/credentials"
            - name: CREDSTORE_NAMESPACE
              value: "<project>-<mode>"
            - name: CREDSTORE_KEYS
              value: "OPENAI_BASE_URL,OPENAI_API_KEY,MODEL_GATEWAY_URL,MODEL_GATEWAY_API_KEY,MODEL_NAME"
          volumeMounts:
            - name: credential-store-binding
              mountPath: /etc/secrets/credential-store
              readOnly: true
      volumes:
        - name: credential-store-binding
          secret:
            secretName: <project>-credstore-runtime
```

For AI Core-backed regions, replace `CREDSTORE_KEYS` with the AI Core key names
the app actually needs, such as `AICORE_AUTH_URL`, `AICORE_BASE_URL`,
`AICORE_CLIENT_ID`, `AICORE_CLIENT_SECRET`, and `AICORE_RESOURCE_GROUP`.

If the app reads model credentials directly from environment variables, have the
platform produce a Kubernetes Secret with the four keys above and reference it:

```yaml
# Helm values
envFromSecrets:
  - <agent-name>-llm
```

```yaml
# Kustomize Deployment patch
envFrom:
  - secretRef:
      name: <agent-name>-llm
```

For a quick non-production smoke in a controlled namespace, you can create that
Secret directly. Do not use this as the production secret path:

```bash
kubectl create secret generic <agent-name>-llm \
  --namespace <namespace> \
  --from-literal=LLM_PROVIDER=openai-compatible \
  --from-literal=OPENAI_BASE_URL=https://<model-gateway>/v1 \
  --from-literal=OPENAI_API_KEY=<secret> \
  --from-literal=MODEL_GATEWAY_URL=https://<model-gateway>/v1 \
  --from-literal=MODEL_GATEWAY_API_KEY=<secret> \
  --from-literal=MODEL_NAME=<model-name>
```

For KSA regulated, where AI Core may be available, the same pattern applies:
bind the relevant credentials through the platform secret backend and make the
app select `LLM_PROVIDER=aicore`. Do not hardcode AI Core as the only path in a
recipe that also targets China Landing, NS2, or KSA non-regulated.

## App Step 4 - Configure Argo CD

Create an Argo CD Application or add an ApplicationSet entry that watches the
deployment path in the application repository.

Helm source path:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: <agent-name>-dev
  namespace: argocd
spec:
  project: <argo-project>
  source:
    repoURL: <agent-repo-url>
    targetRevision: main
    path: deploy/helm
  destination:
    server: https://kubernetes.default.svc
    namespace: <namespace>
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=false
      - PruneLast=true
```

Kustomize source path:

```yaml
source:
  repoURL: <agent-repo-url>
  targetRevision: main
  path: deploy/k8s/overlays/dev
```

The app should not create its own namespace unless the platform has explicitly
delegated namespace ownership to the app team.

## App Step 5 - Run the flow

Expected flow:

```text
1. Developer opens pull request.
2. CI runs tests and starts the container in mock/safe mode.
3. Reviewer merges to main.
4. CD repeats checks, builds the image, and smokes it before push.
5. CD pushes the immutable image tag to the registry.
6. CD updates the watched deployment state in Git.
7. Argo CD reconciles the new Git state into Kyma.
```

Do not use `latest` for GitOps-managed workloads. The image tag in Git is the
deployment intent Argo CD reconciles.

## Single-service pattern

Use one Deployment and one Service when the repository owns one agent process.
The Helm or Kustomize template can be used without structural changes.

Validation checklist:

```text
[ ] PR CI passed
[ ] main CD passed
[ ] image exists in registry with immutable tag
[ ] deployment values or kustomization references the new tag
[ ] Argo CD Application is Synced and Healthy
[ ] Deployment is Available
[ ] Agent Card endpoint responds
[ ] optional JSON-RPC smoke passes
```

## Multi-service same-repo pattern

Use this when services share source, change together, and can release under one
Argo CD Application boundary.

Add a second service by giving it distinct resources:

```text
Dockerfile                      # primary service
Dockerfile.secondary            # secondary service
deploy/k8s/base/deployment.yaml
deploy/k8s/base/service.yaml
deploy/k8s/base/secondary-deployment.yaml
deploy/k8s/base/secondary-service.yaml
deploy/k8s/overlays/dev/
  deployment-patch.yaml
  secondary-deployment-patch.yaml
  kustomization.yaml                        # two image entries
```

The platform repo usually does not change when adding the second service:

```text
same namespace
same image-pull Secret
same runtime binding if the services share a trust boundary
same Argo ApplicationSet entry
same Argo Application and watched deploy path
```

Only create a separate runtime binding, Credential Store namespace, Kubernetes
namespace, or Argo Application when the secondary service has a different trust
boundary, release cadence, owner, or review gate.

Base resources for the secondary service should use distinct names, labels,
container names, and ports:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: <project>-secondary
spec:
  selector:
    matchLabels:
      app.kubernetes.io/name: <project>-secondary
  template:
    metadata:
      labels:
        app.kubernetes.io/name: <project>-secondary
    spec:
      imagePullSecrets:
        - name: <image-pull-secret>
      containers:
        - name: secondary
          image: <project>-secondary
          ports:
            - name: http
              containerPort: 8001
---
apiVersion: v1
kind: Service
metadata:
  name: <project>-secondary
spec:
  selector:
    app.kubernetes.io/name: <project>-secondary
  ports:
    - name: http
      port: 8001
      targetPort: http
```

Add both secondary files to `deploy/k8s/base/kustomization.yaml` and add a
secondary patch plus a second image entry in the overlay:

```yaml
patches:
  - path: deployment-patch.yaml
  - path: secondary-deployment-patch.yaml

images:
  - name: <project>-primary
    newName: <registry>/<project>-primary
    newTag: <initial-tag>
  - name: <project>-secondary
    newName: <registry>/<project>-secondary
    newTag: <initial-tag>
```

The CI workflow should build and smoke both containers before merge. The CD
workflow must build, push, and update both image entries by `images[].name`. Do
not replace every `newTag` line blindly, because that breaks as soon as two
images need different repositories or tags.

The first merge that introduces the secondary service may briefly point Argo at
an image tag that does not exist yet. To avoid that window, either pre-push the
secondary image under the initial tag or merge the manifest change together with
a CD run that immediately pushes both images and commits the final tag update.

For the full copy-adapt walkthrough, use
[`../../references/kustomize-deployment/multi-service-same-repo.md`](../../../references/kustomize-deployment/multi-service-same-repo.md).

Use one Argo CD Application when both services deploy together. Split into a
second repository and Application when the secondary service has a different
release cadence, owner, or review gate.

## Separate-service same-namespace pattern

Use this when services share a namespace but release independently.

Platform-owned state:

```text
namespace: <namespace>
image-pull secret: <image-pull-secret>
runtime secret backend or binding policy
Argo AppProject permissions
```

Application-owned state per service:

```text
repo: <agent-repo-url>
path: deploy/helm or deploy/k8s/overlays/dev
Argo Application: <service-name>-dev
Deployment: <service-name>
Service: <service-name>
```

The two Applications may target the same namespace, but they must not manage the
same Kubernetes object.

## Verify it works

GitHub Actions:

```bash
gh run list --repo <org>/<agent-repo> --limit 5
```

Argo CD and Kyma:

```bash
kubectl get application <agent-name>-dev -n argocd
kubectl get deploy,pod,svc -n <namespace>
kubectl logs -n <namespace> deploy/<agent-name> --tail=40
kubectl port-forward -n <namespace> svc/<agent-name> 8080:8080
curl -s http://127.0.0.1:8080/.well-known/agent-card.json | jq .name
```

Optional JSON-RPC smoke, for A2A v1.0-style servers:

```bash
BASE_URL=http://127.0.0.1:8080 \
AGENT_CARD_PATH=/.well-known/agent-card.json \
A2A_VERSION=1.0 \
A2A_METHOD=SendMessage \
A2A_PAYLOAD='<agent-specific-params-json>' \
python .github/scripts/smoke-a2a.py
```

For other A2A SDK paths, set `AGENT_CARD_PATH` to the verified route, such as
`/agent-card` for tested Python scaffold output using `a2a-sdk 0.3.x`, and use
the method shape expected by that SDK version.

If APIRule was deliberately enabled for the app, add the external check after
the internal Service check:

```bash
kubectl get apirule <agent-name> -n <namespace>
curl -s https://<agent-name>.<kyma-cluster-domain>/.well-known/agent-card.json | jq .name
```

## Troubleshooting

- **Pod stays Pending or ImagePullBackOff:** check image tag, registry hostname,
  image pull secret, and whether the registry is reachable from the Kyma cluster.
- **APIRule returns 404:** confirm the APIRule uses `gateway.kyma-project.io/v2`
  and path `/{**}` rather than old v1beta1 wildcard syntax.
- **APIRule is not Ready:** confirm the namespace has Istio injection enabled and
  roll the Deployment after labeling the namespace.
- **A2A Toolkit Python app exits during import:** check whether `a2a-sdk>=0.2.7`
  resolved to a 1.x package while the generated code still uses pre-1.0 imports.
  Pin the generated app to a compatible SDK line or update the generated code.
- **Agent Card smoke returns 404:** try the actual app routes, commonly
  `/.well-known/agent-card.json`, `/agent-card`, or `/.well-known/agent.json`,
  then set workflow `AGENT_CARD_PATH` and probe paths to the route that responds.
- **ServiceBinding never creates a Secret:** wait for condition `Succeeded`, not
  `Ready`, and verify the subaccount has the service entitlement and quota.
- **CD updates the wrong image tag:** make sure the workflow targets the image
  entry by `name`. Multi-image overlays must not use a global `sed` replacement.
- **Argo fights another controller:** ensure only one Application owns each
  Kubernetes object. Shared namespace is fine; shared object ownership is not.

## Cleanup or rollback

Rollback by reverting the Git commit that changed the image tag or Helm values:

```bash
git revert <image-tag-update-commit>
git push
```

Argo CD will reconcile back to the previous image tag.

For full cleanup in a development namespace:

```bash
kubectl delete application <agent-name>-dev -n argocd
helm uninstall <agent-name> -n <namespace>  # Helm path only
kubectl delete deploy,svc -l app.kubernetes.io/name=<agent-name> -n <namespace>
```

Delete ServiceInstances, ServiceBindings, Secrets, and namespaces only after
confirming they are not shared with other services.

## Region-specific notes

- **China Landing:** validate the exact China region and tenant entitlement
  before choosing Kyma. China Shanghai (`cn40`) and China North 3 (`cn41`) list
  Kyma in the current cookbook matrix. Use `openai-compatible` model gateway
  values because AI Core is not listed for either China target.
- **NS2:** use tenant-provided hostnames and approved registries. Do not assume
  commercial SAP domains or public model endpoints.
- **KSA regulated:** AI Core may be available if entitlement and quota exist;
  keep the model provider boundary so the same app can run through
  `openai-compatible` where AI Core is unavailable.
- **KSA non-regulated:** start with the model-gateway contract.

Run `recipes/optional/region-preflight/` before applying this recipe in any region.

## Changes under BAIP

When BAIP is available in the target region, expect the model provider and some
service-binding details to change. Keep these stable:

- A2A Agent Card and JSON-RPC surface
- app-owned Deployment and Service shape
- immutable image tag in Git
- PR CI and merge-to-main CD gates
- Argo CD Application boundary
- namespace and object ownership rules
