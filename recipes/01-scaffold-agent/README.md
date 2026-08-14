---
title: "Scaffold your agent — toolkit driver + a running A2A agent with mock data"
sap-services: []
complexity: recipe
last-validated: 2026-07-10
changes-under-baip: "The scaffolder's `--llm-provider` flag is the port-back boundary: when BAIP is GA in-region, swap the provider without touching the A2A endpoint, Joule capability bundle, or project shape."
---

# 01 · Scaffold your agent

> **Guided:** checkpoint 1 — `/start` runs this end-to-end. Mid-flow prompt: *"Set up the toolkit and scaffold my agent — here's what it should do: …"*
> **Flow:** first checkpoint — no upstream step. Hands off to **[02-deploy-btp](../02-deploy-btp/)**; connect live data anytime via **[optional/connect-data](../optional/connect-data/)**.
> **Input:** a laptop with Claude Code (or an MCP-capable harness) and **one LLM endpoint** — an SAP AI Core instance with a deployed model, or any OpenAI-compatible endpoint (base URL + key). **No BTP account needed.**
> **Output:** your agent project (worked example: `sales-order-agent/`) running on `localhost:8080` and replying to real messages **with mock data** — consumed by **02-deploy-btp**, and by **optional/connect-data** when you want a live backend.
> **Toolkit command:** `/sap-a2a-agent-toolkit:create-agent <name> --prompt "…"`.

Install the toolkit driver, scaffold *your* agent, run it locally, and talk to it. The generated tools return **mock data** (TODO-marked bodies tailored to your purpose), so the agent converses and demos end-to-end without touching any backend system. Everything in this checkpoint happens on your laptop — BTP, entitlements, and the region question all wait until [02-deploy-btp](../02-deploy-btp/); live business data is an opt-in via [optional/connect-data](../optional/connect-data/).

## 1. Local prerequisites

| Tool | Version | Why |
|---|---|---|
| Claude Code — or one of {Codex, Cursor, OpenCode, Gemini CLI, Cline} | current | Runs the toolkit. The Claude Code plugin is the default driver; the MCP server and raw shell scripts are the alternatives. |
| Node.js | **24.x** | TypeScript agents (Express or CAP). |
| Python | **3.12+** | Only if you scaffold `--lang python`. |

**Windows:** use WSL2 with Ubuntu and install Claude Code plus the selected scaffold runtime inside WSL. Follow [Windows + WSL2 setup](../../docs/windows-wsl2.md) before continuing; do not run the cookbook from native PowerShell, Command Prompt, or Git Bash.

**Not needed yet:** `cf` / `btp` CLIs, Joule Studio CLI, `mbt` — those enter at [02-deploy-btp](../02-deploy-btp/). No S/4HANA or other backend either — the scaffold ships mock data.

One command checks all of this and prints the fix for anything missing: `bash scripts/doctor/doctor.sh` (from the Cookbook root).

## 2. Install the toolkit driver

### Driver A — Claude Code plugin (default)

```bash
# From the Cookbook root — clone the toolkit into toolkits/a2a-agent-toolkit, then launch Claude Code with the plugin:
git clone https://github.com/SAP-samples/joule-a2a-agent-toolkit.git toolkits/a2a-agent-toolkit
claude --plugin-dir toolkits/a2a-agent-toolkit
```

The `--plugin-dir` flag loads the toolkit for that session and needs no prompt. To have plain `claude` from the repo root load it automatically in later sessions, add a `.claude/settings.json` pointing at the plugin directory.

Verify: type `/` — the `sap-a2a-agent-toolkit:` commands (`create-agent`, `deploy-agent`, `create-destination`) appear in the list. If they don't, see [Troubleshooting](#6-troubleshooting).

<details>
<summary>Driver B — MCP server · Driver C — raw shell scripts</summary>

**MCP server** (Codex, Cursor, OpenCode, Gemini CLI, Cline) — the package is
not published and must be built from the vendored submodule:

```bash
git submodule update --init toolkits/a2a-agent-toolkit
./scripts/build-toolkit-mcp.sh
```

Then configure the harness to spawn the absolute path to
`scripts/start-toolkit-mcp.sh`. For example, Codex uses
`~/.codex/config.toml`:

```toml
[mcp_servers.sap_a2a_toolkit]
command = "/absolute/path/to/Cookbook/scripts/start-toolkit-mcp.sh"
```

The harness starts this local stdio process; it is not a hosted service. Launch
the harness from the target workspace so generated projects land there. See
[`docs/harnesses.md`](../../docs/harnesses.md) for all supported harness
configurations.

**Shell scripts** (CI, air-gapped laptops, no LLM in the loop) — documented in [`SCRIPTS.md`](https://github.tools.sap/agent-assisted-coding/A2A-Agent-Toolkit-Plugin/blob/main/SCRIPTS.md):

```bash
bash toolkits/a2a-agent-toolkit/skills/joule-a2a-agent/scripts/scaffold-ts.sh --help   # TypeScript
python toolkits/a2a-agent-toolkit/skills/joule-a2a-agent/scripts/scaffold.py --help    # Python
```

All three drivers produce byte-identical projects for the same inputs.

</details>

## 3. Scaffold your agent

In the selected coding-agent session, describe what you want—the prompt is the
interface:

> Scaffold a new A2A agent named `<name>` with LLM provider `<aicore|openai-compatible>`. Purpose: <one sentence — what it does and for whom>.

The harness runs the toolkit's `create-agent` flow with the prompt, which
tailors the system prompt, tools, and AgentCard skills to your purpose (you'll
get a short spec summary to confirm before it generates). The emitted tools
carry mock data matched to the purpose—swapping them for a live backend is
[optional/connect-data](../optional/connect-data/). The worked example used
throughout this cookbook is `sales-order-agent`—purpose: *"answer questions
about S/4HANA sales orders for sales teams"*—but use your own.

Pick the provider by what you have: `aicore` if you have an AI Core instance with a deployed model, `openai-compatible` for any other endpoint (also the required path in sovereign regions without AI Core — see [`../optional/sovereign-model-gateway/`](../optional/sovereign-model-gateway/), which you can wire later).

**Stacks — the toolkit offers exactly three.** If you don't say otherwise, you get the default:

| Stack | When |
|---|---|
| **TypeScript + Express** (default) | Lightest scaffold, in-memory task store — right for most pilots. |
| **TypeScript + CAP** | CAP/MTA project shape — required for the durable HANA task store, natural for CAP shops. |
| **Python** (`--lang python`) | The four-file a2a-sdk/uvicorn shape — pick it when your team extends agents in Python. (The toolkit's interview labels this "Python + Express"; there's no Express involved.) |

**Heading to production?** Add one line to the prompt — *"use a durable HANA task store so multi-turn conversations survive restarts"* — and Claude scaffolds the CAP + MTA variant (`--framework cap --taskstore hana`) instead of in-memory Express. Everything downstream works the same; the HANA entitlement is verified at [02-deploy-btp](../02-deploy-btp/).

<details>
<summary>Other drivers — equivalent invocations</summary>

**MCP:** *"Use the sap-a2a-toolkit MCP to scaffold a TypeScript Express A2A agent named `<name>` with LLM provider `<aicore|openai-compatible>`. Purpose: `<purpose>`."*

**Shell script:**

```bash
bash toolkits/a2a-agent-toolkit/skills/joule-a2a-agent/scripts/scaffold-ts.sh \
  --name <name> \
  --framework express \
  --llm-provider <aicore|openai-compatible>
```

</details>

## 4. Provide model credentials and run it

Export the env vars **the generated code actually reads** — check the scaffold's `.env.example`:

```bash
# aicore: the AI Core service-key vars the scaffold lists
# openai-compatible (toolkit ≥ v0.6.0):
export MODEL_GATEWAY_URL=https://<your-endpoint>/v1
export MODEL_GATEWAY_API_KEY=<secret>        # never commit; never paste into chat
export MODEL_NAME=<model-or-deployment-name>

cd <name>
npm install && npm start                     # Python: pip install -r requirements.txt && python .
# serves on http://localhost:8080
```

## 5. Verify it works — the chat proof

```bash
# 1. Agent Card resolves (path per the scaffold's a2a-sdk version — check the generated code):
curl -s http://localhost:8080/.well-known/agent.json | jq .name
# expect: "<name>"

# 2. Readiness check, from the Cookbook root:
BASE_URL=http://localhost:8080 AGENT_CARD_PATH=/.well-known/agent.json \
  python3 references/gitops-workflows/scripts/smoke-a2a.py
```

Then send one real message—in the coding-agent session, ask: *"Send the running
agent a test message ('introduce yourself') and show me its reply."* The harness
derives the JSON-RPC envelope from the scaffolded code. Ask it something
in-domain too ("which sales orders are open?")—it answers from the mock data,
which is exactly right at this checkpoint. **The reply—not the Agent Card—is
checkpoint 1.**

## 6. Troubleshooting

**Plugin commands not discovered (`/sap-a2a-agent-toolkit:create-agent` unknown).** The plugin didn't load. Most common cause: the toolkit isn't cloned yet — run `git clone https://github.com/SAP-samples/joule-a2a-agent-toolkit.git toolkits/a2a-agent-toolkit`, then relaunch with `claude --plugin-dir toolkits/a2a-agent-toolkit`. If `toolkits/a2a-agent-toolkit` already exists but is empty, delete it and re-clone.

**MCP server absent from the assistant's tool list.** Run
`./scripts/build-toolkit-mcp.sh`, verify the harness command is the absolute path
to `scripts/start-toolkit-mcp.sh`, and restart or reload the harness. Do not use
the unpublished `@sap/a2a-toolkit-mcp` package through `npx`. Per-harness paths
and reload behavior are documented in
[`docs/harnesses.md`](../../docs/harnesses.md).

**Agent starts but replies with a model/auth error.** The env vars don't match what the scaffold reads — compare your exports against the generated `.env.example` (v0.6.0 sovereign scaffolds read `MODEL_GATEWAY_URL` / `MODEL_GATEWAY_API_KEY`; older ones read `OPENAI_BASE_URL` / `OPENAI_API_KEY`).

**Something else.** File a *cookbook gap* issue: [`.github/ISSUE_TEMPLATE/cookbook-gap.yml`](../../.github/ISSUE_TEMPLATE/cookbook-gap.yml).

## Next

Deploy it — [02-deploy-btp](../02-deploy-btp/). Want live business data first (or after deploying)? [optional/connect-data](../optional/connect-data/) swaps the mock tools for a real backend — S/4HANA via the free api.sap.com sandbox if you don't have a tenant.
