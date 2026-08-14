# BTP Regional Availability for Agent and KG Cookbooks

Last checked: core Discovery Center rows rechecked 2026-07-07; supplemental SDK/service rows checked 2026-07-03.

This reference helps decide whether an A2A/Joule agent cookbook should use SAP AI Core / GenAI Hub or a local OpenAI-compatible model gateway in a target region.

Sources:
- SAP Discovery Center Service Catalog: <https://discovery-center.cloud.sap/serviceCatalog>
- SAP Discovery Center REST service catalog: <https://discovery-center.cloud.sap/servicecatalog/api/v1/services>
- SAP Discovery Center OData service catalog: <https://discovery-center.cloud.sap/servicecatalog/Services?$format=json&$top=1>
- SAP Discovery Center OData metadata: <https://discovery-center.cloud.sap/servicecatalog/$metadata>
- SAP BTP Cloud Foundry region docs: <https://help.sap.com/docs/btp/sap-business-technology-platform/regions-and-api-endpoints-available-for-cloud-foundry-environment>
- SAP Data Privacy Integration Help Portal: <https://help.sap.com/docs/DATA_PRIVACY_INTEGRATION/>
- SAP Document Management Service Help Portal: <https://help.sap.com/docs/DOCUMENT_MANAGEMENT/>
- All-in on AI Decision: Agentic Memory Service: <https://github.tools.sap/CPA/landing-page-content/blob/main/40_Results/all-in-on-ai-decisions/agentic-memory-service.md>
- Agent Memory Service - HANA Cloud Provisioning & Operational Responsibilities, attached Word document from the review thread.
- SAP BTP Everywhere — Region Roadmap Planning: <https://url.sap/btp-dcroadmap> (forward-looking; pair with Discovery Center for current state)
- SAP Cloud SDK for Python README and module guides: <https://github.com/SAP/cloud-sdk-python/tree/main>

Important caveats:
- Discovery Center shows public service and plan visibility. A customer subaccount can still be missing quota, entitlement, commercial model, allowlist, or tenant-level feature access.
- SAP HANA Cloud appears at service level. HANA feature-level checks for vector search, embedding, and knowledge graph / triple-store capabilities must be validated on the actual tenant.
- Agent Memory has a Phase 1 bring-your-own-HANA/default-HANA model. HANA Cloud regional availability is therefore valid evidence for the persistence prerequisite, but it does not by itself prove availability of the managed `hana-agent-memory` binding, Agent Memory APIs, or App Foundation onboarding path.
- Joule capability support depends on the Joule tenant schema and regional product availability. Code-based agents require DTA schema `3.28.0+`.
- SAP Cloud SDK for Python includes modules whose backing services are SAP Application Foundation or internal/backing SaaS services not visible as standalone Discovery Center rows. Those modules are called out below as validation items rather than represented as all-`-` rows in the region matrix.
- SAP Cloud SDK for Python binding names do not always match Discovery Center service names. Example: the data anonymization module uses a `data-anonymization` binding, while the public catalog candidate is `SAP Data Privacy Integration`; keep this as pending evaluation until the service key/binding shape is confirmed in a target tenant.
- The print service appears as `SAP Print service` in the OData service catalog and as `Print Service` in the service-data CSV. The matrix uses the service-data CSV row because it carries the target-region plan details.

## Target Region Matrix

Legend:
- `Y` means the service appears in the SAP Discovery Center service catalog for that region.
- `-` means it did not appear for that region in the relevant check. Core rows were rechecked against the REST catalog on 2026-07-07; supplemental SDK/service rows retain the 2026-07-03 source check until the next full refresh.
- `plan` notes are from the Discovery Center estimate/details endpoint where available.

| Service | China Shanghai | China North 3 | KSA regulated | KSA non-regulated | NS2 Sterling | NS2 Colorado |
|---|---:|---:|---:|---:|---:|---:|
| Cloud Foundry Runtime | Y | Y | Y | Y | Y | Y |
| Kyma runtime | Y | Y | Y | Y | Y | Y |
| SAP AI Core | - | - | Y, `standard`/`extended` | - | - | - |
| SAP AI Launchpad | - | - | Y, `standard` | - | - | - |
| SAP HANA Cloud | Y, `hana`/`hana-free` | Y, `hana`/`hana-free` | Y, `hana` | Y, `hana` | Y, `hana` | Y, `hana` |
| Destination Service | Y | Y | Y | Y | Y | Y |
| Connectivity Service | Y | Y | Y | Y | Y | Y |
| Authorization and Trust Management (XSUAA) | Y | Y | Y | Y | Y | Y |
| Cloud Identity Services (IAS) | - | - | Y, `Default Tenant`/`Additional Tenant` | Y, `Default Tenant`/`Additional Tenant` | Y, `Default Tenant`/`Additional Tenant` | Y, `Default Tenant`/`Additional Tenant` |
| Audit Log Service | Y | Y | Y | Y | Y | Y |
| Cloud Logging | - | - | Y | Y | Y | Y |
| Document Management Service, Integration Option | - | Y, `standard` | Y, `free`/`standard` | Y, `free`/`standard` | Y, `free`/`standard` | Y, `free`/`standard` |
| Document Management Service, Application Option | Y, `standard` | Y, `standard` | Y, `standard` | Y, `standard` | Y, `standard` | Y, `standard` |
| Object Store | Y, `standard` | Y, `standard` | Y, `standard` | Y, `standard` | Y, `standard` | Y, `standard` |
| Print Service | Y, `Sender` | Y, `Sender` | - | - | - | - |

Region labels used by Discovery Center:
- China Shanghai: `China (Shanghai)` on Alibaba
- China North 3: `China (North 3)` on Microsoft Azure
- KSA regulated: `KSA (Dammam – KSA Regulated Customers)` on Google Cloud
- KSA non-regulated: `KSA (Dammam – KSA Non-Regulated Customers)` on Google Cloud
- NS2 Sterling: `US (Sterling)` on SAP
- NS2 Colorado: `US West (Colorado)` on SAP

## SAP Cloud SDK Python Mapping

The SAP Cloud SDK for Python README lists key features that are broader than the original agent cookbook runtime matrix. The table below maps those features to the BTP services or external/backing services that must be available before using that SDK module in a target region.

| Cloud SDK Python key feature | Backing service or dependency to check | Matrix coverage |
|---|---|---|
| Agent Decorators | No standalone BTP service. Code-level configuration for exposing agent functions. Requires only the chosen app runtime and any services used by the decorated function. | Covered indirectly by Cloud Foundry/Kyma and recipe-specific rows. |
| Agent Memory | Two operating modes are documented. **BYOH/default-HANA mode:** the agent memory service stores memory in a customer- or deployment-provided SAP HANA Cloud tenant. **Managed service mode:** App Foundation/BTP Fabric provides a `hana-agent-memory` binding, mounted at `/etc/secrets/appfnd/hana-agent-memory/{instance}`, with `application_url` and XSUAA-style `uaa` credentials for the Agent Memory APIs. | The HANA Cloud row can be used for the BYOH/default-HANA persistence prerequisite. It does **not** prove managed `hana-agent-memory` availability, because that also requires the Agent Memory API/service layer, binding, and App Foundation onboarding path. No standalone Discovery Center row was found for that managed service. |
| AI Core Integration | SAP AI Core service binding. SAP AI Launchpad remains useful for operations/UI but is not required by the Python client at runtime. | SAP AI Core and SAP AI Launchpad rows already existed. |
| Audit Log Service | SAP Audit Log Service. | Already covered. |
| Audit Log NG | SAP Audit Log Service v3/NG endpoint via OTLP/gRPC. | Covered by Audit Log Service row; verify the v3/NG endpoint on the actual tenant. |
| Destination Service | SAP Destination Service. | Already covered. |
| Document Management Service | SAP Document Management service, integration option for the runtime service binding; application option may also be needed for UI/admin scenarios. | Added both DMS integration and application option rows. |
| IAS (Identity and Access Service) | SAP Cloud Identity Services tenant and IAS credentials. | Added Cloud Identity Services row. |
| ObjectStore Service | Object Store on SAP BTP / Object Store service binding. | Added Object Store row. |
| Secret Resolver | No standalone BTP service. Reads mounted service bindings or `CLOUD_SDK_CFG_*` environment variables for other services. | Covered indirectly by each service binding row. |
| Telemetry & Observability | SDK emits OpenTelemetry; SAP Cloud Logging is the BTP-managed target in this matrix, but customers may use another approved OTLP collector. | Cloud Logging row already existed. |
| Print Service | Print Service service binding. | Added Print Service row. |

Additional SDK module observed in the repository: `adms` integrates with SAP Advanced Document Management Service / ADM OData APIs as an IAS-based BTP Shared SaaS application. In the public catalog evidence, this is best tracked through SAP Document Management Service rather than a separate `ADMS` service row. Keep the DMS integration/application rows in the matrix, and still validate the ADMS-specific provisioning path for recipes that call `sap_cloud_sdk.adms`.

### Pending Evaluation

These SDK-backed capabilities have plausible service/product mappings, but they should not be treated as regionally available or unavailable until the mapping and onboarding path are confirmed.

| Capability | SDK evidence | Evaluation needed |
|---|---|---|
| Data Anonymization Service | SDK binding/config name is `data-anonymization`; the client calls `/anonymization/api/v1.0/...` endpoints and can resolve client certificates through Destination Service. `SAP Data Privacy Integration` is the public catalog candidate. | Confirm whether `SAP Data Privacy Integration` service keys expose the `data-anonymization` binding shape expected by the SDK, then decide whether to add a regional matrix row. |

### Out of Scope

These capabilities are intentionally excluded from the regional availability decision for this document.

| Capability | Reason |
|---|---|
| Unified Metadata Service (UMS) for Extensibility | Extensibility resolves managed `sap-managed-runtime-ums-*` destinations and calls UMS GraphQL, but this capability is not part of the regional availability decision for these recipes. Do not use this matrix to decide UMS availability. |
| SAP Agent Gateway | Not expected to be available to these teams/customers, and no standalone Discovery Center row was found. Do not use this matrix to decide Agent Gateway availability. |

### SDK Features Needing Product Validation

These SDK-backed capabilities were present in the Cloud SDK Python repository but did not appear as normal Discovery Center service rows in the supplied catalog data. Do not read that as confirmed regional unavailability; validate with the service owner or SAP Application Foundation before deciding whether a recipe can use them.

| Capability | SDK evidence | Validation needed |
|---|---|---|
| Agent Memory | The Cloud SDK code expects the managed binding shape: `hana-agent-memory` with `application_url` and `uaa` credentials. The Agentic Memory decision and operational model also define Phase 1 BYOH/default-HANA modes where HANA Cloud is supplied separately. | Decide which mode the recipe uses. For BYOH/default-HANA, check SAP HANA Cloud regional availability, entitlement, tenant feature readiness, and the Agent Memory configuration that points to that tenant. For managed `hana-agent-memory`, confirm the service binding, API availability, commercial availability, and App Foundation onboarding path per target region. |
| Advanced Document Management Service (ADMS) | `adms` module uses IAS-based ADM service credentials and ADM OData APIs. | Treat regional catalog coverage as DMS coverage, then confirm the BTP Shared SaaS / ADMS-specific provisioning path and service-binding shape. |

## Practical Guidance

### China Landing

Build the agent runtime on Cloud Foundry where available. Use HANA Cloud for persistence, task state, vector storage, and KG data only after tenant-level feature validation.

Main limitation: SAP AI Core and SAP AI Launchpad were not listed for China Shanghai or China North 3. Cloud Logging and Cloud Identity Services were also not listed. Kyma was listed for both China targets in the 2026-07-07 REST catalog check. SAP Cloud SDK's DMS integration option was listed for China North 3 but not China Shanghai in the supplemental 2026-07-03 source check; Print Service was listed for both China targets with `Sender` plan. Data Anonymization is pending evaluation and should not drive the China decision yet. UMS is out of scope for this matrix.

Recommended scaffold:

```bash
/sap-a2a-agent-toolkit:create-agent <agent-name> \
  --framework cap \
  --taskstore hana \
  --landscape <china-landscape> \
  --llm-provider openai-compatible
```

Set `OPENAI_BASE_URL` to a customer-approved model gateway reachable from the BTP runtime. For local development that can be `http://localhost:11434/v1`, but deployed CF/Kyma apps need a network-reachable endpoint.

### NS2 / SAP Sovereign Regions

Cloud Foundry, Kyma, HANA Cloud, Destination, XSUAA, Cloud Identity Services, Audit Log, Cloud Logging, DMS integration/application options, and Object Store were listed for `US (Sterling)` and `US West (Colorado)`.

Main limitation: SAP AI Core, SAP AI Launchpad, and Print Service were not listed. Treat GenAI Hub as unavailable unless the customer subaccount proves otherwise. Agent Memory in BYOH/default-HANA mode can use the listed HANA Cloud prerequisite, but managed `hana-agent-memory` still needs product/App Foundation validation. ADMS needs separate product validation; Data Anonymization is pending evaluation; UMS and Agent Gateway are out of scope for this matrix.

Recommended scaffold:

```bash
/sap-a2a-agent-toolkit:create-agent <agent-name> \
  --framework cap \
  --taskstore hana \
  --landscape <ns2-landscape> \
  --llm-provider openai-compatible
```

### KSA

KSA has two different regional labels. The regulated region listed AI Core and AI Launchpad. The non-regulated region did not.

Both KSA regions listed Cloud Identity Services, DMS integration/application options, Object Store, Cloud Foundry, Kyma, HANA Cloud, Destination, XSUAA, Audit Log, and Cloud Logging. Print Service was not listed for either KSA target region in the service-data CSV. Agent Memory BYOH/default-HANA persistence is covered by the HANA Cloud prerequisite, but managed `hana-agent-memory` onboarding remains a separate check. Data Anonymization is pending evaluation and should not drive the KSA decision yet. UMS is out of scope for this matrix.

Recommended rule:
- For `KSA (Dammam – KSA Regulated Customers)`, `--llm-provider aicore` is viable if the customer subaccount has entitlement and quota.
- For `KSA (Dammam – KSA Non-Regulated Customers)`, start with `--llm-provider openai-compatible`.

### Regular BTP Regions

Regular commercial regions such as Frankfurt, US East, Singapore, Japan, and Australia generally have the full agent path: Cloud Foundry/Kyma, AI Core, AI Launchpad, HANA Cloud, Destination, XSUAA, Audit Log, and Cloud Logging. Still run the preflight because assigned entitlements are global-account specific. For SAP Cloud SDK Python recipes, also check Cloud Identity Services, DMS integration option, Object Store, Print Service, and any SAP Application Foundation backend service used by the selected module. Keep Data Anonymization behind the pending-evaluation gate until its product mapping is confirmed. UMS is out of scope for this matrix.

## SAP Cloud SDK Python Preflight Additions

For recipes using SAP Cloud SDK Python modules, extend the regional preflight beyond the original agent runtime rows:

```bash
cf marketplace -e identity || true
cf marketplace -e sdm || true
cf marketplace -e objectstore || true
cf marketplace -e print || true
cf marketplace -e hana-agent-memory || true
```

For Agent Memory, first decide which mode the recipe uses:
- **BYOH/default-HANA:** do not expect a `hana-agent-memory` marketplace row. Verify HANA Cloud entitlement, the target HANA tenant, tenant feature readiness, and the Agent Memory service/API configuration that points to that tenant.
- **Managed `hana-agent-memory`:** use `cf marketplace -e hana-agent-memory` or equivalent tenant checks only as evidence for the managed binding/service layer. This is separate from HANA Cloud regional availability.

Also verify mounted service bindings or environment fallbacks expected by the SDK:

```bash
find "${SERVICE_BINDING_ROOT:-/etc/secrets/appfnd}" -maxdepth 3 -type f | sort
env | grep '^CLOUD_SDK_CFG_' | sort
```

For pending-evaluation capabilities such as Data Anonymization, first confirm the product mapping and provisioning path with the service owner before adding them as required regional preflight checks. UMS and Agent Gateway are out of scope for this matrix.

## HANA Vector and KG Checks

Discovery Center confirms the HANA Cloud service is available in the target regions above, but it does not prove that every HANA Cloud tenant has every advanced feature enabled.

Before committing to a KG/vector cookbook in a customer region:

1. Confirm `hana / hdi-shared` entitlement if CAP task persistence or HDI deployer is used.
2. Confirm HANA Cloud instance class, version, and feature flags in HANA Cloud Central.
3. Run a smoke test for vector columns/functions on the target tenant.
4. Run a smoke test for the intended KG/triple-store workflow on the target tenant.
5. Capture the result in the customer issue and send product gaps or customer feedback to Aha.

Example vector smoke test idea:

```sql
CREATE LOCAL TEMPORARY TABLE #VECTOR_CHECK (
  ID INTEGER,
  EMBEDDING REAL_VECTOR(3)
);

INSERT INTO #VECTOR_CHECK VALUES (1, TO_REAL_VECTOR('[0.1,0.2,0.3]'));

SELECT ID, EMBEDDING FROM #VECTOR_CHECK;
```

If this fails on syntax or type availability, do not ship the vector cookbook for that tenant until HANA feature availability is resolved.

## Preflight Commands

Start with the repository preflight script:

```bash
bash scripts/region-preflight/region-preflight.sh "US (Sterling)"
```

Then run tenant-specific checks against the customer subaccount:

```bash
# Global/subaccount regions visible to this account
btp --format json list accounts/available-region

# Assigned entitlements in the customer subaccount
btp --format json list accounts/entitlement --subaccount <SUBACCOUNT_ID>

# CF marketplace from the targeted org/space
cf marketplace -e aicore || true
cf marketplace -e destination || true
cf marketplace -e hana-cloud || true
cf marketplace -e identity || true
cf marketplace -e sdm || true
cf marketplace -e objectstore || true
cf marketplace -e print || true
cf services
```

Discovery Center query pattern:

```bash
curl -sG 'https://discovery-center.cloud.sap/servicecatalog/Services' \
  --data-urlencode '$format=json' \
  --data-urlencode '$select=Id,Name,Provider,RegionDataCenter' \
  --data-urlencode "\$filter=substringof('SAP AI Core',Name)"
```

## Cookbook Design Rule

Keep the cookbook layered:

1. Agent transport: A2A endpoint on Cloud Foundry or Kyma.
2. Joule integration: Destination plus capability YAML.
3. Model access: `aicore` when SAP AI Core is regionally available and entitled, otherwise `openai-compatible`.
4. State/KG/vector persistence: HANA Cloud when available and feature-validated.
5. SAP Cloud SDK service modules: provision only what the recipe imports, for example DMS integration option, Object Store, Cloud Identity Services, Print Service, or Agent Memory. For Agent Memory, distinguish BYOH/default-HANA mode from managed `hana-agent-memory` binding mode. Keep Data Anonymization pending evaluation; keep UMS/extensibility and Agent Gateway out of scope.
6. Observability: Cloud Logging when available, otherwise app logs, log drains, or the customer's approved logging stack.

This lets regional teams build customer value immediately and leaves a cleaner path to port the implementation back to BAIP when the target region and product maturity catch up.
