# Observed production-order agent chart

This experimental chart deploys the checked-in Python agent and its MCP tools to an existing Kyma cluster.
Both processes use one image pinned by digest.
Both use mock data and mock summaries without credentials.
The agent keeps task state in memory and supports one replica.

Build the SDK-free image with the sample's `Dockerfile.telemetry`.
Follow [recipe 02](../../recipes/02-deploy-btp/) for image preparation, deployment, a real A2A message, and cleanup.
Set `image.repository`, `image.tag`, and `image.digest` before rendering or installing the chart.
Use existing Secret names in `imagePullSecrets` when your registry requires authentication.
The chart creates no Secrets, service bindings, or BTP resources.

The two Services stay inside the cluster by default.
The agent listens on port `8000` and calls the MCP Service on port `8090`.
ClusterIP access does not provide authentication.
The Agent Card and TCP probes show process availability, without proof of a business reply.

Enable `apirule.enabled` only for an approved development or smoke test.
Set `apirule.host` and explicitly set `apirule.noAuth=true` for that path.
The APIRule exposes only the agent through the existing Kyma gateway.
The MCP Service has no external route.

Telemetry export is disabled by default for both processes.
For the agent, select `telemetry.enabled=true`, an approved HTTP/protobuf gateway base in `telemetry.endpoint`, and a bounded `telemetry.scope`.
The image must include the sample's optional `telemetry` extra.
Use the same scope in the separately managed Cloud Logging pipeline chart.
The release namespace supplies `TELEMETRY_NAMESPACE`.
The MCP process exports no telemetry through this option.
The agent records its own two MCP client spans.
This setting creates no Cloud Logging service, binding, Secret, or pipeline.
Follow the [Cloud Logging recipe](../../recipes/optional/sap-cloud-logging/) for pipeline ownership and separate export approval.

Use a dedicated release and namespace for this observed application.
