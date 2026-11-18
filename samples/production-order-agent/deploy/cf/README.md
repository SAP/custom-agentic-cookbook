# Run the mock sample on Cloud Foundry

This experimental path runs the agent and MCP in one Cloud Foundry app container.
The launcher starts the existing MCP module on loopback before the agent.
It fixes both providers to mock mode and stops both processes if either fails.
MCP has no external route.
The agent uses one instance and loses task state after a restart.

SAP BTP Cloud Foundry does not support container-to-container networking.
This packaging therefore uses loopback communication inside one app.
Read the [SAP feature list](https://help.sap.com/docs/BTP/65de2977205c403bbc107264b8eccf4b/f8a351c8d81544a2942c911dccaba3c7.html).
Read the [Docker deployment guide](https://help.sap.com/docs/BTP/65de2977205c403bbc107264b8eccf4b/c190ad6eeb78428c91a2b66e5557f962.html) for target requirements.

The image exposes only agent port 8000.
Cloud Foundry supplies `PORT` at runtime.
The launcher requires an explicit advertised `URL` and rejects port 8090 for the agent.
It accepts HTTPS origins and loopback HTTP origins for local tests.
The manifest defaults to no route and creates no bindings or services.

## Build and test locally

From the sample directory, install and test the fixed dependencies:

```bash
uv sync --frozen --group dev
uv run --frozen pytest -q
docker build --platform linux/amd64 -f Dockerfile.cf -t production-order-agent:cf-smoke .
```

Start the local container on an unused loopback port:

```bash
docker run --rm --name production-order-cf-smoke \
  --cap-drop ALL --security-opt no-new-privileges=true \
  -p 127.0.0.1:18000:8000 \
  -e PORT=8000 -e URL=http://127.0.0.1:18000 \
  production-order-agent:cf-smoke
```

Use a unique container name if another test uses the example name.
From a second terminal in the sample directory, send a real message:

```bash
uv run --frozen python scripts/smoke_a2a.py --base-url http://127.0.0.1:18000
```

Require a completed task with Released, Partially Confirmed, both operations, and the potential-delay assessment.
An Agent Card alone does not prove the business result.
Stop the exact test container after the test.

## Repeat the container lifecycle test

From the sample directory, obtain the immutable local image ID:

```bash
docker image inspect production-order-agent:cf-smoke --format '{{.Id}}'
```

Set `TEST_IMAGE_ID` to that output. Test all three lifecycle cases:

```bash
uv run --frozen python scripts/verify_container.py --image "$TEST_IMAGE_ID" --mode cf
uv run --frozen python scripts/verify_container.py --image "$TEST_IMAGE_ID" --mode cf --fail-child mcp
uv run --frozen python scripts/verify_container.py --image "$TEST_IMAGE_ID" --mode cf --fail-child agent
```

Each case requires the business reply and MCP on loopback.
The test requires UID 10001, zero capabilities, and the default seccomp filter.
Graceful shutdown must exit zero. Each child failure must stop its sibling and exit one.
Each case removes its exact container and network, then requires the port to close.
These tests do not change Cloud Foundry or remove the image.

## Select and approve the target

Select an existing Cloud Foundry org and space that you can use for this test.
Use the target-issued API endpoint and account login flow.
Do not copy an endpoint or identity from another landscape.
Make sure that Docker deployment, image architecture, quota, and registry access work on the selected target.
Current regional availability does not prove these target requirements.

Select a new app name and a new route for this test.
Record the exact app and route ownership before any change.
Keep registry credentials and service keys outside the manifest and chat.
This fixed-mock path does not consume model keys, data keys, or service bindings.

Test the image before requesting approval to publish it.
After the exact registry-push approval, publish the tested image and record its registry digest.
Copy `manifest.yaml` to an ignored local file.
Set its Docker image to the exact approved `repository@sha256:digest` reference.
Set the new app name and approved advertised HTTPS URL.
Keep `instances: 1`, `no-route: true`, and both providers mock.
Do not set `PORT` in the manifest because the platform owns that value.

## Deploy after approval

Obtain approval for the exact app creation and push.
From the sample directory, push only the reviewed local manifest:

```bash
cf push -f your-reviewed-local-cf-manifest.yaml
```

The initial push has no public route.
Make sure that the selected org and space still match the approved target before the push.
Keep the full operation log.
A successful push does not establish a business reply.

The sample provides no inbound application authentication.
Approve the exact unauthenticated development route separately before mapping it.
After mapping approval, map only the new route to this agent app.
Do not map any route to MCP or port 8090.
Make sure that the route points to the only exposed agent port.

Send the smoke message against the approved HTTPS route from the sample directory.
Require the same completed business artifact as the local test.
Record live push, route, business-reply, and cleanup results separately.
Model services, live data, HANA, XSUAA, and Joule require their own implementation and tests.

## Remove only the test resources

Approve removal of the exact new app and route.
Remove the test app without blanket route or service deletion.
Remove the recorded route only if this test created it and no other app uses it.
Make sure that the app and route remain absent.
Preserve existing orgs, spaces, domains, routes, services, bindings, and registry images.
Delete a registry image only after separate approval for that exact digest.
Remove the ignored local manifest after the test.

The recipe remains experimental until the selected live deployment, business reply, and cleanup pass.
Local Docker results do not prove managed Cloud Foundry behavior.
The pinned base and dependency security findings remain separate release gates.
