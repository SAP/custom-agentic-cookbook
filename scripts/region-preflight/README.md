# region-preflight

Check what SAP BTP services are listed in Discovery Center for a given region — the first step of every customer pilot.

## What it does

Queries the public Discovery Center catalog for the services this cookbook cares about (Cloud Foundry, Kyma, AI Core, AI Launchpad, HANA Cloud, Destination, Connectivity, Cloud Logging, XSUAA, Audit Log) and prints an `available` / `not listed` table per matching data center.

Requires `curl` and `jq`. No BTP login needed — the catalog endpoint is public.

## Usage

```bash
bash scripts/region-preflight/region-preflight.sh <region>
```

Accepts loose input, resolved to one or more canonical Discovery Center labels:

```bash
# Landscape code (BTP CLI form) → single data center:
bash scripts/region-preflight/region-preflight.sh eu10        # Europe (Frankfurt)
bash scripts/region-preflight/region-preflight.sh cn40        # China (Shanghai)
bash scripts/region-preflight/region-preflight.sh sa30        # KSA (Dammam – Regulated)
bash scripts/region-preflight/region-preflight.sh sa31        # KSA (Dammam – Non-Regulated)

# Short alias → all matching data centers:
bash scripts/region-preflight/region-preflight.sh europe
bash scripts/region-preflight/region-preflight.sh china
bash scripts/region-preflight/region-preflight.sh ksa
bash scripts/region-preflight/region-preflight.sh us

# City substring or verbatim Discovery Center label:
bash scripts/region-preflight/region-preflight.sh frankfurt
bash scripts/region-preflight/region-preflight.sh "China (Shanghai)"
```

Run with no args to see the built-in usage help.

## Snapshot: all regions at a glance

For the panoramic view — every cookbook service × every multi-cloud data center in one table — see [`regions-overview.md`](regions-overview.md). It's a rendered snapshot of the same catalog this script queries, useful when scoping a customer engagement before you know the target region. For source-backed sovereign and Cloud SDK service caveats, cross-check [`../../skills/sap-sovereign-regions/references/btp-regional-availability.md`](../../skills/sap-sovereign-regions/references/btp-regional-availability.md). Regenerate the overview with `bash scripts/region-preflight/gen-overview.sh`.

## Where it fits

This script is step 1 of [`recipes/optional/region-preflight/`](../../recipes/optional/region-preflight/). That recipe covers the whole flow: what to run, how to read the output, how to combine it with `btp list accounts/entitlement` (step 2), and how to pick the LLM provider path (step 4). Use the recipe for the full workflow; use this script directly when you just need the availability table.
