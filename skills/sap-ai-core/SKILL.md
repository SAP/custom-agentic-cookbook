---
name: sap-ai-core
description: Use this skill when configuring or calling SAP AI Core — obtaining service-key credentials, configuring sap-ai-sdk-gen, checking resource groups and deployments, and making model calls without exposing secrets.
---

# SAP AI Core — configure and call

SAP AI Core exposes models through deployments inside resource groups. Before
selecting it, run the
[`region-preflight`](../../recipes/optional/region-preflight/) and confirm that
the target subaccount has both the service entitlement and usable quota. Do not
infer availability from a region name or hardcode a model name.

## Obtain a service key

An administrator can create the prerequisites in SAP BTP Cockpit:

1. Under **Entitlements**, assign the SAP AI Core `extended` plan and quota to
   the target subaccount.
2. Under **Services → Instances and Subscriptions**, create an SAP AI Core
   instance using that plan.
3. Open the instance, create a service key, and download its JSON through the
   approved secret-handling channel.

Store the downloaded key outside the repository with owner-only permissions.
Never paste the key, client secret, access token, certificate, or complete
environment file into chat, logs, source control, or an image.

## Configure credentials

Use the current SAP AI SDK packages. `generative-ai-hub-sdk` is deprecated; use
`sap-ai-sdk-gen` for model calls and `sap-ai-sdk-core` for the configuration
CLI.

```bash
uv add sap-ai-sdk-gen sap-ai-sdk-core
(
  set -e
  umask 077
  uv run aicore configure --service-key-json /secure/path/aicore-service-key.json
  chmod 600 ~/.aicore/config.json
)
```

The command writes an owner-only profile under `~/.aicore/`. Alternatively,
map the service key into environment variables through a local secret manager
or deployment secret:

| Environment variable | Service-key value |
| --- | --- |
| `AICORE_AUTH_URL` | `url` plus `/oauth/token` |
| `AICORE_CLIENT_ID` | `clientid` |
| `AICORE_CLIENT_SECRET` | `clientsecret` |
| `AICORE_BASE_URL` | `serviceurls.AI_API_URL`, ending in `/v2` |
| `AICORE_RESOURCE_GROUP` | Resource group containing the deployment |

X.509 authentication may use `AICORE_CERT_FILE_PATH` and
`AICORE_KEY_FILE_PATH` instead of a client secret when the service key and
tenant support it.

## Verify authentication and resources

Capture the OAuth token in a shell variable; do not print it:

```bash
TOKEN=$(curl --fail --silent --show-error \
  -X POST "$AICORE_AUTH_URL" \
  -u "$AICORE_CLIENT_ID:$AICORE_CLIENT_SECRET" \
  -d 'grant_type=client_credentials' \
  | jq -er .access_token)

curl --fail --silent --show-error \
  "$AICORE_BASE_URL/lm/deployments" \
  -H "Authorization: Bearer $TOKEN" \
  -H "AI-Resource-Group: $AICORE_RESOURCE_GROUP" \
  | jq '.resources[] | {id, status, scenarioId}'

unset TOKEN
```

At least one appropriate foundation-model deployment must be `RUNNING`. If the
resource group or deployment is managed centrally, ask its owner rather than
creating a duplicate. Use SAP AI Launchpad or the documented AI Core lifecycle
API to create missing resources only after the user approves the live and
potentially billable change.

## Call a model from Python

Read the model name from configuration and let `sap-ai-sdk-gen` select a
matching deployment in the configured resource group:

```python
import os

from gen_ai_hub.proxy.native.openai import OpenAI

client = OpenAI()
response = client.chat.completions.create(
    model=os.environ["MODEL_NAME"],
    temperature=0,
    messages=[{"role": "user", "content": "Summarize this production order."}],
)
print(response.choices[0].message.content)
```

For local development, run `aicore configure` first. In Cloud Foundry or Kyma,
inject the same `AICORE_*` names from a service binding or secret; never bake
them into the application or container.

## Common failures

| Symptom | Check |
| --- | --- |
| `401 Unauthorized` | Reconfigure the client ID and secret; do not print them while debugging. |
| `404 Not Found` | Ensure `AICORE_BASE_URL` ends in `/v2`. |
| `403 Forbidden` | Confirm `AICORE_RESOURCE_GROUP` and the caller's authorization. |
| `503` or deployment unavailable | Wait for the selected deployment to reach `RUNNING`. |
| No deployment for the model | Query the live catalog/deployments and choose a model available in this region and resource group. |

## Verify

Run the deployment query above and confirm the intended deployment reports
`RUNNING`, then execute one minimal SDK call without logging credentials or the
token.

## Related guidance

- [`recipes/optional/region-preflight/`](../../recipes/optional/region-preflight/)
- [`recipes/optional/sovereign-model-gateway/`](../../recipes/optional/sovereign-model-gateway/)
- [`sap-sovereign-regions`](../sap-sovereign-regions/SKILL.md)
