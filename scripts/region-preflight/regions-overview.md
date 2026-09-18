# BTP regions — availability overview

Snapshot of Discovery Center availability for the ten services this cookbook cares about, across every BTP data center that hosts the multi-cloud Cloud Foundry / Kyma runtime.

- **Source:** `https://discovery-center.cloud.sap/servicecatalog/api/v1/services`
- **Fetched:** 2026-09-16
- **Regenerate:** `bash scripts/region-preflight/region-preflight.sh <region>` gives the live per-region view; this doc is the panorama. All cells were rendered directly from the live catalog (see [How to regenerate this doc](#how-to-regenerate-this-doc)) — no hand transcription.

> ⚠️ This is a **point-in-time snapshot** of a public catalog. Discovery Center is authoritative but changes weekly — always re-run the preflight script before scoping a pilot. Cell entries reflect *listed* availability; some services (e.g. AI Core) are further gated by entitlement, contract type (regulated vs. non-regulated), and BAIP / Business Data Cloud licensing. Verify with `btp list accounts/entitlement` after this check.

For source-backed sovereign-region caveats beyond the ten generated service rows here — including SAP Cloud SDK Python mappings, Agent Memory mode distinctions, Document Management, Object Store, Print Service, and pending Data Anonymization evaluation — also check [`../../skills/sap-sovereign-regions/references/btp-regional-availability.md`](../../skills/sap-sovereign-regions/references/btp-regional-availability.md).

## Legend

- ✅ — service appears in Discovery Center's `regionDataCenter` field for that data center.
- — — not listed for that data center in Discovery Center today.

Not listed ≠ never available. Sovereign / regulated regions frequently gain services on a rolling basis, and a service may be technically deployable via a landscape Discovery Center doesn't index (e.g. NS2, SAP-run sovereign clouds outside the public catalog). Treat this table as a starting point, not a contract.

The tables cover the **30 multi-cloud data centers** where at least CF Runtime is listed. Neo-only landscapes (Frankfurt Neo, Tokyo Neo, KSA Riyadh, etc.) are excluded — the cookbook targets Cloud Foundry / Kyma, not Neo.

## Landscape codes → Discovery Center labels

Landscape codes identify a specific Cloud Foundry landscape (and its
hyperscaler); Discovery Center speaks human region labels. This is the mapping
the preflight script uses to turn a code into the exact label it queries.
Several codes share one label when multiple hyperscalers host the same physical
region — e.g. `us10` (AWS) and `us21` (Azure) are both "US East (VA)".

Code ↔ region comes from SAP Help "Regions and API Endpoints Available for the
Cloud Foundry Environment" (the code is the CF API-endpoint subdomain, so each
row is self-identifying); each label is the verbatim Discovery Center key.

| Landscape | Discovery Center label | IaaS | Notes |
|---|---|---|---|
| `eu10` | Europe (Frankfurt) | AWS | Most commercial services GA here first |
| `eu11` | Europe (Frankfurt) EU Access | AWS | EU Access — restricted operator access |
| `eu13` | Europe (Milan) | AWS | |
| `eu20` | Europe (Netherlands) | Azure | |
| `eu30` | Europe (Frankfurt) SAP EU Access | SAP | SAP-operated, EU Access sovereignty tier |
| `us01` | US (Sterling) | SAP | SAP-run US sovereign |
| `us02` | US West (Colorado) | SAP | SAP-run US sovereign |
| `us10` | US East (VA) | AWS | |
| `us11` | US West (Oregon) | AWS | |
| `us20` | US West (WA) | Azure | |
| `us21` | US East (VA) | Azure | Same DC as `us10` |
| `us30` | US Central (IA) | GCP | |
| `ap10` | Australia (Sydney) | AWS | |
| `ap11` | Singapore | AWS | |
| `ap12` | South Korea (Seoul) | AWS | |
| `ap20` | Australia (Sydney) | Azure | Same DC as `ap10` |
| `ap21` | Singapore | Azure | Same DC as `ap11` |
| `ap30` | Australia Southeast (Sydney) | GCP | |
| `jp10` | Japan (Tokyo) | AWS | |
| `jp20` | Japan (Tokyo) | Azure | Same DC as `jp10` |
| `jp30` | Japan (Osaka) | GCP | |
| `ca10` | Canada (Montreal) | AWS | |
| `ca20` | Canada (Toronto) | Azure | |
| `br10` | Brazil (São Paulo) | AWS | |
| `br20` | Brazil South | Azure | |
| `in30` | India (Mumbai) | GCP | |
| `cn20` | China (North 3) | Azure | China Landing, Azure-hosted |
| `cn40` | China (Shanghai) | Alibaba | China Landing, Alibaba-hosted |
| `sa30` | KSA (Dammam – KSA Regulated Customers) | GCP | KSA regulated tier |
| `sa31` | KSA (Dammam – KSA Non-Regulated Customers) | GCP | |
| `ch20` | Switzerland (EU Access) | Azure | EU Access |
| `il30` | Israel (Tel Aviv) | GCP | |
| `ae01` | UAE (Dubai) | SAP | SAP-run UAE sovereign |

Visible in Discovery Center but with no stable landscape shortcut in the
preflight map: **Europe (Rot) SAP Cloud Infrastructure EU Access** (SAP). The
`europe` alias picks it up via substring match.

## Service availability by region

Ten cookbook services, thirty data centers. Wide tables — expect horizontal scrolling on narrow screens.

### Europe

| Service | Frankfurt (`eu10`) | Frankfurt EU Access (`eu11`) | Frankfurt SAP EU Access (`eu30`) | Netherlands (`eu20`) | Milan (`eu13`) | Rot SAP EU Access | Switzerland EU Access (`ch20`) |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| SAP BTP, Cloud Foundry Runtime | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| SAP BTP, Kyma runtime | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| SAP AI Core | ✅ | ✅ | ✅ | ✅ | — | ✅ | — |
| SAP AI Launchpad | ✅ | ✅ | ✅ | ✅ | — | ✅ | — |
| SAP HANA Cloud | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| SAP Destination Service | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| SAP Connectivity Service | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| SAP Cloud Logging | ✅ | ✅ | ✅ | ✅ | ✅ | — | ✅ |
| SAP Authorization and Trust Management | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| SAP Audit Log Service | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

### Americas

| Service | US East VA (`us10`/`us21`) | US Central IA (`us30`) | US West WA (`us20`) | US West Oregon (`us11`) | US West Colorado (`us02`) | US Sterling (`us01`) | Canada Montreal (`ca10`) | Canada Toronto (`ca20`) | Brazil São Paulo (`br10`) | Brazil South (`br20`) |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| SAP BTP, Cloud Foundry Runtime | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| SAP BTP, Kyma runtime | ✅ | ✅ | ✅ | — | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| SAP AI Core | ✅ | ✅ | — | — | — | — | ✅ | — | ✅ | — |
| SAP AI Launchpad | ✅ | ✅ | — | — | — | — | — | — | ✅ | — |
| SAP HANA Cloud | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| SAP Destination Service | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| SAP Connectivity Service | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| SAP Cloud Logging | ✅ | ✅ | ✅ | — | ✅ | ✅ | ✅ | — | ✅ | ✅ |
| SAP Authorization and Trust Management | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| SAP Audit Log Service | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

### Asia-Pacific

| Service | Singapore (`ap11`/`ap21`) | Japan Tokyo (`jp10`/`jp20`) | Japan Osaka (`jp30`) | South Korea Seoul (`ap12`) | Australia Sydney (`ap10`/`ap20`) | Australia SE Sydney (`ap30`) | India Mumbai (`in30`) |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| SAP BTP, Cloud Foundry Runtime | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| SAP BTP, Kyma runtime | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| SAP AI Core | ✅ | ✅ | — | ✅ | ✅ | ✅ | ✅ |
| SAP AI Launchpad | ✅ | ✅ | — | — | ✅ | ✅ | ✅ |
| SAP HANA Cloud | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| SAP Destination Service | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| SAP Connectivity Service | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| SAP Cloud Logging | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| SAP Authorization and Trust Management | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| SAP Audit Log Service | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

### Sovereign / regulated

The columns that matter most for this cookbook — where the "why" of the sovereign track lives.

| Service | UAE Dubai (`ae01`) | Israel Tel Aviv (`il30`) | KSA Dammam Regulated (`sa30`) | KSA Dammam Non-Reg. (`sa31`) | China Shanghai (`cn40`) | China North 3 (`cn20`) |
|---|:-:|:-:|:-:|:-:|:-:|:-:|
| SAP BTP, Cloud Foundry Runtime | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| SAP BTP, Kyma runtime | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| SAP AI Core | ✅ | — | ✅ | — | — | — |
| SAP AI Launchpad | ✅ | — | ✅ | — | — | — |
| SAP HANA Cloud | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| SAP Destination Service | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| SAP Connectivity Service | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| SAP Cloud Logging | ✅ | — | ✅ | ✅ | — | — |
| SAP Authorization and Trust Management | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| SAP Audit Log Service | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

### What this table says about the sovereign track

- **AI Core / AI Launchpad are the gating constraint.** AI Core is missing from both China DCs, KSA Non-Regulated, Israel, Osaka, Canada (Toronto), every US West variant (WA / Oregon / Colorado), US Sterling, Brazil South, Milan, and Switzerland EU Access; AI Launchpad additionally lags in Canada (Montreal) and South Korea (Seoul), where AI Core is now listed. Every recipe using `--llm-provider aicore` needs a verified `openai-compatible` fallback in those regions. This is the whole reason [`recipes/optional/sovereign-model-gateway/`](../../recipes/optional/sovereign-model-gateway/) exists.
- **KSA is bifurcated.** `sa30` (regulated) has AI Core, `sa31` (non-regulated) does not. Pin the landscape code in every pilot brief — "KSA" alone is ambiguous.
- **China Landing has no AI Core, no AI Launchpad, no Cloud Logging.** Pilots here run on a customer-approved OpenAI-compatible model gateway (Qwen, a local Llama deployment, or similar) and use an alternative observability stack — see the China notes in [`recipes/optional/observe-and-eval/`](../../recipes/optional/observe-and-eval/).
- **Brazil is bifurcated too.** `br10` (São Paulo, AWS/GCP) has AI Core; `br20` (Brazil South, Azure) does not.
- **HANA Cloud, Destination, Connectivity, XSUAA, Audit Log** are listed in every one of the 30 multi-cloud DCs — the persistence + identity + auditing floor for every recipe is intact everywhere.
- **Kyma is available in every region except US West (Oregon)** as of the snapshot. Cloud Foundry is universal.
- **Cloud Logging** has some scattered gaps: Canada (Toronto), US West (Oregon), Israel, both Chinas, and Rot SAP EU Access.

## Coverage summary

Cookbook services across the 30 multi-cloud data centers listed above (Neo-only landscapes excluded):

| Service | Regions | Gaps |
|---|:-:|---|
| SAP BTP, Cloud Foundry Runtime | 30 / 30 | — |
| SAP BTP, Kyma runtime | 29 / 30 | US West (Oregon) |
| SAP AI Core | 17 / 30 | Brazil South; Canada (Toronto); China (North 3); China (Shanghai); Europe (Milan); Israel (Tel Aviv); Japan (Osaka); KSA (Dammam – KSA Non-Regulated Customers); Switzerland (EU Access); US (Sterling); US West (Colorado); US West (Oregon); US West (WA) |
| SAP AI Launchpad | 15 / 30 | Brazil South; Canada (Montreal); Canada (Toronto); China (North 3); China (Shanghai); Europe (Milan); Israel (Tel Aviv); Japan (Osaka); KSA (Dammam – KSA Non-Regulated Customers); South Korea (Seoul); Switzerland (EU Access); US (Sterling); US West (Colorado); US West (Oregon); US West (WA) |
| SAP HANA Cloud | 30 / 30 | — |
| SAP Destination Service | 30 / 30 | — |
| SAP Connectivity Service | 30 / 30 | — |
| SAP Cloud Logging | 24 / 30 | Canada (Toronto); China (North 3); China (Shanghai); Europe (Rot) SAP Cloud Infrastructure EU Access; Israel (Tel Aviv); US West (Oregon) |
| SAP Authorization and Trust Management | 30 / 30 | — |
| SAP Audit Log Service | 30 / 30 | — |

## How to regenerate this doc

Every cell above was rendered from the live catalog by [`gen-overview.sh`](gen-overview.sh) — the same catalog the preflight script consults. To refresh after a Discovery Center change:

```bash
bash scripts/region-preflight/gen-overview.sh
```

That prints all four regional tables plus the coverage summary block to stdout. Paste the output into this file between the region-table and coverage-summary markers, update the **Fetched** date at the top, and commit. Do not hand-edit individual cells — the whole point is that this doc is a rendered view, not a maintained one.

For ad-hoc lookups you don't want to touch this doc for:

```bash
# All Discovery Center labels (deduped) — the columns of the tables above:
curl -sf 'https://discovery-center.cloud.sap/servicecatalog/api/v1/services' \
  | jq -r '.[] | select(.name=="SAP BTP, Cloud Foundry Runtime") | .regionDataCenter' \
  | tr ',' '\n' | sed -E 's/^ +| +$//g' | sort -u

# Region list for one service (a row of the tables above):
curl -sf 'https://discovery-center.cloud.sap/servicecatalog/api/v1/services' \
  | jq -r '.[] | select(.name=="SAP AI Core") | .regionDataCenter'

# Full per-region availability for the cookbook services:
bash scripts/region-preflight/region-preflight.sh <region>
```

When a new region shows up in Discovery Center, extend the `landscape_to_label` case in [`region-preflight.sh`](region-preflight.sh) and add its column to the appropriate section header list in `gen-overview.sh`. Then re-run and commit.
