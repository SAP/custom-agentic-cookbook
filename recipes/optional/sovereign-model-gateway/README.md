# Optional: Sovereign Model Gateway

> **Flow:** sovereign-region **branch** — replaces the `aicore` assumption in the checkpoint recipes. Rejoins the happy path at **[02-deploy-btp](../../02-deploy-btp/)**.
> **Input:** the toolkit driver from **[01-scaffold-agent](../../01-scaffold-agent/)** (its Output) plus a customer-approved OpenAI-compatible gateway URL + API key + model name.
> **Output:** a `sales-order-agent` CAP + HANA task-store scaffold emitted with `--llm-provider openai-compatible` (no AI Core binding; `langchain-openai` `ChatOpenAI` wired to `MODEL_GATEWAY_URL` with a bearer token) — consumed by **02-deploy-btp** for deploy.
> **Toolkit command:** `/sap-a2a-agent-toolkit:create-agent sales-order-agent --framework cap --taskstore hana --llm-provider openai-compatible`.

> **Guided:** `/start` routes here automatically at **checkpoint 2** when the preflight shows no AI Core in the target region. Mid-flow prompt: *"Switch my agent to a sovereign model gateway."*

Use this when SAP AI Core / GenAI Hub is unavailable or not approved in the target region.

## Region Profiles

Default to this recipe for:

- China Landing
- NS2 / SAP sovereign
- KSA non-regulated

Use it as fallback anywhere AI Core entitlement or quota is blocked.

## Scaffold

Three interchangeable drivers. All three now accept the sovereign LLM provider natively — the emitted project drops the AI Core service binding, swaps in `@langchain/openai` (TypeScript) / `langchain-openai` (Python), and expects `MODEL_GATEWAY_URL` + `MODEL_GATEWAY_API_KEY` at runtime.

#### Claude Code plugin (default)

```bash
/sap-a2a-agent-toolkit:create-agent sales-order-agent \
  --framework cap \
  --taskstore hana \
  --llm-provider openai-compatible \
  --landscape <landscape>
```

#### MCP server (Codex, Cursor, OpenCode, Gemini CLI, Cline)

Ask the assistant something like:

> Use the sap-a2a-toolkit MCP to scaffold a sovereign TypeScript CAP A2A agent named `sales-order-agent` in landscape `<landscape>`, with the HANA task store and LLM provider `openai-compatible` (this region has no AI Core). Purpose: `<short purpose>`.

Build with `./scripts/build-toolkit-mcp.sh`, then configure the harness to spawn
the absolute `scripts/start-toolkit-mcp.sh` path. Setup:
[`docs/harnesses.md`](../../../docs/harnesses.md).

#### Standalone shell script

```bash
bash toolkits/a2a-agent-toolkit/skills/joule-a2a-agent/scripts/scaffold-ts.sh \
  --name sales-order-agent \
  --framework cap \
  --taskstore hana \
  --landscape <landscape> \
  --llm-provider openai-compatible
```

Reference: `SCRIPTS.md` (in the A2A Agent Toolkit plugin).

The gateway must satisfy the contract in the [Contract](#contract) section below regardless of which driver you use.

## Configure

```bash
export LLM_PROVIDER=openai-compatible
export MODEL_GATEWAY_URL=https://model-gateway.example.com/v1
export MODEL_GATEWAY_API_KEY=<secret>
export MODEL_NAME=<model-name>
```

> ℹ Toolkit ≥ v0.6.0 scaffolds read `MODEL_GATEWAY_URL` / `MODEL_GATEWAY_API_KEY`. Older scaffolds used `OPENAI_BASE_URL` / `OPENAI_API_KEY` — always match the generated `.env.example`.

For deployment, set secrets through the customer's approved deployment mechanism, not in Git.

## Validate

- `curl <MODEL_GATEWAY_URL>/models` if the gateway supports it
- app start logs show no missing AI Core binding error
- agent card is reachable
- simple Joule prompt reaches the agent

## Contract

The scaffolded agent expects an **OpenAI-compatible** HTTP surface on the customer-approved gateway:

| Env var | Required | Meaning |
|---|---|---|
| `LLM_PROVIDER` | yes | Literal `openai-compatible`. The toolkit branches on this. |
| `MODEL_GATEWAY_URL` | yes | Base URL of the gateway. Must end in `/v1` for compatibility with `@langchain/openai` / `langchain-openai` defaults. (Pre-v0.6.0 scaffolds: `OPENAI_BASE_URL`.) |
| `MODEL_GATEWAY_API_KEY` | yes | Bearer token accepted by the gateway. (Pre-v0.6.0 scaffolds: `OPENAI_API_KEY`.) |
| `MODEL_NAME` | yes | The gateway's deployment/model identifier (not necessarily an upstream OpenAI model name). |

Minimum HTTP surface the gateway must implement (subset of the OpenAI REST spec):

- `POST /v1/chat/completions` with the standard `messages`, `model`, `temperature`, `stream` fields.
- Streaming via SSE (`stream: true`) is recommended but not required.
- `POST /v1/embeddings` only if the recipe uses `sap-hana-vector` — see optional/hana-vector-store.

The agent framework never talks to AI Core directly under this path; the entire model surface is the gateway. Region-specific gateway options: Alibaba DashScope / Qwen or PAI-EAS DeepSeek in China Landing; customer-approved sovereign endpoints in NS2 and KSA non-regulated.
