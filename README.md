# Custom Agentic Cookbook

[![REUSE status](https://api.reuse.software/badge/github.com/SAP/custom-agentic-cookbook)](https://api.reuse.software/info/github.com/SAP/custom-agentic-cookbook)

Recipes, runnable samples, and agent skills for building custom AI agents on
SAP Business Technology Platform (SAP BTP), including sovereign and regulated
deployments.

> [!NOTE]
> This repository is under active development. Check the requirements and
> validation status in each recipe before using it in a production landscape.

## Why this Cookbook

SAP BTP services and model availability vary by region, particularly in
sovereign and regulated environments. This Cookbook provides a practical path
from a local prototype to deployment on Cloud Foundry or Kyma and, where
available, integration with Joule.

Each recipe identifies its prerequisites, regional considerations, validation
steps, and optional alternatives so teams can choose only the capabilities
their environment supports.

## Get started

Clone the Cookbook and begin with the first recipe:

```bash
git clone https://github.com/SAP/custom-agentic-cookbook.git
cd custom-agentic-cookbook
```

Follow the core path in order:

| Checkpoint | Guide | Requirement |
| --- | --- | --- |
| 1 | [Scaffold and run an agent locally](recipes/01-scaffold-agent/) | A supported coding agent and an LLM endpoint |
| 2 | [Deploy the agent on SAP BTP](recipes/02-deploy-btp/) | A subaccount with Cloud Foundry or Kyma |
| 3 | [Connect the agent to Joule](recipes/03-joule/) | A Joule-enabled tenant in a supported region |

Checkpoint 1 uses mock data and does not require an SAP BTP account. For the
complete flow and its dependencies, see the [recipe guide](recipes/README.md).

### Install the agent skills

The skills follow the [Agent Skills](https://agentskills.io/) format. Install
the repository and select the skills you need:

```bash
npx skills add SAP/custom-agentic-cookbook
```

List the available skills without installing them:

```bash
npx skills add SAP/custom-agentic-cookbook --list
```

## Available recipes

Use these optional recipes when the core path needs another capability:

| Recipe | Use it to |
| --- | --- |
| [Connect business data](recipes/optional/connect-data/) | Add S/4HANA, SuccessFactors, or another HTTP API |
| [Check regional availability](recipes/optional/region-preflight/) | Validate services in sovereign, regulated, or unfamiliar regions |
| [Use a sovereign model gateway](recipes/optional/sovereign-model-gateway/) | Use an approved OpenAI-compatible endpoint where SAP AI Core is unavailable |
| [Bring your own model](recipes/optional/bring-your-own-model/) | Serve a custom model through SAP AI Core |
| [Add GitOps delivery](recipes/optional/gitops-cicd/) | Deploy to Kyma with Argo CD |
| [Add HANA vector search](recipes/optional/hana-vector-store/) | Build retrieval-augmented generation over documents |
| [Add a HANA knowledge graph](recipes/optional/hana-kg-triple-store/) | Query connected business data with SPARQL |
| [Observe and evaluate an agent](recipes/optional/observe-and-eval/) | Add structured telemetry and evaluation guidance |
| [Use SAP Cloud Logging](recipes/optional/sap-cloud-logging/) | Send Kyma agent telemetry to SAP Cloud Logging |

## Available skills

| Skill | Helps with |
| --- | --- |
| [`sap-ai-core`](skills/sap-ai-core/) | SAP AI Core setup, deployments, and authentication |
| [`sap-hana-data-prep`](skills/sap-hana-data-prep/) | Preparing business data for vector or knowledge-graph ingestion |
| [`sap-hana-triple`](skills/sap-hana-triple/) | Knowledge graphs and SPARQL on SAP HANA Cloud |
| [`sap-hana-vector`](skills/sap-hana-vector/) | Vector search and retrieval-augmented generation on SAP HANA Cloud |
| [`sap-joule-capability`](skills/sap-joule-capability/) | Joule capability bundles for code-based agents |
| [`sap-kyma-cli`](skills/sap-kyma-cli/) | Kyma deployment patterns used by the Cookbook |
| [`sap-repair-joule-access`](skills/sap-repair-joule-access/) | Joule CLI authentication and authorization troubleshooting |
| [`sap-sovereign-regions`](skills/sap-sovereign-regions/) | Region-specific model and service guardrails |

For detailed selection guidance, see the [skills catalog](skills/README.md).
Complementary SAP-authored skills for BTP, Cloud Foundry, Joule, UI5, and
Fiori are available from [skills.cloud.sap](https://skills.cloud.sap/).

## Experimental samples

- [`samples/fde-a2a-minimal`](samples/fde-a2a-minimal/) is a credential-free
  Python A2A v1.0 sample with local, container, and Kyma deployment paths. It
  uses an in-memory task store and is limited to one replica. External `noAuth`
  exposure is intended only for development and smoke testing.
- [`samples/production-order-agent`](samples/production-order-agent/) is a
  mock-safe A2A v1.0 business example with two MCP tools for production-order
  status and operations, an opt-in public SAP S/4HANA sandbox connection, and
  optional SAP AI Core synthesis. Local and container paths are included; BTP
  deployment is intentionally deferred.

## Support

Search the [GitHub issue tracker](https://github.com/SAP/custom-agentic-cookbook/issues)
before opening a bug report or feature request. Report suspected security
issues privately through the repository's
[security policy](https://github.com/SAP/custom-agentic-cookbook/security/policy).

## Contributing

Contributions are welcome. Read the [contribution guidelines](CONTRIBUTING.md)
before opening an issue or pull request. All participants must follow the
[SAP Open Source Code of Conduct](https://github.com/SAP/.github/blob/main/CODE_OF_CONDUCT.md).

## License

Copyright 2026 SAP SE or an SAP affiliate company and Custom Agentic Cookbook
contributors. This project is licensed under the [Apache License 2.0](LICENSE).
Third-party licensing and copyright information is available through
[REUSE](https://api.reuse.software/info/github.com/SAP/custom-agentic-cookbook).

## Contest

![Developer Advocate](images/devadv-small.png)

SUBSTRING(lastName FROM 9 FOR 1)

For more information: <https://url.sap/7afji2>
