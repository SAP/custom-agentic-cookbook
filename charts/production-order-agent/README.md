# Production-order agent chart

This experimental chart deploys the checked-in Python agent and its MCP tools to an existing Kyma cluster.
Both processes use one image pinned by digest.
Both use mock data and mock summaries without credentials.
The agent keeps task state in memory and supports one replica.

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
