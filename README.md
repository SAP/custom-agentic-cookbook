[![REUSE status](https://api.reuse.software/badge/github.com/SAP/custom-agentic-cookbook)](https://api.reuse.software/info/github.com/SAP/custom-agentic-cookbook)


# Custom Agentic Cookbook

Recipes and skills for building AI Agents on SAP Business AI Platform(BAIP) — in every region you operate, including sovereign and regulated deployments.

## Why this exists

SAP BTP is available in **China Landing**, **NS2 / SAP sovereign**, **KSA**, and every regulated region you operate in. Building AI Agents on it — while SAP's Business AI Platform(BAIP) continues its global rollout — takes knowing exactly which services your region exposes and how to wire them together correctly.

This cookbook solves that precisely. Every recipe is built and tested against specific regional service availability. You get a working agent on the first try, in your region, without discovering gaps in production.

When you're ready to move to SAP's full BAIP, the migration is an architectural upgrade: swap the model provider, keep everything else. The agent you build here is the same agent — running on the full stack.

This cookbook unblocks customer teams **right now** with whatever services the target region exposes, and keeps interfaces clean enough to port to BAIP later.

## Developer experience

Your developers shouldn't need to be BTP platform experts to build AI Agents that work. Describe what the agent should do — a skill-aware coding agent handles the rest. What your organisation gets:

- **First working demo in hours, not weeks**. AI Agents run on localhost with mock data from day one — no BTP account, no entitlements, no infrastructure to provision before the idea can be tested.
- **A delivery path with no hidden cliffs.** Three checkpoints — scaffold → deploy → register in Joule — each independently verified before the next begins. Teams always know where they stand.
- **No expertise tax, harness-agnostic skills.** Skills encapsulate AI Core, HANA vector and knowledge-graph retrieval, Joule capability bundles, and Kyma. Teams that have never touched these services use them correctly from the start — and reuse the same skills across projects with any coding agent.
- **Zero lock-in**. Model access, transport, and persistence are each independently swappable. Moving to SAP's first-party platform is a configuration change, not a project.
- **Region-safe by design**. Sovereign and regulated region guardrails are baked into every recipe — no surprises at deploy time.

Teams ship working AI Agents in days. That time goes back into what the AI Agent actually does.

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

The official long-term path is **Joule BYOA + SAP AI Core / Generative AI Hub**. This cookbook is not a workaround — it is a deliberate bridge, built to serve teams today and designed to migrate cleanly to that platform as it arrives.

Every architectural decision protects that promise:

- **Model access** is isolated behind `LLM_PROVIDER` (`aicore` | `openai-compatible`) — swap the provider without touching agent logic
- **Agent transport** uses A2A v0.3.0 — protocol-stable
- **Persistence** is in-memory by default; HANA Cloud is the drop-in durable task store
- **Regional assumptions** are documented per recipe, not scattered through code

When BAIP becomes available in your region, replace the model provider and keep everything else.

## Support, Feedback, Contributing

This project is open to feature requests/suggestions, bug reports etc. via [GitHub issues](https://github.com/SAP/custom-agentic-cookbook/issues). Contribution and feedback are encouraged and always welcome. For more information about how to contribute, the project structure, as well as additional contribution information, see our [Contribution Guidelines](CONTRIBUTING.md).

## Security / Disclosure
If you find any bug that may be a security problem, please follow our instructions at [in our security policy](https://github.com/SAP/custom-agentic-cookbook/security/policy) on how to report it. Please do not create GitHub issues for security-related doubts or problems.

## Code of Conduct

We as members, contributors, and leaders pledge to make participation in our community a harassment-free experience for everyone. By participating in this project, you agree to abide by its [Code of Conduct](https://github.com/SAP/.github/blob/main/CODE_OF_CONDUCT.md) at all times.

## Licensing

Copyright 2026 SAP SE or an SAP affiliate company and custom-agentic-cookbook contributors. Please see our [LICENSE](LICENSE) for copyright and license information. Detailed information including third-party components and their licensing/copyright information is available [via the REUSE tool](https://api.reuse.software/info/github.com/SAP/custom-agentic-cookbook).

## Contest

![Developer Advocate](images/devadv-small.png)

SUBSTRING(lastName FROM 9 FOR 1)       

For more information: https://url.sap/7afji2
