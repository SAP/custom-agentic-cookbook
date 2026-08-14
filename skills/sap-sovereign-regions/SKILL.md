---
name: sap-sovereign-regions
description: Use this skill before suggesting any SAP AI Core model, Joule capability, or BTP service in a recipe or generated code. Encodes the model and service availability deltas for China Landing, NS2, KSA, and commercial regions so the agent never recommends something that doesn't exist in the customer's region.
---

# SAP Sovereign Regions — what works where

When generating code or recipes for a SAP customer, **always** check region context first. China and KSA have no Anthropic/OpenAI models in AI Core; NS2 has a gated subset. Hardcoding a wrong model produces a 403 at deploy time — the highest-cost failure mode for sovereign pilots.

## Decision rule

1. If the user has named a region (`china`, `ns2`, `ksa`, `commercial` / EU/US/AP), use it.
2. If they haven't but the prompt mentions sovereign keywords ("21Vianet", "FedRAMP", "Saudi", "国产化", "ITAR"), infer the region and confirm.
3. If still ambiguous, ASK before generating code.

## Model availability (June 2026 snapshot — verify against live catalog)

| Family | commercial | china | ns2 | ksa |
|--------|-----------|-------|-----|-----|
| Anthropic Claude | ✅ Sonnet/Opus 4.x | ❌ | ⚠ subset | ❌ |
| OpenAI GPT | ✅ 4o/5/o-series | ❌ | ⚠ subset | ❌ |
| Mistral | ✅ | ✅ Large 2407 | ⚠ check | ✅ Large 2407 |
| Llama / SAP-hosted OSS | ✅ | ✅ preferred | ✅ | ✅ |
| Qwen / DeepSeek | rare | ✅ via partner | ❌ | rare |
| Falcon | rare | rare | rare | ✅ |
| Embeddings (OpenAI) | ✅ | ❌ | ⚠ subset | ❌ |
| Embeddings (multilingual SAP-hosted) | ✅ | ✅ | ✅ | ✅ |

## Default picks for new recipes

| Region | LLM | Embedding |
|--------|-----|-----------|
| commercial | `anthropic--claude-sonnet-4-5` | `text-embedding-3-large` |
| china | `mistralai--mistral-large-2407` | SAP-hosted multilingual |
| ns2 | pull live catalog; never default | pull live catalog |
| ksa | `mistralai--mistral-large-2407` | SAP-hosted multilingual (verify Arabic quality) |

## Other deltas

| Capability | china | ns2 | ksa |
|---|---|---|---|
| Cross-region egress | blocked | blocked (FedRAMP) | restricted |
| Public PyPI / Docker Hub | blocked; use mirrors | mirror only | mirror only |
| Joule UI | gated | gated | GA |
| Joule Studio 2.0 / BAIP | later | later | later |

## When you must hardcode a region default

Don't. Scaffold with `/sap-a2a-agent-toolkit:create-agent` from the A2A Agent Toolkit submodule at [`toolkits/a2a-agent-toolkit/`](../../toolkits/a2a-agent-toolkit/) instead, passing `--llm-provider aicore` or `--llm-provider openai-compatible` based on live preflight output and the source-backed regional reference in [`references/btp-regional-availability.md`](references/btp-regional-availability.md). The generated project reads the model name from an env var (`MODEL_NAME` for AI Core, `MODEL_GATEWAY_URL` + gateway-side deployment name for `openai-compatible`) — never inline a model name in a template's source code.

## Verify

```bash
# Confirm a model is available in the customer's region:
curl -s "$AICORE_BASE_URL/v2/lm/scenarios/foundation-models/configurations" \
  -H "Authorization: Bearer $TOKEN" -H "AI-Resource-Group: $AICORE_RESOURCE_GROUP" \
  | jq -r '.resources[].name' | grep -i "$MODEL_QUERY"
```

## Cross-references

- [`references/btp-regional-availability.md`](references/btp-regional-availability.md) — source-backed regional availability matrix and operating guidance
- Region-aware bootstrap walkthrough: [`recipes/00-develop/00-region-preflight/`](../../recipes/00-develop/00-region-preflight/)
