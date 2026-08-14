---
title: "Deploy on BTP — Cloud Foundry or Kyma"
sap-services: [BTP Cloud Foundry runtime, BTP Kyma runtime, HANA Cloud, Destination Service, XSUAA]
region-availability:
  - region: commercial
    cf: yes
    kyma: yes
  - region: china-cf
    cf: yes
    kyma: yes
    notes: "cn40 Shanghai — both CF and Kyma listed in Discovery Center"
  - region: china-kyma
    cf: yes
    kyma: yes
    notes: "China Shanghai and China North 3 list Kyma; verify tenant entitlement"
  - region: ns2
    cf: yes
    kyma: yes
    notes: "Sterling + Colorado"
  - region: ksa
    cf: yes
    kyma: yes
    notes: "regulated + non-regulated"
complexity: recipe
last-validated: 2026-07-07
changes-under-baip: "Service-binding shape may change to BAIP-native bindings; CF manifest and Kyma Helm chart + APIRule survive unchanged."
---

# 02 · Deploy on BTP — Cloud Foundry or Kyma

> **Guided:** checkpoint 2 — the **first step that needs a BTP account**. `/start` runs the subaccount checks here, derives the landscape from your subaccount, and routes sovereign regions through the model gateway automatically. Mid-flow prompt: *"Deploy my agent to BTP."*
> **Flow:** happy-path convergence point — accepts the output of **[01-scaffold-agent](../01-scaffold-agent/)** (default, mock data), **[optional/connect-data](../optional/connect-data/)**, **[optional/sovereign-model-gateway](../optional/sovereign-model-gateway/)**, **[optional/bring-your-own-model](../optional/bring-your-own-model/)**, or the **optional/** RAG / KG variants. Hands off to **[03-joule](../03-joule/)** and **[optional/observe-and-eval](../optional/observe-and-eval/)**.
> **Input:** the agent project from **01-scaffold-agent** (its Output) — any toolkit-scaffolded shape, task store chosen, `--llm-provider` set. Mock data deploys fine; live data via optional/connect-data can come before or after.
> **Output:** a deployed A2A agent URL — `<agent>.cfapps.<landscape>.hana.ondemand.com` (CF) or `<agent>.<cluster-domain>` (Kyma) — with the Agent Card reachable, consumed by **03-joule** (Joule wiring) and **optional/observe-and-eval** (observability).
> **Toolkit command:** `/sap-a2a-agent-toolkit:deploy-agent` (drives `cf push` + MTA on CF, or Helm + APIRule v2 on Kyma).

Deploy the agent project from checkpoint 1 — TypeScript Express (`manifest.yml`), TypeScript CAP (`mta.yaml`), or the Python four-file shape (`agent.py`, `agent_executor.py`, `app.py`, `__main__.py`) — to either BTP Cloud Foundry **or** BTP Kyma. `deploy-agent` auto-detects which shape it's looking at. The two routes are presented side-by-side so you can pick the one your subaccount entitles you to — and switch later without rewriting the agent.

## Step 0 — First BTP touchpoint: region, subaccount, logins

Everything before this checkpoint ran on your laptop. Now the target subaccount matters.

### 0.1 Pick the LLM path for the region

The landscape is **derived from the subaccount**, not asked: `btp --format json get accounts/subaccount <SUBACCOUNT_ID> | jq .region`.

| Region | Default LLM path |
|--------|------------------|
| Commercial hubs (`eu10`, `eu11`, `us10`, `us20`, `us21`, `ap10`, `ap11`, `jp10`, …) | `--llm-provider aicore` |
| EU Access (`eu10`/`eu11` operational-restriction tier) | `aicore` — cross-region model routing needs customer approval; fallback `openai-compatible`. |
| China Landing (`cn40`, `cn41`) · NS2 · KSA non-regulated (`sa31`) | `openai-compatible` — AI Core not in region → [`../optional/sovereign-model-gateway/`](../optional/sovereign-model-gateway/). |
| KSA regulated (`sa30`) | `aicore` with `openai-compatible` fallback (entitlement-gated per tenant). |

Sovereign, regulated, or unfamiliar region — or the table above doesn't settle it? Run the full [**region preflight**](../optional/region-preflight/) (Discovery Center check + entitlement dump + tier rules) before continuing. If the provider changes here (e.g. the scaffold used `aicore` but the region has none), re-scaffold with the right `--llm-provider` or follow the sovereign gateway recipe — the tool code and Agent Card carry over unchanged.

### 0.2 What the subaccount must have

**The minimum to build and host an agent on BTP is a subaccount with Cloud Foundry or Kyma — nothing else.** Everything below the first row is conditional on what your agent actually uses:

No subaccount yet? The reusable [`infra/btp/`](../../infra/btp/) Terraform account factory creates the subaccount, runtime, entitlements, roles, and CF spaces without storing credentials in the repository. Run the region preflight before enabling paid or region-specific profiles.

| Prereq | Needed when | Verify |
|---|---|---|
| **CF environment** enabled + one org/space (or **Kyma runtime**) | **always — the only hard requirement** | `btp list accounts/environment-instance --subaccount <SUB_ID>` |
| **AI Core** entitlement + instance + a deployed foundation model | only on `--llm-provider aicore` — use it if you have it. No AI Core? Any OpenAI-compatible endpoint works instead (`openai-compatible`); the model can be hosted anywhere, no BTP service needed for it. | `cf marketplace -e aicore` |
| **HANA Cloud** (`hana / hdi-shared`) | only for the durable HANA task store — the in-memory store is fine for MVPs | `btp --format json list accounts/entitlement --subaccount <SUB_ID> \| jq '.quotas[] \| select(.service=="hana" or .service=="hana-cloud")'` |
| **Destination** + **XSUAA** entitlements + instances | only when wiring the agent into Joule ([03-joule](../03-joule/)); Destination is also the production-grade way to reach backends (see [optional/connect-data](../optional/connect-data/)) | `cf marketplace -e destination` · `cf marketplace -e xsuaa` |

Missing a conditional entitlement? BTP Cockpit → *Entitlements* → *Configure Entitlements*. For AI Core, the entitlement alone is not enough — create the instance **and** deploy at least one foundation model, or the agent has no callable model.

### 0.3 Log in

```bash
# BTP CLI
btp login --url https://cli.btp.cloud.sap            # sovereign landscapes may use a different API URL — check the subaccount overview
btp target --subaccount <SUBACCOUNT_ID>

# Cloud Foundry — one endpoint per landscape (do NOT reuse an eu10 login for cn40)
cf login -a https://api.cf.<landscape>.hana.ondemand.com
cf target -o <ORG> -s <SPACE>
```

| Landscape | CF endpoint |
|---|---|
| `eu10` / `eu11` / `us10` / `ap10` | `https://api.cf.<landscape>.hana.ondemand.com` |
| `cn40` (China Landing) | `https://api.cf.cn40.platform.sapcloud.cn` |
| `sa30` / `sa31` (KSA) | `https://api.cf.sa3x.hana.ondemand.com` |
| NS2 | per-tenant endpoint — take the literal hostname from the subaccount overview; do not hardcode |

Local CLI additions for this checkpoint: `cf` CLI **v8+**, `btp` CLI. CAP/MTA agents also need `mbt` (`npm i -g mbt`) and the MultiApps plugin (`cf install-plugin multiapps`). Kyma route: see prerequisites below.

## Prerequisites

Cloud Foundry route:
- `cf` CLI logged into the target landscape (step 0.3)
- CF org + space targeted
- Only the conditional entitlements your variant needs (step 0.2) — a mock-data, in-memory, `openai-compatible` agent needs none

Kyma route:
- Kyma runtime enabled on the subaccount
- `kubectl` configured against the Kyma kubeconfig
- BTP Operator installed (`kubectl get crd | grep btpoperator`)
- API Gateway module ≥ 3.4 (APIRule `v2`; `v1beta1` is removed)
- Namespace has Istio sidecar injection enabled (`kubectl label ns <ns> istio-injection=enabled`)
- A container registry reachable from the cluster
- `helm` ≥ 3.12
- Only the conditional entitlements your variant needs (step 0.2)

Both routes:
- The agent project from checkpoint 1, serving a valid Agent Card locally. Any toolkit-scaffolded shape works — TS Express, TS CAP, or the Python four-file shape.
- **Canonical entrypoints** (already encoded in the scaffold's manifest/chart — don't hand-edit): Python: `uvicorn app:app --host 0.0.0.0 --port ${PORT:-8080}`; TS Express: `npm start` honouring `$PORT`; CAP: the MTA module's start command.
- Sovereign LLM contract values ready: `MODEL_GATEWAY_URL`, `MODEL_GATEWAY_API_KEY`, plus the model-name var from the scaffold's `.env.example` (see [`../optional/sovereign-model-gateway/`](../optional/sovereign-model-gateway/)).
- **Agent Card path (a2a-sdk version-dependent):** SDK pinned to spec ≤ v0.2.6 serves `/.well-known/agent.json`; spec ≥ v0.3.0 serves `/.well-known/agent-card.json`. Check the scaffolded code and use the matching path in the verify commands below.

## Step 1 — Deploy with the toolkit

You already built the agent in checkpoint 1 (plus optional/connect-data if you took it) — you do **not** re-scaffold here. The toolkit's `deploy-agent` command takes the existing project directory and drives the whole deployment: build the manifest / Helm chart, create the service bindings (HANA / Destination / XSUAA where used), push the app to the runtime, and (where Joule is available) register the capability. It auto-detects the project type from the files in the directory. You don't hand-write a `manifest.yml`, `xs-security.json`, an APIRule, or a `cf push` — the toolkit generates and runs them.

```bash
# Cloud Foundry (default target)
/sap-a2a-agent-toolkit:deploy-agent ./<agent-name> --target cf
```

```bash
# Kyma
/sap-a2a-agent-toolkit:deploy-agent ./<agent-name> \
  --target kyma \
  --overlay dev \
  --cluster-domain <cluster-domain>
```

> ℹ `deploy-agent` goes end-to-end through Joule when the tenant supports it (DTA schema 3.28.0+). If you only want the runtime deploy and will wire Joule separately, that's fine — [`03-joule`](../03-joule/) covers the destination + capability bundle in detail, and `deploy-agent` is idempotent so you can re-run it after.

**Same task, other drivers** (no Claude plugin):

#### MCP server

> Use the sap-a2a-toolkit MCP to deploy the A2A agent in `./<agent-name>` to `<cf|kyma>` in landscape `<landscape>`.

Build with `./scripts/build-toolkit-mcp.sh`, then configure the harness to spawn
the absolute `scripts/start-toolkit-mcp.sh` path. Setup:
[`docs/harnesses.md`](../../docs/harnesses.md).

#### Standalone shell scripts

The Python/MCP drivers don't wrap the full deploy as one command — run the underlying sequence (`cf push` / `helm install` → `create-destination.sh` → `joule deploy`). The script matrix and the manifest/APIRule templates the scripts emit are documented in `SCRIPTS.md` §3 (in the A2A Agent Toolkit plugin); for Kyma, use the reusable Helm chart in [`references/kyma-deployment/`](../../references/kyma-deployment/) as the deployment wrapper.

## Verify it works

```bash
# Cloud Foundry
cf apps
cf logs <agent-name> --recent | tail -40
# Commercial / NS2 / KSA:
curl -s https://<agent-name>.cfapps.<landscape>.hana.ondemand.com/.well-known/agent.json | jq .name
# China Shanghai (cn40):
curl -s https://<agent-name>.cfapps.cn40.platform.sapcloud.cn/.well-known/agent.json | jq .name
# expect: "<agent-name>"
# If SDK ≥ v0.3.0: swap /.well-known/agent.json → /.well-known/agent-card.json
```

```bash
# Kyma
kubectl get pods -l app=<agent-name>
kubectl logs deploy/<agent-name> --tail=40
kubectl get apirules -A | grep <agent-name>
curl -s https://<agent-name>.<cluster-domain>/.well-known/agent-card.json | jq .name
# expect: "<agent-name>"
# If SDK ≤ v0.2.6: swap /.well-known/agent-card.json → /.well-known/agent.json
```

Then the chat proof against the **deployed** URL, using the helper from [`references/gitops-workflows/scripts/smoke-a2a.py`](../../references/gitops-workflows/scripts/smoke-a2a.py):

```bash
BASE_URL=https://<agent-url> \
AGENT_CARD_PATH=</.well-known/agent.json or agent-card.json> \
  python3 references/gitops-workflows/scripts/smoke-a2a.py
```

…or ask the coding harness: *"Send the deployed agent a test message and show
me the reply."*

## Step 2 — Cleanup

```bash
# Cloud Foundry
cf delete <agent-name> -f -r
cf delete-service <agent-name>-destination -f
cf delete-service <agent-name>-xsuaa       -f
cf delete-service <agent-name>-hana        -f
# cf delete-service aicore -f   # KSA regulated only
```

```bash
# Kyma
helm uninstall <agent-name>
kubectl delete apirule <agent-name>
kubectl delete servicebinding  <agent-name>-destination-binding
kubectl delete serviceinstance <agent-name>-destination
# Repeat delete for xsuaa / hana bindings + instances you created.
```

## Region-specific notes

- **Commercial (eu10/us10/us20/eu20/ap10):** both runtimes available. CF route `<app>.cfapps.<landscape>.hana.ondemand.com`. AI Core not entitled by default in every commercial subaccount — confirm in step 0.2 before passing `--llm-provider aicore`.
- **China Shanghai (cn40):** CF yes, Kyma yes in the 2026-07-07 Discovery Center check. Deploy CF using the `.sapcloud.cn` route (`<app>.cfapps.cn40.platform.sapcloud.cn`) or deploy through Kyma after tenant entitlement is confirmed. No AI Core / GenAI Hub in cn40 (confirm with the [region preflight](../optional/region-preflight/)) — `--llm-provider openai-compatible` is mandatory, pointed at a BYO-LLM endpoint (Alibaba DashScope / Qwen, or PAI-EAS DeepSeek). Anthropic / OpenAI / Gemini routes are blocked at the network boundary.
- **NS2 (Sterling + Colorado):** both runtimes available. CF API endpoints are issued per-tenant under the NS2 boundary — pull the literal hostname from the subaccount overview; do not hardcode. AI Core is not listed for NS2 (confirm with the [region preflight](../optional/region-preflight/)), so `--llm-provider openai-compatible` against the sovereign model gateway is the only supported route here; there is no AI Core fallback to bolt on.
- **KSA regulated (Dammam):** CF yes, Kyma yes. **Only** sovereign region where AI Core is listed (`standard` / `extended`); `--llm-provider aicore` is viable if the subaccount has the entitlement and quota.
- **KSA non-regulated (Dammam):** CF yes, Kyma yes. No AI Core listed — start with `--llm-provider openai-compatible`.

## Troubleshooting

### Cloud Foundry

- `cf push` fails with `No buildpack matched`: ensure `requirements.txt` (Python) or `package.json` (TS) exists at the project root — the buildpack auto-detects on it.
- App crashes immediately on start: check `cf logs <agent-name> --recent`. Most common cause is the start command not honouring `$PORT` — Python must be `uvicorn app:app --host 0.0.0.0 --port ${PORT:-8080}`; TS scaffolds read `process.env.PORT`.
- 503 on the Agent Card endpoint: `cf restage <agent-name>` after any `cf set-env` or `cf bind-service` change.
- `generative-ai-hub-sdk` dependency conflict: it pins `pydantic==2.10.6` which conflicts with `a2a-sdk` (needs `>=2.11.3`). Use `langchain-openai` with direct AI Core credential extraction instead.
- `No service instance found for 'aicore'`: the entitlement exists but no instance was created in the target space — `cf create-service aicore <plan> aicore-<agent-name>` then re-push. If the marketplace doesn't list `aicore`, the service is not GA in this landscape — switch to `--llm-provider openai-compatible` (step 0.1).
- `cf login` returns 401 in cn40 / sa3x / NS2: sovereign landscapes use different auth endpoints and sometimes a different `btp` API URL. Confirm the CF endpoint from step 0.3 matches the subaccount's BTP Cockpit overview.

### Kyma

- Pod stuck `CrashLoopBackOff` with no logs: the namespace likely lacks Istio sidecar injection. APIRule v2 requires it — `kubectl label ns <ns> istio-injection=enabled` and roll the deployment.
- 404 from the gateway: APIRule v2 does not support regex paths — use `{*}` (one segment) or `{**}` (zero-or-more, must be last). `path: /*` is v1beta1 syntax.
- 403 / preflight failures from a browser client: APIRule v2 has **no default CORS policy**. Declare `corsPolicy` explicitly and add `OPTIONS` to `rules.methods`.
- APIRule shows `v1beta1` warnings: that version is removed in API Gateway module 3.4 and reconciliation stops at 3.9. Migrate to `gateway.kyma-project.io/v2`.
- `ServiceBinding` stays `Pending`: confirm BTP Operator is installed (`kubectl get crd serviceinstances.services.cloud.sap.com`) and that the subaccount is entitled to the offering/plan you referenced.
- `helm install` fails with `Chart.yaml file is missing`: copy `references/kyma-deployment/` into the agent repository as `deploy/helm/`, then retry the install.

## Source

- Region availability check: [`../optional/region-preflight/`](../optional/region-preflight/) + Discovery Center.
- Sovereign LLM setup: [`../optional/sovereign-model-gateway/`](../optional/sovereign-model-gateway/).
- Reusable Kyma chart: [`references/kyma-deployment/`](../../references/kyma-deployment/).
- Reproducible GitOps path: [`../optional/gitops-cicd/`](../optional/gitops-cicd/).
