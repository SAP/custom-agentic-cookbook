---
title: Build with your coding assistant
sap-services: []
region-availability: development-time practice
complexity: beginner
last-validated: 2026-10-29
---

# Build with your coding assistant

Use your coding assistant to adapt an existing agent and supply repeatable verification.
This optional recipe supports checkpoint 1. It requires no BTP service.
A coding harness is the application that runs your assistant.

> Guided: Start from checkpoint 1 or an existing agent.
> Input: A Cookbook clone and the behavior that you want.
> Output: A reviewed agent change with a real message reply and cleanup evidence.
> Toolkit command: None. This exercise uses the checked-in public starter.

## Open the workspace

Clone the public Cookbook:

~~~bash
git clone https://github.com/SAP/custom-agentic-cookbook.git
cd custom-agentic-cookbook
~~~

Open this directory in your coding harness.
Ask the assistant to read [AGENT-CONTEXT.md](../../../AGENT-CONTEXT.md) and the
selected sample README before editing. Do not assume that every harness loads
this context automatically. The public starter runs from a terminal; it does
not require a toolkit plugin or a harness-specific MCP driver.

## State the change

Supply the expected behavior, selected sample, target environment, and constraints.
For example:

~~~text
Read AGENT-CONTEXT.md and the selected sample README.
Adapt this agent to answer the specified business question.
Preserve its supported A2A protocol and existing default behavior.
Use mock data for the first local test.
Preserve unrelated work in this workspace.
Show the changed files, real message reply, failure result, and cleanup evidence.
Do not deploy or publish anything.
~~~

For local architecture planning, invoke the
[setup skill](../../../skills/sap-setup-btp-agent/SKILL.md).
It writes a credential-free pilot manifest that the
[coordinator](../../../docs/cookbookctl.md) can validate and render locally.
It does not provision BTP or deploy this agent. The mock exercise needs no
pilot manifest. Any live change requires separate explicit approval.

For a backend integration, supply an approved API specification or metadata source.
Keep authentication values outside chat and Git.
Require explicit errors when the backend fails. Do not permit a hidden mock fallback.

## Review the change

Read the diff before accepting the implementation.
Make sure that the selected sample supplies every referenced file and dependency.
Make sure that the assistant preserves the protocol, default behavior, and credential boundaries.
Require the documented happy path and a relevant failure path.

The selected source code and sample README define their extension interfaces.
Do not require a universal four-file layout or a universal port.
Do not copy an old REST stream request into an A2A JSON-RPC test.

## Verify it works

### Public production-order exercise

Use this concrete local exercise before adapting a live backend. It uses
public dependencies and synthetic records. It does not need a toolkit or a
BTP account. The exercise retains an immutable public commit for repeatability;
its validation applies to that pinned version, not to later packaging changes.
Run the commands in one Bash terminal on macOS or Linux.
Install Git, Bash, Python 3.12 or newer below 3.15, and
[uv](https://docs.astral.sh/uv/getting-started/installation/) first.

~~~bash
git clone https://github.com/SAP/custom-agentic-cookbook.git cookbook-assistant-exercise
cd cookbook-assistant-exercise
git switch --detach 6e56cca48bf20e446d9644f18847864b975318e5
git switch -c exercise/coding-assistant
cd samples/production-order-agent
uv sync --frozen --group dev
~~~

Ask your assistant to make this small change and show the diff:

~~~text
In the public production-order sample, change only the mock operation 0010
description from "Prepare components" to "Prepare mock components for validation".
Keep both MCP tool names, statuses, dates, confirmations, and A2A v1 unchanged.
Run the frozen tests and prove that the changed text reaches the A2A artifact.
Stop the MCP process and require a failed task. Remove only the test processes.
~~~

Read the change in `src/production_order_agent/mcp_server.py`.
Before you start the servers, run the tests and formatting commands:

~~~bash
uv run --frozen --group dev pytest -q
uv run --frozen --group dev ruff check .
uv run --frozen --group dev ruff format --check .
git diff --check
git diff -- src/production_order_agent/mcp_server.py
~~~

This block requires free ports and starts the test processes.
It sends a real message and tests backend failure.
It makes sure that the ports close after cleanup.
It keeps logs and JSON replies in a temporary evidence directory outside Git.

~~~bash
(
set -euo pipefail
umask 077
proof_dir=$(mktemp -d)
printf 'Evidence directory: %s\n' "$proof_dir"
mcp_pid=
agent_pid=
cleanup_assistant_exercise() {
  for recipe_pid in "$mcp_pid" "$agent_pid"; do
    if [ -n "$recipe_pid" ]; then
      kill "$recipe_pid" 2>/dev/null || true
      wait "$recipe_pid" 2>/dev/null || true
    fi
  done
  mcp_pid=
  agent_pid=
}
trap cleanup_assistant_exercise EXIT
.venv/bin/python - <<'PY'
import socket
for port in (18080, 18090):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", port))
PY
DATA_MODE=mock MCP_HOST=127.0.0.1 MCP_PORT=18090 \
  .venv/bin/python -m production_order_agent.mcp_server >"$proof_dir/mcp.log" 2>&1 &
mcp_pid=$!
HOST=127.0.0.1 PORT=18080 URL=http://127.0.0.1:18080 \
MCP_SERVER_URL=http://127.0.0.1:18090/sse LLM_PROVIDER=mock \
  .venv/bin/python -m production_order_agent >"$proof_dir/agent.log" 2>&1 &
agent_pid=$!
.venv/bin/python - <<'PY'
import socket, time
for port in (18080, 18090):
    deadline = time.monotonic() + 15
    while True:
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                break
        if time.monotonic() >= deadline:
            raise RuntimeError(f"Test server on port {port} did not start")
        time.sleep(0.1)
PY
.venv/bin/python scripts/smoke_mcp.py --server-url http://127.0.0.1:18090/sse
.venv/bin/python - <<'PY' >"$proof_dir/business.json"
import json, sys
sys.path.insert(0, "scripts")
from smoke_a2a import run
result = run("http://127.0.0.1:18080")
assert "Prepare mock components for validation" in result["reply"]
print(json.dumps(result, indent=2))
PY
cat "$proof_dir/business.json"
kill "$mcp_pid"
wait "$mcp_pid" || true
mcp_pid=
.venv/bin/python - <<'PY' >"$proof_dir/failure.json"
import json, httpx
with httpx.Client(timeout=30, trust_env=False) as client:
    response = client.post("http://127.0.0.1:18080/",
        headers={"A2A-Version": "1.0"},
        json={"jsonrpc": "2.0", "id": "failure", "method": "SendMessage",
              "params": {"message": {"messageId": "failure", "role": "ROLE_USER",
                         "parts": [{"text": "Why is production order 1000000 delayed?"}]}}})
    response.raise_for_status()
    result = response.json()
assert result["result"]["task"]["status"]["state"] == "TASK_STATE_FAILED"
print(json.dumps(result, indent=2))
PY
cleanup_assistant_exercise
.venv/bin/python - <<'PY'
import socket
for port in (18080, 18090):
    with socket.socket() as probe:
        assert probe.connect_ex(("127.0.0.1", port)) != 0, f"Test port {port} remains open"
print("Owned processes stopped; ports 18080 and 18090 closed")
PY
printf 'Evidence directory: %s\n' "$proof_dir"
)
~~~

The completed answer must include the changed description, Released,
Partially Confirmed, operations 0010 and 0020, and potential delay for
the unconfirmed operation 0020. The failure JSON must contain a failed task.
Keep the public base, final change commit, diff, commands, and results with
the evidence. Delete the temporary evidence directory only after review.

### Other selected samples

Start from a clean clone of the final commit.
Install the selected sample dependencies with its frozen installation command.
Run its documented tests and start its agent and required MCP service.
An MCP service exposes tools for the agent.

Send the documented A2A business message.
Make sure that the completed artifact contains the expected records and assessment.
An Agent Card proves discovery only. It does not prove that tools or business answers work.

Stop or disconnect the test backend.
Send another message and make sure that the documented failure reaches the caller.
Record the tested commit, commands, result, and image digest when a container is used.
A digest identifies the exact image contents.

Use the cleanup commands from the selected sample README.
Make sure that the test processes, containers, ports, and exact test resources are absent.
Do not remove shared services or unrelated workspace files.

## Continue

Use [checkpoint 2](../../02-deploy-btp/README.md) for an approved BTP deployment.
Use [checkpoint 3](../../03-joule/README.md) for an enabled Joule tenant.
Use [connect-data](../connect-data/README.md) only when the user requests business data.
Use [CONTRIBUTING.md](../../../CONTRIBUTING.md) before preparing a contribution.

## Troubleshooting

If a referenced file is absent, make sure that the assistant selected the correct implementation and current recipe.
If tools fail, compare the request with the approved API metadata before changing the agent prompt.
If startup works but the answer fails, use the sample's business message test and troubleshooting guidance.
If the assistant proposes a live change, review its exact target and scope and
obtain separate explicit approval before executing it.
