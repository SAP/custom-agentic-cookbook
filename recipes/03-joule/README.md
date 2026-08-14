---
title: "Wire an A2A agent into Joule"
sap-services: [Joule, Destination Service, XSUAA, Joule Studio CLI]
region-availability:
  - region: commercial
    works: yes
    note: "GA in eu10; rolling out elsewhere. Verify DTA schema 3.28.0+"
  - region: china
    works: no
    note: "Joule control plane not in cn40 as of 2026-06-29. Use UI5 chat shell + Build Work Zone tile fallback."
  - region: ns2
    works: no
    note: "Joule not GA in NS2 boundary. Ship a custom UI shell."
  - region: ksa
    works: limited
    note: "Joule rollout trails CF runtime GA. Verify per tenant."
complexity: recipe
last-validated: 2026-06-29
changes-under-baip: "Joule capability YAML schema may evolve; DTA → BAIP capability model. The `agent-request` action stays."
---

# 03 · Wire into Joule

> **Guided:** checkpoint 3 — the last step, only where Joule is available in the region. Mid-flow prompt: *"Wire my deployed agent into Joule."*
> **Flow:** terminal step of the happy path — consumes the deployed URL from **[02-deploy-btp](../02-deploy-btp/)**.
> **Input:** the deployed `<agent>` URL and Agent Card from **02-deploy-btp** (its Output), plus BTP roles `extensibility_developer` + `capabilityadmin` and a working `joule-studio-cli`.
> **Output:** a Terraform-managed BTP HTTP destination named `<ALIAS_NAME>` pointing at the deployed URL **plus** a deployed Joule capability bundle (`joule-capability/da.sapdas.yaml`) that surfaces the agent inside Joule.
> **Automation:** `infra/btp/scripts/joule-destination.sh` creates the native destination; `joule deploy --compile` publishes the capability bundle. The toolkit command remains an alternative for subaccounts not managed by Terraform.

> ⚠ Region: Joule BYOA + A2A v0.3.0 + DTA schema 3.28.0+ is GA in eu10; rolling out elsewhere; NOT GA in cn40 / NS2 / ksa-non-regulated. For sovereign regions, use the UI5 chat shell fallback (recipe TODO).
> Plugin profile: `genai-hub`
> LLM provider: `aicore`
> Persistence: any

## When to use it

The customer's region has Joule with DTA schema 3.28.0+ AND the customer wants their agent surfaced inside the Joule consumer experience.

## Prerequisites

- Agent already deployed ([01-scaffold-agent](../01-scaffold-agent/) — optionally [optional/connect-data](../optional/connect-data/) — then [02-deploy-btp](../02-deploy-btp/))
- BTP roles: `extensibility_developer` + `capabilityadmin`
- Joule Studio CLI: `npm install -g @sap/joule-studio-cli` (note: `@sap/joule-cli` 404s; use `@sap/joule-studio-cli`)
- `joule login` succeeded (the App2App IAS flow must be configured — see [Troubleshooting](#troubleshooting))
- BTP Destination service available in the region

## Scaffold

The plugin generates the `joule-capability/` folder when you scaffold with the default `genai-hub` profile.

## Configure

### Log in to the Joule tenant

For a new account, bootstrap Cloud Identity Services, trust, and Joule from the
Terraform directory first:

```bash
cd infra/btp
./scripts/joule-bootstrap.sh --apply \
  --var-file=terraform.tfvars \
  --var-file=profiles/joule-studio.tfvars.example
```

If SAP creates a new identity tenant, activate its initial administrator from
SAP's email and run the identical command again. The helper discovers the IAS
hostname and resumes with trust and Joule provisioning; no hostname needs to be
copied into a variable file.

For shared or production operation, use the separately locked foundation,
identity, and Joule roots in [`infra/btp/stacks`](../../infra/btp/stacks/README.md)
instead of extending the legacy single state. After each stage, run
`infra/btp/scripts/status.sh` for the consolidated readiness report.

When the tenant was provisioned with `infra/btp`, run the repository helper:

```bash
cd infra/btp
./scripts/joule-login.sh
```

If the `joule-cli` service binding has not been created yet, make that mutation
explicit on the first run:

```bash
./scripts/joule-login.sh --create-binding
```

The script derives the Joule API URL from Terraform, reads the binding secret
directly from BTP into memory, and invokes `joule login --sso-passcode`. It does
not print or persist the binding credentials. The temporary authentication code
is entered through the prompt opened by the CLI.

The destination ALIAS must match `system_aliases.<AliasName>.destination` in
`joule-capability/capability.sapdas.yaml`.

> ℹ Two YAMLs, two jobs: `capability.sapdas.yaml` holds the capability metadata and system aliases; `da.sapdas.yaml` is the top-level deployment descriptor you pass to `joule deploy` in the Deploy step below. Both are generated into `joule-capability/` by the scaffold.

#### Terraform (default for Terraform-managed subaccounts)

From `infra/btp`, resolve the deployed CF app route and create the native BTP
destination:

```bash
./scripts/joule-destination.sh \
  --agent-name <agent-name> \
  --destination-name <ALIAS_NAME> \
  --var-file=terraform.tfvars \
  --var-file=profiles/agent.tfvars.example \
  --var-file=profiles/joule-studio.tfvars.example \
  --apply
```

For Kyma or an explicitly selected route, replace `--agent-name` with
`--agent-url=https://<PUBLIC_AGENT_HOST>`. Terraform owns subsequent updates and
deletion. Authentication is fixed to `NoAuthentication`; the wrapper never
creates a Destination service key or stores credentials.

#### Toolkit alternatives for non-Terraform subaccounts

The older plugin, MCP, and shell drivers remain available when Terraform does
not own the subaccount destination. Do not mix them with the Terraform resource
for the same destination name.

##### Claude Code plugin

```bash
/sap-a2a-agent-toolkit:create-destination <agent-name> <ALIAS_NAME> <landscape>
```

##### MCP server

Ask the assistant something like:

> Use the sap-a2a-toolkit MCP to create a BTP destination named `<ALIAS_NAME>` pointing at the deployed CF app `<agent-name>` in landscape `<landscape>`.

Build with `./scripts/build-toolkit-mcp.sh`, then configure the harness to spawn
the absolute `scripts/start-toolkit-mcp.sh` path. Setup:
[`docs/harnesses.md`](../../docs/harnesses.md).

##### Standalone shell script

```bash
bash toolkits/a2a-agent-toolkit/skills/joule-a2a-agent/scripts/create-destination.sh \
  --agent-name <agent-name> \
  --destination-name <ALIAS_NAME> \
  --landscape <landscape>
```

Reference: [`SCRIPTS.md` §6](https://github.tools.sap/agent-assisted-coding/A2A-Agent-Toolkit-Plugin/blob/main/SCRIPTS.md#6-reference-create-destinationsh).

> ℹ `joule deploy` is **not** wrapped by any driver. Run it directly against `joule-capability/` — see the Deploy step below.

## Deploy

```bash
cd <agent-name>/joule-capability
joule deploy ./da.sapdas.yaml --compile -n "<assistant_name>"
```

## Verify it works

```bash
curl -s https://<agent-route>/.well-known/agent.json | jq .name
# expect: agent card

# Then in the Joule UI, send a prompt that matches the capability scenario description.
# Inspect cf logs to confirm the A2A task arrived.
cf logs <agent-name> --recent | grep "task received"
```

## Troubleshooting

- `Schema version defined in config file is greater than the current schema version of Joule` → tenant DTA schema is too old. Request a Joule service update.
- `namespace validation error` → `metadata.namespace` must be `joule.ext`.
- 401 from Joule → re-run `joule login`; verify `extensibility_developer` + `capabilityadmin` roles.
- `joule login` fails → the App2App IAS flow isn't configured for Joule Studio CLI on the subaccount. Follow the [role-assignment guide](https://help.sap.com/docs/joule/integrating-joule-with-sap/assign-roles) — a one-time IAS admin action, not something the toolkit can auto-provision.
- `joule list`, `compile`, or `deploy` returns HTTP 401/403 → use the [`sap-repair-joule-access`](../../skills/sap-repair-joule-access/SKILL.md) diagnostic skill. It distinguishes a stale token from a missing Terraform assignment without driving the interactive passcode prompt.

## Cleanup or rollback

```bash
joule undeploy <capability-id>
```

## Region-specific notes

- **eu10:** happy path, GA.
- **eu11 / us10 / us20 / us21 / jp10 / ap10 / ap11:** rolling out; verify per tenant.
- **China (cn40):** NO. Use UI5 chat shell + Build Work Zone tile instead.
- **NS2:** NO. Ship a custom UI shell.
- **KSA non-regulated:** NO. Use UI5 chat shell.
- **KSA regulated:** verify per tenant; AI Core is available so the prerequisites can be met.

## Related skills

For UI work alongside this recipe, install these skills from <https://skills.cloud.sap/>:

- `sap-fiori-guidelines` — Fiori design system + AI/Joule UI patterns
- `ui5-best-practices-integration-cards` — Joule cards rendered from agent output
- `accessibility` — UI5 a11y APIs
- `styling` — UI5 Web Components theming

## Source

- Discovery Center (Joule listing per region) — confirm with the [region preflight](../optional/region-preflight/).
- [`skills/joule-a2a-agent/references/joule-capability.md`](https://github.tools.sap/agent-assisted-coding/A2A-Agent-Toolkit-Plugin/blob/main/skills/joule-a2a-agent/references/joule-capability.md) (in the A2A Agent Toolkit plugin)

### Further reading

- Felix Bartler (SAP), [**Joule A2A: Connect Code Based Agents into Joule**](https://community.sap.com/t5/technology-blog-posts-by-sap/joule-a2a-connect-code-based-agents-into-joule/ba-p/14329279) — SAP community blog (2026-02-16). Canonical SAP-authored walkthrough that this recipe operationalizes: LangGraph ReAct agent on CF, A2A protocol, `capability.sapdas.yaml` + `joule.ext` namespace, `agent-request` action, destination wiring, `joule deploy -c -n "<bot_name>"`. Example repo: [`fyx99/joule-pro-code-a2a`](https://github.com/fyx99/joule-pro-code-a2a).
