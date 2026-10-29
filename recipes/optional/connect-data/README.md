# Optional · Connect data — swap mock tools for a live backend

> **Guided:** optional step — `/start` offers it after checkpoint 1 (and it works just as well after deploying). Mid-flow prompt: *"Connect my agent to real data: …"*
> **Flow:** optional **branch** off **[01-scaffold-agent](../../01-scaffold-agent/)** — replaces the scaffold's mock tool data with a live backend. Rejoins the happy path at **[02-deploy-btp](../../02-deploy-btp/)** (`deploy-agent` is idempotent, so re-deploying an already-deployed agent after connecting data works too).
> **Input:** the agent project from **01-scaffold-agent** (its Output) — talking, with mock data in its tools.
> **Output:** the same project answering from a live backend (worked example: the S/4HANA `A_SalesOrder` OData service) — real answers to questions like "which sales orders are open for sold-to party X?".
> **Toolkit command:** none — this step edits the `tools/` directory of the project `create-agent` produced.

Take this when the pilot needs live business data—the S/4HANA sales-order tool
below is the worked example; the same pattern (prompt the coding agent, keep
credentials behind the tool boundary, verify with a message that must call the
tool) applies to SuccessFactors, Ariba, or any HTTP API your agent's purpose
needs. Skip it entirely if mock data is enough for the demo or the deployment
milestone comes first.

You do **not** hand-write the tool. Continue the same coding-agent session and
give it a follow-up prompt. The harness rewrites the mock tool bodies against
the real backend while keeping the tool interfaces, system prompt, and
Agent Card unchanged.

## Prerequisites

- The agent project from [`01-scaffold-agent`](../../01-scaffold-agent/) that
  already serves a valid Agent Card, open in your selected coding harness.
- A reachable backend. For the worked example: an S/4HANA system exposing the standard **`API_SALES_ORDER_SRV`** OData service (entity set `A_SalesOrder`).
- Backend credentials available to the agent at runtime — for the worked example: `S4_BASE_URL`, `S4_USERNAME`, `S4_PASSWORD` (basic auth for the demo; use a BTP Destination + principal propagation in production — see [`03-joule`](../../03-joule/)).
- **No S/4 tenant? Use the free sandbox.** Register at [api.sap.com](https://api.sap.com), then use `S4_BASE_URL=https://sandbox.api.sap.com/s4hanacloud` with the key sent as an `APIKey` header (`S4_APIKEY`) instead of basic auth — mention that in the step-1 prompt and Claude Code wires it. Mock data on SAP's side, but the real OData shape, so the tool ports to a customer tenant unchanged. Note: the sandbox is on the public internet and not reachable from air-gapped sovereign environments (see [`references/PREREQUISITES.md`](../../../references/PREREQUISITES.md)).

## Step 1 — Prompt the coding agent to connect the tool

In the session that has the project open, describe what you want the agent to be
able to do. Let the coding harness inspect the project and propose the file
layout, function signatures, and API mechanics. The worked example:

> Replace the mock data in the sales-order-agent with live S/4HANA data — it should answer things like "which orders are open for this customer?" and "what's on order 12345?" from the real system. Our S/4 connection details are in the environment.

That's enough. The coding agent should find the right S/4HANA OData service
(`API_SALES_ORDER_SRV` / `A_SalesOrder`), pattern-match the existing S/4 tool at
[`references/supply-chain-risk-agent/tools/s4_purchase_orders.py`](../../../references/supply-chain-risk-agent/tools/s4_purchase_orders.py),
rewrite the tool bodies, and keep credentials and endpoint URLs behind the tool
boundary so the model never sees them.

For a different backend, swap the description: *"…answer questions about leave balances from SuccessFactors…"*, *"…check open POs in Ariba…"* — same flow, same boundary rules. If you want to steer it, add specifics ("filter by sold-to party", "include line items", "use a BTP Destination instead of basic auth"). Review the generated files before running.

## Step 2 — Provide backend credentials

Locally (worked example):

```bash
export S4_BASE_URL=https://<s4-host>          # or https://sandbox.api.sap.com/s4hanacloud
export S4_USERNAME=<user>                      # tenant only
export S4_PASSWORD=<secret>                    # never commit; use a secret store in deployment
# sandbox instead: export S4_APIKEY=<key-from-api.sap.com>
npm start                                      # or the scaffold's run command
```

## Verify it works

```bash
# The Agent Card still resolves (tool wiring didn't break the app):
curl -s http://localhost:8080/.well-known/agent.json | jq .name
```

Then send the agent a message that **must call the tool**. In the coding-agent
session, ask: *"Send the running agent this message and show me the reply:
'List the open sales orders for sold-to party 0000100000.'"* The harness derives
the JSON-RPC envelope from the scaffolded code and shows the reply.

Expected: the agent answers with real `A_SalesOrder` rows, and the tool invocation appears in the app logs. If the reply still reads like the scaffold's mock data, the rewrite didn't land — re-check the step-1 wiring.

## Sovereign note

The backend read path is region-agnostic — it is a plain HTTP/OData call to the customer's own system. Only the **model** provider changes per region: this step works identically whether the agent runs on `--llm-provider aicore` or the `openai-compatible` sovereign gateway ([`../sovereign-model-gateway/`](../sovereign-model-gateway/)).

## Next

Deploy (or re-deploy) in [02-deploy-btp](../../02-deploy-btp/).

> If you didn't pick the durable HANA task store at scaffold time and now want it (state surviving restarts / scale-out), re-run the 01-scaffold-agent prompt with the "durable HANA task store" line — everything here still applies.
