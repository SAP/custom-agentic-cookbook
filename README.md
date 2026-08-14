# Custom Agentic Cookbook

Customer-facing cookbook(recipes and skills) for building custom AI Agents on SAP BTP(Business Technology Platform) - across regular commercial regions, **China Landing**, **NS2 / SAP sovereign**, **KSA**, and other regulated deployments — before BAIP is generally available everywhere.

## Why this exists

Official BTP path for AI Agent extensibility is **Joule BYOA + SAP AI Core / Generative AI Hub**. That path is GA (General Availability) today in `eu10` and rolling out across the regular commercial regions. It is **not** available in China Landing, NS2, or KSA non-regulated as of the most recent 2026-07-07 regional check. BAIP (Business AI Platform) consolidates this stack going forward; GA dates per region are not firm yet.

This cookbook unblocks customer teams **right now** with whatever services the target region exposes, and keeps interfaces clean enough to port to BAIP later.

## Developer experience

The cookbook is built so you can go from an idea to a running, deployable agent by describing what you want in plain language — the coding agent does the wiring. What that gives you:

- **Prompt-driven scaffolding.** Describe your agent's purpose to a skill-aware coding agent (Claude Code, Cursor, Cline, Codex) and get a complete, runnable A2A project — system prompt, tools, and agent card tailored to that purpose. The prompt is the interface; there's no boilerplate to hand-write.
- **Runs locally on day one — no cloud account.** The scaffold ships with mock data, so your agent converses and demos end-to-end on `localhost` before you touch BTP, entitlements, or regions. You build and test the agent's behavior first, and wire in a live backend only when you're ready.
- **A guided, verifiable path.** Three checkpoints — scaffold → deploy (Cloud Foundry or Kyma) → register in Joule — each an independent milestone with a chat proof, so you always confirm the agent works before moving to the next step. Optional recipes (live data, RAG, knowledge graph, GitOps, observability) layer one capability at a time onto the same project.
- **Composable, harness-agnostic skills.** Capability modules for AI Core, HANA vector/knowledge-graph retrieval, Joule capability bundles, and Kyma work with any coding agent that supports the skill format — reuse them across projects instead of relearning each service's setup.
- **Portable by construction.** Model access sits behind a provider switch, transport uses the stable A2A protocol, and persistence swaps in-memory for HANA Cloud — so an agent built here moves to SAP's first-party platform (Joule BYOA + AI Core) later with minimal rework.
- **Region-aware for regulated deployments.** Sovereign and regulated regions are first-class: availability guardrails are documented per recipe, so you learn what's supported in your target region up front rather than discovering it at deploy time.

The net effect: less time on plumbing and platform archaeology, more time on what your agent actually does.

## Quickstart

**1. Clone the repo**

```bash
git clone https://github.com/SAP/custom-agentic-cookbook.git
cd custom-agentic-cookbook
```

**2. Pick a recipe and follow it in order**

| Checkpoint | What you get | What you need |
|---|---|---|
| [01 · Scaffold your agent](recipes/01-scaffold-agent/) | Your agent running on localhost with mock data | A coding agent (Claude Code, Cursor, Codex, etc.) + one LLM endpoint |
| [02 · Deploy on BTP](recipes/02-deploy-btp/) | A public agent URL on Cloud Foundry or Kyma | A BTP subaccount with CF or Kyma |
| [03 · In Joule](recipes/03-joule/) | Your agent answering inside Joule | A Joule-enabled tenant (region-dependent) |

Start at checkpoint 01 — no BTP account needed until checkpoint 02. The scaffold uses mock data so you can build and test locally first.

**Pre-requisites:**

- A coding agent that supports skills (Claude Code, Cursor, Cline, Codex CLI, or any MCP-compatible harness)
- An LLM endpoint — SAP AI Core if you have one, or any OpenAI-compatible endpoint
- A BTP subaccount with Cloud Foundry or Kyma (checkpoint 02 onwards only)

**Optional extras** — pull in when your situation calls for it:

| Recipe | When to use |
|---|---|
| [connect-data](recipes/optional/connect-data/) | Add live S/4HANA, SuccessFactors, or any HTTP API data (free api.sap.com sandbox included) |
| [region-preflight](recipes/optional/region-preflight/) | Sovereign, regulated, or unfamiliar region — run a Discovery Center check first |
| [sovereign-model-gateway](recipes/optional/sovereign-model-gateway/) | AI Core unavailable in your region — swap to an OpenAI-compatible model gateway |
| [bring-your-own-model](recipes/optional/bring-your-own-model/) | Customer hosts a custom LLM behind AI Core |
| [gitops-cicd](recipes/optional/gitops-cicd/) | Replace manual `cf push` / `helm upgrade` with an Argo CD GitOps pipeline |
| [hana-vector-store](recipes/optional/hana-vector-store/) | Add RAG over documents using HANA Cloud vector retrieval |
| [hana-kg-triple-store](recipes/optional/hana-kg-triple-store/) | Add knowledge graph traversal using HANA Cloud triple store |
| [observe-and-eval](recipes/optional/observe-and-eval/) | Add structured logging, OTel middleware, and an eval harness |
| [sap-cloud-logging](recipes/optional/sap-cloud-logging/) | Wire telemetry pipelines to SAP Cloud Logging (Kyma) |

## Repository map

```
recipes/
  01-scaffold-agent/        Checkpoint 1 — scaffold and run locally (mock data, no BTP)
  02-deploy-btp/            Checkpoint 2 — deploy to Cloud Foundry or Kyma
  03-joule/                 Checkpoint 3 — register agent inside Joule
  optional/                 Opt-in extras: live data, sovereign gateway, GitOps, BYO model, RAG, KG, observability, SAP Cloud Logging

skills/
  sap-ai-core/              Bootstrap AI Core, resource groups, deployments, OAuth2
  sap-hana-vector/          HANA Cloud vector retrieval (RAG)
  sap-hana-triple/          HANA Cloud knowledge graph / triple store
  sap-hana-data-prep/       Prepare documents and data for HANA vector/KG ingestion
  sap-joule-capability/     Author .sapdas.yaml Joule capability bundles
  sap-repair-joule-access/  Diagnose Joule CLI login and capability-deployment failures
  sap-sovereign-regions/    Regional availability guardrails for sovereign and regulated regions
  sap-kyma-cli/             Kyma deployment patterns
```

Skills work with any coding agent that supports the skill format (Claude Code, Cursor, Cline, Codex CLI). For the broader SAP-authored skill catalog (BTP CLI, CF CLI, Joule CLI, UI5, Fiori Guidelines, and more), install directly from [skills.cloud.sap](https://skills.cloud.sap/).

## Positioning

This cookbook is an **interim solution for teams building on BTP today**, particularly in regions where SAP's first-party agent platform (BAIP / Joule BYOA + AI Core) is not yet generally available.

The official long-term path is Joule BYOA + SAP AI Core / Generative AI Hub. This cookbook is designed with a clean layered architecture so agents built here can be ported to that platform later with minimal rework:

- **Model access** is isolated behind `LLM_PROVIDER` (`aicore` | `openai-compatible`) — swap the provider without touching agent logic
- **Agent transport** uses A2A v0.3.0 — protocol-stable
- **Persistence** is in-memory by default; HANA Cloud is the drop-in durable task store
- **Regional assumptions** are documented per recipe, not scattered through code

When BAIP becomes available in your region, replace the model provider and keep everything else.

## Feedback

Use GitHub Issues to report problems:

- **[Cookbook gap](https://github.com/SAP/custom-agentic-cookbook/issues/new?template=cookbook-gap.yml)** — a recipe step is missing, broken, or unclear

## Contributing, security, license

- [CONTRIBUTING.md](CONTRIBUTING.md) — how to add a recipe, region, or skill
- [SECURITY.md](SECURITY.md) — how to report a vulnerability
- [LICENSE](LICENSE) — repository license
