# Recipes

Each numbered folder is one checkpoint in the guided toolkit flow.
The generated agent starts with mock data.
The toolkit example is a Sales Order Agent.
Its `--prompt` workflow tailors the generated project to your purpose.

The [connect-data](optional/connect-data/) recipe uses the checked-in Python production-order sample.
It is a standalone local path to synthetic records from the public SAP sandbox.
Generated projects need a separate backend adapter.

> ℹ **Not on Claude Code?** Read [`AGENTS.md`](../AGENTS.md), then use the locally built toolkit MCP server (Codex, Cursor, OpenCode, Gemini CLI, Cline) or the raw shell scripts. Run `./scripts/build-toolkit-mcp.sh`; the MCP package is not published. See [`docs/harnesses.md`](../docs/harnesses.md) and the vendored [`SCRIPTS.md`](../toolkits/a2a-agent-toolkit/SCRIPTS.md). Same inputs, same outputs.

## Layout

```
recipes/
  01-scaffold-agent/  checkpoint 1 — toolkit driver + scaffold (mock data) + local chat proof; no BTP
  02-deploy-btp/      checkpoint 2 — first BTP touchpoint: subaccount, logins, region, deploy CF/Kyma
  03-joule/           checkpoint 3 — wire the deployed agent into Joule (where available)
  optional/           pull in only when the situation calls for it (incl. connect-data, RAG, KG, observability)
```

## The flow

From the Cookbook root, clone the toolkit and launch Claude Code with the plugin (`git clone https://github.com/SAP-samples/joule-a2a-agent-toolkit.git toolkits/a2a-agent-toolkit && claude --plugin-dir toolkits/a2a-agent-toolkit`), then type **`/start`**. It asks three questions — what your agent should do, which LLM endpoint you have, whether you have a BTP subaccount yet — then drives the checkpoints, persisting every decision and completed step in `pilot-config.env` (gitignored) so any later session resumes where you left off.

| Checkpoint | Result you'll see | Needs |
|---|---|---|
| [**01 · Scaffold your agent**](01-scaffold-agent/) | your agent replies on localhost — mock data, tailored to your purpose | a supported coding harness + one LLM endpoint |
| [**02 · Deploy on BTP**](02-deploy-btp/) | a public agent URL (Cloud Foundry or Kyma) | a BTP subaccount with CF or Kyma — first step that needs one |
| [**03 · In Joule**](03-joule/) | the agent answering inside Joule | a Joule-enabled tenant (region-dependent) |

For a standalone sandbox example, use [`optional/connect-data`](optional/connect-data/) with the checked-in Python production-order sample.
If checkpoint 1 uses that sample, continue with the same project.
Toolkit-generated projects need a separate backend adapter and deployment path.

```mermaid
flowchart TD
    C1["01 · scaffold agent<br/>driver + scaffold (mock data) + chat proof<br/>(local only — no BTP)"] --> C2
    C2["02 · deploy on BTP<br/>subaccount + logins + region check<br/>+ deploy-agent (CF or Kyma)"] --> C3
    C3["03 · in Joule<br/>create-destination + joule deploy"]

    SAMPLE["Checked-in Python production-order sample"] --> D["optional/connect-data<br/>standalone local sandbox path"]
    C2 -. sovereign / unfamiliar region .-> P["optional/region-preflight"]
    P -. informs .-> C2
    C2 -. no AI Core in region .-> O1["optional/sovereign-model-gateway"]
    C1 -. custom model behind AI Core .-> O3["optional/bring-your-own-model"]
    O1 -. rejoins .-> C2
    O3 -. rejoins .-> C2
    C2 -. GitOps replaces manual push .-> O2["optional/gitops-cicd"]

    C1 -. generated project RAG .-> W1["optional/hana-vector-store"]
    C1 -. generated project KG .-> W2["optional/hana-kg-triple-store"]
    C2 -. observability .-> W3["optional/observe-and-eval"]
    C2 -. SAP Cloud Logging .-> W4["optional/sap-cloud-logging"]
```

Each recipe names its input, output, and guided prompt.
The checkpoint project accumulates one capability per step.
The connect-data recipe is a standalone path for the checked-in sample.

## Optional — pull in when needed

| Recipe | When | Relationship |
|---|---|---|
| [connect-data](optional/connect-data/) | Read synthetic production-order records from the public SAP sandbox. | Use the checked-in Python sample. Generated agents need a separate adapter. |
| [region-preflight](optional/region-preflight/) | the target region is sovereign, regulated, or unfamiliar | Diagnostic for checkpoint 2 — Discovery Center check + entitlement dump + LLM-path tier table. Commercial hubs can skip it. |
| [sovereign-model-gateway](optional/sovereign-model-gateway/) | AI Core is unavailable/blocked (China Landing, NS2, KSA non-regulated, or EU Access without cross-region routing) | Swaps the model provider to `--llm-provider openai-compatible` against a customer-approved gateway. Rejoins at checkpoint 2. |
| [bring-your-own-model](optional/bring-your-own-model/) | the customer hosts a custom LLM behind AI Core (e.g. Ollama serving Gemma) | Replaces the default catalog model behind `--llm-provider aicore`. Rejoins at checkpoint 2. |
| [gitops-cicd](optional/gitops-cicd/) | the team wants Argo CD reconciliation instead of a manual `cf push` / `helm upgrade` | Replaces checkpoint 2's manual push with a GitOps pipeline. |
| [hana-vector-store](optional/hana-vector-store/) | the agent needs RAG over documents | Extends a toolkit-generated project. The standalone production-order sample needs a separate integration. |
| [hana-kg-triple-store](optional/hana-kg-triple-store/) | the agent needs knowledge graph traversal | Extends a toolkit-generated project. The standalone production-order sample needs a separate integration. |
| [observe-and-eval](optional/observe-and-eval/) | the deployed agent needs observability and evaluation | Layers on checkpoint 2 — adds structured logging, OTel middleware, and an eval harness. |
| [sap-cloud-logging](optional/sap-cloud-logging/) | the Kyma-deployed agent needs SAP Cloud Logging integration | Layers on checkpoint 2 (Kyma) — wires telemetry pipelines to SAP Cloud Logging. |

## Adding a recipe

1. Mirror the frontmatter of [`02-deploy-btp/README.md`](02-deploy-btp/README.md) at the top of the new recipe's `README.md`.
2. Numbered checkpoint recipes are reserved for the linear track; new material goes to `optional/` (opt-in) with a descriptive slug.
3. Open with the `> **Guided:** / **Flow:** / **Input:** / **Output:** / **Toolkit command:**` callout — the Guided line names the checkpoint it serves plus a paste-able mid-flow prompt, and the Input must literally name the producing step's Output.
4. Include `## Verify it works` — with a chat proof (a real message and the expected reply), not just the agent-card curl, wherever the recipe produces a runnable agent.
5. PR with the CONTRIBUTING checklist.
