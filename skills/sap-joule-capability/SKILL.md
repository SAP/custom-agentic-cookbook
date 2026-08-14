---
name: sap-joule-capability
description: Use this skill when authoring `.sapdas.yaml` capability bundles to register a code-based agent into Joule. Covers the four bundle files (capability, _da, scenarios, functions), the `joule.ext` namespace rules, daar packaging, and the three integration paths (direct A2A, BPA-async, multi-agent front-door).
---

# Joule Capability Bundles — wire a code agent into Joule

To make a code-based A2A agent callable from Joule, ship a `joule-capability/` directory containing four kinds of `.sapdas.yaml` files. Joule consumes them via the Joule CLI (`joule deploy`).

## Bundle layout

```
joule-capability/
├── capability.sapdas.yaml         # who is this agent, where is its Agent Card
├── _da.sapdas.yaml                # which conversational surfaces it can appear in
├── scenarios/
│   └── default.sapdas.yaml        # intents → functions
└── functions/
    └── <name>.sapdas.yaml         # each function maps to an A2A skill id
```

## `capability.sapdas.yaml`

```yaml
apiVersion: joule.ext/v1
kind: Capability
metadata:
  name: my-first-agent
spec:
  agentCardUrl: https://my-first-agent.<your-cf-domain>/.well-known/agent.json
  authMode: oauth2-client-credentials      # OR `ias` for prod
  scenarios: [default]
```

## `_da.sapdas.yaml` (Digital Assistant binding)

```yaml
apiVersion: joule.ext/v1
kind: DigitalAssistant
metadata: { name: my-first-agent-da }
spec:
  surfaces: [joule-code-editor, joule-sidebar-erp]
  capabilityRef: my-first-agent
```

## `scenarios/<name>.sapdas.yaml`

```yaml
apiVersion: joule.ext/v1
kind: Scenario
metadata: { name: default }
spec:
  intents: ["@my-first-agent *"]
  fallback: true
  functions: [echo]
```

## `functions/<name>.sapdas.yaml`

```yaml
apiVersion: joule.ext/v1
kind: Function
metadata: { name: echo }
spec:
  description: "Echo what the user said"
  examples: ["say PONG"]
  a2aSkillId: echo            # matches AgentSkill(id="echo") in agent_executor.py
```

## Deploying

```bash
joule login
joule deploy ./joule-capability
joule list capabilities | grep my-first-agent
```

## Three integration paths

| Path | When | How |
|------|------|-----|
| 1: Direct A2A | one agent, sync, < 60s | `authMode: oauth2-client-credentials`, agent on CF/Kyma — quickstart Step 06 |
| 2: BPA-async | long-running | Capability targets a BPA process; agent does work, callback to BPA |
| 3: Multi-agent front-door (proxy) | many agents, central IAS | Capability targets the proxy URL; proxy fans out — planned, no vendored template yet. Not the same as [SwissKnife](https://github.com/SAP-samples/btp-joule-a2a-pro-code-agent) (single full A2A agent, not a proxy); see [`references/btp-joule-a2a-pro-code-agent/`](../../references/btp-joule-a2a-pro-code-agent/). |

## Region availability

Joule itself is not GA in every region — run [`recipes/00-develop/00-region-preflight/`](../../recipes/00-develop/00-region-preflight/) before promising a customer.

## Pitfalls

- `agentCardUrl` blocked by auth → Joule can't discover. Always make `/.well-known/agent.json` public.
- `a2aSkillId` mismatch → Joule registers the function but invocation returns 404. Compare to your agent's `AgentSkill(id=...)`.
- Missing `scenarios` or empty intents → Joule registers the capability but won't route.

## Verify

```bash
joule list capabilities | grep -E "<name>.+ACTIVE"
joule invoke --capability <name> --text "say PONG"
# expect: response containing PONG
```

## Cross-references

- Joule capability bundles live inside the agent template. The `references/a2a-agent-cap/` slot (TODO — see [`references/README.md`](../../references/README.md)) will ship the canonical CAP bundle; until then, use the public reference at [`references/btp-joule-a2a-pro-code-agent/`](../../references/btp-joule-a2a-pro-code-agent/).
- Walkthrough: [`recipes/01-deploy/01-wire-into-joule/`](../../recipes/01-deploy/01-wire-into-joule/)
