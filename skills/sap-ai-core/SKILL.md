---
name: sap-ai-core
description: Use this skill when provisioning or calling SAP AI Core — creating service instances, resource groups, deployment configurations, deployments, and OAuth2 client-credentials tokens. Includes per-region model-catalog gotchas so the agent never hardcodes a model that doesn't exist in the customer's region.
---

# SAP AI Core — bootstrap and call

AI Core is SAP's model-hosting surface on BTP. Models are accessed through *deployments*, which sit inside *resource groups*, which sit inside an *AI Core service instance*.

## Bootstrap sequence

```bash
# 1. Service instance + binding (gives you OAuth2 creds)
btp create services/instance --offering-name aicore --plan-name extended \
  --name aicore-coe-pilot --subaccount $SUBACCOUNT
btp create services/binding --binding-name aicore-coe-pilot-key \
  --instance-name aicore-coe-pilot --subaccount $SUBACCOUNT
btp get services/binding aicore-coe-pilot-key --subaccount $SUBACCOUNT --output json > ai-core-key.json

# 2. Extract envs
export AICORE_BASE_URL=$(jq -r .serviceurls.AI_API_URL ai-core-key.json)
export AICORE_AUTH_URL=$(jq -r .url ai-core-key.json)/oauth/token
export AICORE_CLIENT_ID=$(jq -r .clientid ai-core-key.json)
export AICORE_CLIENT_SECRET=$(jq -r .clientsecret ai-core-key.json)

# 3. Token
export TOKEN=$(curl -s -X POST $AICORE_AUTH_URL \
  -d "grant_type=client_credentials" \
  -u "$AICORE_CLIENT_ID:$AICORE_CLIENT_SECRET" | jq -r .access_token)

# 4. Resource group
curl -s -X POST "$AICORE_BASE_URL/v2/admin/resourceGroups" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"resourceGroupId":"coe-pilot"}'

# 5. Find the right model for the region
curl -s "$AICORE_BASE_URL/v2/lm/scenarios/foundation-models/configurations" \
  -H "Authorization: Bearer $TOKEN" -H "AI-Resource-Group: coe-pilot" | jq '.resources[].name'
```

## Region gotchas

| Region | DO NOT use | Use instead |
|--------|-----------|-------------|
| china | `anthropic--*`, `gpt-*` | `mistralai--mistral-large-2407`, local OSS, Qwen via partner |
| ksa | `anthropic--*`, `gpt-*` | `mistralai--mistral-large-2407`, Falcon, local OSS |
| ns2 | hardcoded model | always pull live catalog; restricted by authorization tier |
| commercial | n/a | full catalog |

When in doubt, run `scripts/region-preflight/region-preflight.sh <region>` and check the live catalog before picking.

## Calling a deployment

```python
from gen_ai_hub.proxy.langchain.init_models import init_llm
llm = init_llm(
    "anthropic--claude-sonnet-4-5",
    deployment_id=os.environ["AICORE_MODEL_DEPLOYMENT_ID"],
    temperature=0.0,
)
llm.invoke("hello")
```

The `generative-ai-hub-sdk` reads AICORE_* env vars and handles token refresh.

## Pitfalls

- Forgetting the `AI-Resource-Group` header → 403.
- Calling a deployment before it's `RUNNING` → 503; poll status first.
- Using commercial endpoints from a sovereign region → cross-region call, blocked.
- Burning entitlement: don't leave dev deployments running 24/7 in sovereign regions where capacity is scarce.

## Verify

```bash
curl -s "$AICORE_BASE_URL/v2/lm/deployments/$AICORE_MODEL_DEPLOYMENT_ID" \
  -H "Authorization: Bearer $TOKEN" -H "AI-Resource-Group: $AICORE_RESOURCE_GROUP" \
  | jq -r .status
# expect: RUNNING
```

## Cross-references

- Bootstrap walkthrough: [`recipes/00-develop/00-region-preflight/`](../../recipes/00-develop/00-region-preflight/) for AI Core availability + entitlement check; [`recipes/optional/sovereign-model-gateway/`](../../recipes/optional/sovereign-model-gateway/) for the `openai-compatible` fallback when AI Core is not in-region.
- [`sap-sovereign-regions`](../sap-sovereign-regions/SKILL.md) and its [`btp-regional-availability.md`](../sap-sovereign-regions/references/btp-regional-availability.md) reference — source-backed per-region service and model guardrails.
- Upstream: `github.tools.sap/joule-demos/ai-core-onboarding-guide`
