---
title: "Connect the production-order agent to Customer-Managed Joule"
sap-services: [Joule, Destination Service]
complexity: recipe
status: partial
---

# 03 · Customer-Managed Joule

Status: partial. This recipe supplies a single-turn bundle and locally tested A2A v0.3 compatibility.
Compiler upload, Joule action evaluation, endpoint authentication, a visible Joule answer,
and cleanup remain unproven.

The input is the public [production-order starter](../../samples/production-order-agent/)
and its selected HTTPS endpoint from [recipe 02](../02-deploy-btp/).
Use an existing Customer-Managed Joule (CMJ) tenant and synthetic mock data first.
This recipe does not provision Joule, IAS, BTP services, or a new account.
SAP-Managed Joule, plugin scaffolding, push notifications, and multi-turn paths are separate work.

DTA means design-time artifact. DA means digital assistant.
The bundle contains DTA files that a compiler prepares for deployment to a DA.
An artifact is data that an A2A task returns.

## Prerequisites

The path needs these resources:

- An owner-approved existing IAS/Joule association eligible for this CMJ path, with BYOA support and DTA schema 3.28.0 or later
- Evidence that the selected operator already has the required Manage Applications authorization
- The tenant's required deployment roles, namespace policy, and IAS App2App CLI access from its administrator
- A reachable HTTPS agent endpoint and an agreed authentication mechanism
- Node.js for legacy `@sap/joule-studio-cli@1.5.21`, which accepts Node 20.12 through 24

[Regional preflight](../optional/region-preflight/) supplies catalog context.
Make sure that the selected tenant has Joule availability and enablement separately.
AI Core and CF are not unconditional prerequisites.
Either selected deployment runtime can supply an endpoint.
Its protocol and authentication must pass tests.

## Local protocol test

Follow the [bundle README](../../samples/production-order-agent/joule-capability/) to start the existing mock MCP server.
Run the agent with `--joule-v03` and send a real HTTP v0.3 message.
The option enables the SDK adapter and legacy Agent Card.
Without the option, v1 remains the default.
The test requires a completed manufacturing-order artifact from both MCP tools.
After testing, stop both local processes.

Current CMJ [BYOA](https://help.sap.com/docs/JOULE/ba88d1ec6a1b442098863d577c19b0c0/2f9701e60fd24e948c2c74fe9e55ce23.html?version=CLOUD)
constructs A2A v0.3.0 JSON-RPC `message/send`.
It expects a synchronous response within 60 seconds.
The mock test does not prove the deployed or model deadline.

## Select the destination and bundle

The four files in [joule-capability](../../samples/production-order-agent/joule-capability/)
include a DA descriptor, capability alias map, function, and production-order intent scenario.
The alias `ProductionOrderAgent` maps to destination `COOKBOOK_PRODUCTION_ORDER_A2A`.
Review the example DA and capability names and `joule.ext` namespace for the selected tenant.
Update references consistently. The path assumes no fifth context file or toolkit-generated folder.

After separate creation approval, create one HTTP destination manually in the existing CMJ subaccount.
Point it to the chosen HTTPS agent base URL.
Match its name exactly to the alias map.
The sample and development charts provide no endpoint authentication.
Prepare an authenticated HTTPS endpoint before compiler upload.
Use `OAuth2ClientCredentials` for the destination.
The destination token grant, issuer, audience, scope, and card access path must match.
Test a rejected unauthenticated request and a successful authenticated business request.
Do not publish MCP. CLI login and Joule UI login do not prove agent endpoint authentication.

## Compiler and deployment gate

Use external legacy CLI `@sap/joule-studio-cli@1.5.21`.
Before installation, make sure that its package license and Node requirements permit your isolated tool environment.
Do not vendor the CLI.
Newer releases have a different Node and Work CLI surface.
They are not implicitly compatible with this candidate.
See [official installation](https://help.sap.com/docs/JOULE/ba88d1ec6a1b442098863d577c19b0c0/5270f042bdb2459fa2875e241ebae2e7.html?version=CLOUD)
and [authentication](https://help.sap.com/docs/JOULE/ba88d1ec6a1b442098863d577c19b0c0/5853b3509b8747a3ad832d94e55507fd.html?version=CLOUD).

Complete interactive SSO in your own terminal.
Keep secrets and authentication state outside Git and chat.
Some IAS applications require `app_tid`.
Do not copy a value from another tenant or guess it.

`joule compile` uploads the bundle and creates an authenticated remote compiler job.
It is not a local schema test.
Before running it, obtain separate authorization for the upload and selected target.
YAML parsing or the packaged DA schema can test local structure.
They cannot establish function or capability compilation.
Inspect compile output and the resulting artifact for private values.
Deployment is another live mutation and requires its own approval.

The function assumes that `agent-request` exposes the v0.3 task under `agent_result.body`.
This response wrapper contains the task. Local HTTP does not establish Joule's wrapper.
The expressions select only the completed first `production-order-summary` text artifact.
They do not guess other wrappers.
Actual Joule evaluation must establish behavior for missing values, wrong types, and empty text.
It must also establish whether actions continue after a transport error.

## Verify it works

After separate compile and deployment approvals, open the selected CMJ UI.
Ask “Why is production order 1000000 delayed?”
Require the visible expected status, operations, and potential delay for operation 0020.
Make sure that a real A2A request reached the agent.
Make sure that both private MCP tools supplied data.
Capture sanitized evidence for the action wrapper, response conditions, backend failures, and selected endpoint authentication.

A login, successful compile or deployment, capability listing, healthy app, or Agent Card alone does not complete this checkpoint.
Keep local protocol proof, compiler proof, the visible Joule answer, and cleanup proof separate.
Record each result against the selected source and environment.

## Cleanup or rollback

After cleanup approval, remove only this added local capability from the selected DA.
Use the pinned CLI's documented command:

```bash
joule remove "<DA_NAME>" --capability "<NAMESPACE>:<CAPABILITY_NAME>"
```

See [official removal](https://help.sap.com/docs/JOULE/ba88d1ec6a1b442098863d577c19b0c0/3fa5325ef29246da9b4ddc4ea54eafe0.html?version=CLOUD).
Remove or restore only the destination owned by this test.
Make sure that it no longer routes.
Make sure that pre-existing DA capabilities, users, tenant, and services remain.
Endpoint and sample teardown follow the selected deployment recipe.


## Native response-validation gap

The current `answer_text != ''` expression does not independently reject a
whitespace-only string. Actual Joule evaluation must cover space, tab/newline,
U+2003, null, list, map, Boolean and numeric text values, as well as missing
fields and transport failures. A local Python contract or YAML parse cannot
prove the selected Joule runtime's type handling, Unicode checks, response
wrapper or continuation after transport errors. Keep these cases as open
native acceptance requirements; do not assume that a trim-only change clears
them. The current bundle is an experimental proposal for native validation.
