# Optional · Region Preflight

> **Flow:** diagnostic — run before **[02-deploy-btp](../../02-deploy-btp/)** whenever the target region is sovereign, regulated, or unfamiliar. Not needed for the local checkpoint (1).
> **Guided:** `/start` runs this automatically at **checkpoint 2** when the region calls for it, deriving the landscape from the subaccount. Mid-flow prompt: *"Run the region preflight for my subaccount and pick the LLM path."*
> **Input:** a target BTP region and a customer subaccount ID.
> **Output:** the `--llm-provider` decision (`aicore` | `openai-compatible`) and runtime hint (CF | Kyma), consumed by **02-deploy-btp** (and by a re-scaffold if the provider changes).
> **Toolkit command:** none — this recipe runs the preflight script.

**Fast path (commercial regions):** if the subaccount sits in a regular commercial hub (`eu10`, `eu11`, `us10`, `us20`, `ap10`, …), the answer is `--llm-provider aicore` — you can skip this recipe and let [02-deploy-btp](../../02-deploy-btp/)'s step 0 confirm. Run the full preflight below for sovereign/regulated targets (China Landing, NS2, KSA, EU Access) or whenever you're unsure.

Use this before every customer pilot in a sovereign or unfamiliar region.

## Goal

Decide whether the customer can use SAP AI Core / GenAI Hub or must fall back to an OpenAI-compatible sovereign/local model gateway. Some regions support both with a stated preference — EU Access can stay on AI Core but any cross-region model routing needs customer approval; KSA is split into a regulated tier with AI Core and a non-regulated tier without. The tier table in step 4 spells out the branch you take.

## Inputs

- target BTP region — anything the script can resolve: BTP CLI landscape code (`eu10`, `cn40`, `sa30`), short alias (`europe`, `china`, `ksa`), city substring (`frankfurt`, `dammam`), or verbatim Discovery Center label (`Europe (Frankfurt)`, `China (Shanghai)`)
- customer subaccount ID

## Decisions you'll make from the output

- runtime: Cloud Foundry or Kyma
- persistence: memory, HANA task store, vector, KG
- model provider: AI Core / GenAI Hub vs OpenAI-compatible sovereign gateway

## Steps

### 1. Check what SAP offers in the region

[`scripts/region-preflight/region-preflight.sh`](../../../scripts/region-preflight/region-preflight.sh) queries the public Discovery Center catalog for the services this cookbook cares about (CF, Kyma, AI Core, AI Launchpad, HANA Cloud, Destination, Connectivity, Cloud Logging, XSUAA, Audit Log) and prints an `available` / `not listed` table per matching data center.

The script resolves loose input to one or more canonical Discovery Center region labels:

```bash
bash scripts/region-preflight/region-preflight.sh <region>

# Landscape code (BTP CLI form) → single data center:
bash scripts/region-preflight/region-preflight.sh eu10        # Europe (Frankfurt)
bash scripts/region-preflight/region-preflight.sh cn40        # China (Shanghai)
bash scripts/region-preflight/region-preflight.sh sa30        # KSA (Dammam – KSA Regulated Customers)
bash scripts/region-preflight/region-preflight.sh sa31        # KSA (Dammam – KSA Non-Regulated Customers)

# Short alias → all matching data centers (fans out):
bash scripts/region-preflight/region-preflight.sh europe      # all Europe (*) DCs
bash scripts/region-preflight/region-preflight.sh china       # both China DCs
bash scripts/region-preflight/region-preflight.sh ksa         # both KSA DCs
bash scripts/region-preflight/region-preflight.sh us          # all US* DCs

# City substring → matching DCs:
bash scripts/region-preflight/region-preflight.sh frankfurt   # Frankfurt + EU Access variants

# Verbatim Discovery Center label (works too):
bash scripts/region-preflight/region-preflight.sh "Europe (Frankfurt)"
bash scripts/region-preflight/region-preflight.sh "China (Shanghai)"
```

Requires `curl` and `jq`. No login needed — the catalog endpoint is public. When the input doesn't match anything, the script prints the live list of valid labels so you can pick one.

> 💡 Scoping before you know the target region? [`scripts/region-preflight/regions-overview.md`](../../../scripts/region-preflight/regions-overview.md) is the panoramic version — every cookbook service × every multi-cloud data center in one page.

> ℹ A plugin command (`/sap-a2a-agent-toolkit:region-preflight`) is on the roadmap but not yet shipped. Use the script.

### 2. Check what the customer's subaccount is actually entitled to

Discovery Center says "could this work here?" — your subaccount answers "does it work for me?" Run these against the customer's tenant:

> Not logged in yet? `btp login --url https://cli.btp.cloud.sap` then `btp target --subaccount <SUBACCOUNT_ID>` — the full login walkthrough (including sovereign API URLs) is in [02-deploy-btp step 0.3](../../02-deploy-btp/README.md#03-log-in).

```bash
# Full entitlement dump (works without cf login):
btp --format json list accounts/entitlement --subaccount <SUBACCOUNT_ID>

# Quick filter for the services this cookbook cares about — jq pulls just
# service+plan+quota so you can scan in one screen:
btp --format json list accounts/entitlement --subaccount <SUBACCOUNT_ID> \
  | jq '.quotas[] | select(.service | test("^(aicore|hana|hana-cloud|cloudfoundry|kymaruntime|destination|connectivity|xsuaa|auditlog-|cloud-logging|application-logs)"; "i")) | {service, plan, quota}'

# Then, once cf-logged-in to the target org+space, confirm the plans are
# actually offered in that space's marketplace. CF CLI v7+ uses -e, NOT -s:
cf marketplace -e aicore || true
cf marketplace -e hana-cloud || true
cf services
```

> ℹ The `-s` flag was removed in CF CLI v7. If you see `unknown flag 's'`, you're on a current CLI — use `-e` (service offering).

**What "entitled" means here.** A `quota` entry in `btp list accounts/entitlement` proves the *global account* gave this subaccount permission to provision the service. It does **not** prove the service is GA in the region (that's Discovery Center, step 1) and it does **not** prove an instance has been created (that's `cf services`). All three signals must line up before the deploy will actually succeed.

### 3. Find the subaccount's actual region

The entitlement output tells you *what* the subaccount can provision, not *where* it lives. Get the region:

```bash
btp --format json get accounts/subaccount <SUBACCOUNT_ID> | jq '{displayName, region, betaEnabled, state}'
```

Cross-reference the `region` field (e.g. `eu10`, `cn40`, `sa30`) with what step 1 already told you about that landscape. If the subaccount's region doesn't match any region where AI Core is GA — but the entitlement output still showed an `aicore` quota — the entitlement is non-honourable in this subaccount and you must fall back to `--llm-provider openai-compatible`.

### 4. Pick the LLM path

Cross-check the script output (step 1) and the subaccount region (step 3) against this tier table:

| Region | Default LLM path |
|--------|------------------|
| Regular commercial hubs (`eu10`, `eu11`, `us10`, `us20`, `us21`, `ap10`, `ap11`, `jp10`, …) | `--llm-provider aicore` |
| EU Access (operational-restriction tier on `eu10` / `eu11`) | `--llm-provider aicore` — but any cross-region model routing needs customer approval. Fallback: `openai-compatible` against a customer-approved EU gateway. |
| China Landing (`cn40`, `cn41`) | `--llm-provider openai-compatible` — AI Core not in region. |
| NS2 (US Federal / DoD / IC) | `--llm-provider openai-compatible` — AI Core not listed. |
| KSA regulated (`sa30`) | `--llm-provider aicore` with `openai-compatible` fallback (entitlement-gated per tenant — the preflight script tells you which). |
| KSA non-regulated (`sa31`) | `--llm-provider openai-compatible` — AI Core not listed. |

If the region isn't in this table, trust the preflight script (step 1) and the source-backed reference in [`skills/sap-sovereign-regions/references/btp-regional-availability.md`](../../../skills/sap-sovereign-regions/references/btp-regional-availability.md) — if `aicore` shows `available` in Discovery Center **and** the entitlement dump (step 2) has an `aicore` quota **and** the subaccount region (step 3) matches, use `--llm-provider aicore`. Otherwise fall back to `--llm-provider openai-compatible` and wire a customer-approved gateway ([`../sovereign-model-gateway/`](../sovereign-model-gateway/)).
