# Experimental single-turn CMJ bundle

Status: partial. The local Python protocol path works.
The Joule compiler, response handling, authentication, visible Joule answer, and
cleanup remain unproven. Do not treat these files as a completed Joule checkpoint.

CMJ means Customer-Managed Joule. DTA means design-time artifact.
DA means digital assistant.
This four-file DTA bundle targets the existing production-order sample.
It uses one synchronous request with the current utterance.
It does not store conversation context or support streaming and push notifications.
The selected CMJ tenant must support DTA 3.28.0.
The example namespace `joule.ext` and names must pass its role and schema policy.

From the sample directory, run the mock MCP server and agent in separate terminals:

```bash
uv run --frozen python -m production_order_agent.mcp_server
```

```bash
uv run --frozen python -m production_order_agent --joule-v03
```

The explicit option enables the SDK's v0.3 `message/send` adapter.
It adds a legacy card at `/.well-known/agent.json`.
The current v1 card and `SendMessage` remain available.
Without the option, the v1-only default remains.
The legacy card uses the SDK converter and an advertised v0.3 interface.

Run the HTTP test in another terminal:

```bash
uv run --frozen python scripts/smoke_joule.py --base-url http://127.0.0.1:8000
```

The test requires a completed task with status, operations, and delay text from
both mock MCP datasets. It proves local A2A behavior.
It does not run a Joule action.
After testing, stop both local processes with Ctrl-C.

## Repeat the container protocol test

From the sample directory, build the amd64 image:

```bash
docker build --platform linux/amd64 --file Dockerfile.mock --tag production-order-agent:joule-smoke .
docker image inspect production-order-agent:joule-smoke --format '{{.Id}}'
```

Set `TEST_IMAGE_ID` to the immutable image ID. Test that image:

```bash
uv run --frozen python scripts/verify_container.py --image "$TEST_IMAGE_ID" --mode joule
```

The test requires completed v0.3 and v1 business replies through private MCP.
After MCP stops, the test requires failed v0.3 and v1 tasks with only the safe error artifact.
It requires UID 10001, zero capabilities, and the default seccomp filter.
It removes its exact containers and network, then requires the loopback port to close.
This test does not call Joule or prove its action wrapper.

## Bundle contract

`da.sapdas.yaml` includes the capability in this directory.
The intent scenario selects `functions/call_agent.yaml`.
Its alias selects `COOKBOOK_PRODUCTION_ORDER_A2A` in `capability.sapdas.yaml`.
After separate approval, create that destination manually in the selected existing CMJ subaccount.
Use the selected HTTPS agent base URL instead of its card path.

The current sample has no endpoint authentication.
Prepare an authenticated HTTPS route before compiler upload.
Use the selected tenant's OAuth2 client-credentials destination.
Obtain its issuer, audience, token endpoint, scopes, and approved client access first.
Keep the client credentials outside Git and local evidence.
Test a rejected unauthenticated request and a successful authenticated business request.
MCP must remain private. Authentication and destination tests need the selected tenant.

The function assumes that Joule exposes the task under `agent_result.body`.
Here, the response wrapper means the object that contains the task.
Local HTTP returns a JSON-RPC wrapper whose `result` contains the v0.3 task.
It does not prove Joule's internal wrapper. The function does not guess other wrappers.

For a completed task, the function selects the first `production-order-summary`
artifact's first text part. An artifact is data that a task returns.
Other results retain a safe constant reply. This matches the pinned starter contract.
The function does not search arbitrary artifacts or expose task IDs and backend diagnostics.

`getSafe` and `orElse` follow official Joule scripting guidance.
Actual Joule evaluation must test missing values, wrong types, and empty or whitespace text.
It must also test failed tasks, JSON-RPC errors, and transport timeouts.
An initialized reply does not prove that actions continue after a transport failure.
YAML parsing alone does not prove response handling or error recovery.

## Remaining platform tests

Use external legacy `@sap/joule-studio-cli@1.5.21` with compatible Node.
The compiler uploads the bundle and creates an authenticated remote job.
Before running it, obtain separate upload approval for the selected tenant.
No compiler ran here.

Inspect its output.
Make sure that the descriptor name, schemas, namespace, alias, and function names pass.
After separate deployment approval, inspect the Joule action wrapper with synthetic data.
Test the response conditions in Joule.
Then ask “Why is production order 1000000 delayed?” in CMJ.
Require a visible answer from the tools within Joule's 60-second synchronous limit.
Mock latency does not prove the full deployed or model deadline.
See [recipe 03](../../../recipes/03-joule/).

After cleanup approval, remove only this added capability from the selected DA.
Use the pinned CLI's documented `joule remove <DA> --capability <namespace>:<name>` command.
Remove or restore only the destination owned by this test.
Make sure that unrelated DA capabilities and tenant resources remain intact.

## Public source

The four-file structure adapts the Apache-2.0 public
[Joule toolkit reference at 7d284bd6](https://github.com/SAP-samples/joule-a2a-agent-toolkit/blob/7d284bd6d6e83f2ce9e3bf164689adc9db9ad4f1/skills/joule-a2a-agent/references/joule-capability.md).
It does not use that reference's multi-turn or status-message snippets.
Retain the repository's Apache-2.0 notices.
This adaptation does not provide toolkit parity.
Official references are [BYOA](https://help.sap.com/docs/JOULE/ba88d1ec6a1b442098863d577c19b0c0/2f9701e60fd24e948c2c74fe9e55ce23.html?version=CLOUD),
[SpEL safe access](https://help.sap.com/docs/JOULE/ba88d1ec6a1b442098863d577c19b0c0/a96708519552494cbaef4ab81bf94a21.html?version=CLOUD),
and [CLI removal](https://help.sap.com/docs/JOULE/ba88d1ec6a1b442098863d577c19b0c0/3fa5325ef29246da9b4ddc4ea54eafe0.html?version=CLOUD).


## Native response-validation gap

The current `answer_text != ''` expression does not independently reject a
whitespace-only string. Actual Joule evaluation must cover space, tab/newline,
U+2003, null, list, map, Boolean and numeric text values, as well as missing
fields and transport failures. A local Python contract or YAML parse cannot
prove the selected Joule runtime's type handling, Unicode checks, response
wrapper or continuation after transport errors. Keep these cases as open
native acceptance requirements; do not assume that a trim-only change clears
them. The current bundle is an experimental proposal for native validation.
