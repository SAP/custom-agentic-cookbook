---
name: sap-joule-capability
description: Prepare the experimental single-turn production-order DTA bundle for Customer-Managed Joule, with explicit A2A v0.3 compatibility and separate compiler, auth, runtime and cleanup gates.
---

# Customer-Managed Joule capability bundle

Use the [single-turn bundle](../../samples/production-order-agent/joule-capability/) and
[recipe 03](../../recipes/03-joule/). The full checkpoint remains partial.
CMJ means Customer-Managed Joule. DTA means design-time artifact.
DA means digital assistant. The bundle contains DTA files for a DA.

Do not assume a toolkit-generated bundle or provision a tenant.
Do not substitute SAP-Managed Joule or Work CLI behavior for this CMJ DTA path.
The selected tenant and tools must support this specific path.

## Public starter contract

Run the production-order sample with `--joule-v03` to enable the SDK's v0.3 adapter and legacy card.
Without it, the v1-only default remains.
Both versions share the existing business and MCP implementation and in-memory task store.
The change adds no inbound authentication, streaming, push, or multi-turn capability.
The legacy card advertises v0.3. The current v1 card and `SendMessage` remain available.

## Four files and resolution

The bundle contains these files:

- `da.sapdas.yaml`: One local capability folder with DA schema 1.4.0
- `capability.sapdas.yaml`: DTA 3.28.0, namespace and name, and alias map for the destination
- `functions/call_agent.yaml`: Remote `agent-request`, current utterance, and safe reply
- `scenarios/invoke_agent.yaml`: Production-order intent that selects `call_agent`

The function name selects its filename.
The system alias selects the exact destination name.
The Agent Card skill ID is metadata, not a function endpoint.
This single-turn path requires no context or task file.
Before use, make sure that the namespace, names, descriptor, and schemas pass the selected tenant and tool policy.

The bundle adapts structure from the Apache-2.0 public
[toolkit reference at 7d284bd6](https://github.com/SAP-samples/joule-a2a-agent-toolkit/blob/7d284bd6d6e83f2ce9e3bf164689adc9db9ad4f1/skills/joule-a2a-agent/references/joule-capability.md).
It does not port the toolkit.
It does not claim toolkit scaffold or runtime parity.

## Response boundary

An artifact is data that a task returns.
Local v0.3 HTTP returns task state `completed`, a first `production-order-summary`
artifact, and a first `kind: text` part.
The answer is in artifact text. `status.message` is absent.
The function assumes that Joule places this task in `agent_result.body`.
That response wrapper remains unproven in Joule.

Use official [getSafe/orElse](https://help.sap.com/docs/JOULE/ba88d1ec6a1b442098863d577c19b0c0/a96708519552494cbaef4ab81bf94a21.html?version=CLOUD)
for missing keys and indexes.
Accept only the selected completed state, artifact name, text kind, and nonempty text.
Do not guess wrappers or use collection expressions without test evidence.
Actual Joule evaluation must test wrong types, empty or whitespace text, failed tasks,
protocol errors, and transport timeout behavior.
Keep raw responses, credentials, task IDs, and backend errors out of text for the user.
Static parsing does not prove expression behavior.

## Platform and release gates

The path requires these gates:

- An existing CMJ tenant with selected namespace, roles, IAS access, and HTTPS endpoint
- An authenticated HTTPS endpoint and an OAuth2 client-credentials destination before compiler upload, with MCP kept private
- External legacy `@sap/joule-studio-cli@1.5.21` with compatible Node and package license
- Separate approval before `joule compile`, which uploads files and creates an authenticated remote job
- Separate deployment approval, actual CMJ action evaluation, and a visible answer from the tools within 60 seconds
- Exact capability and destination ownership with separate cleanup approval

Do not vendor the CLI or install or update it globally as part of this skill.
Use [BYOA](https://help.sap.com/docs/JOULE/ba88d1ec6a1b442098863d577c19b0c0/2f9701e60fd24e948c2c74fe9e55ce23.html?version=CLOUD)
as the protocol source.
CLI and UI authentication do not prove authentication for requests from Joule to the agent.
Record compiler, runtime, and cleanup proof separately before marking the checkpoint complete.
