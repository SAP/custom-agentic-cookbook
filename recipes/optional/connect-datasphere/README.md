---
title: "Read Datasphere through OAuth and OData"
sap-services: [SAP Datasphere]
complexity: recipe
validation-status: "Controlled adapter and local A2A fixtures pass. Real Datasphere and deployed A2A acceptance remain pending."
---

# Read Datasphere data

Use the checked-in [Datasphere reader](../../../samples/datasphere-reader/) to read a configured view.
It contains a runnable adapter, an example, a bounded MCP tool, and repeatable fixture tests.
It requires public Python dependencies and does not use a toolkit-generated project.

Follow the sample guide for local tests and tenant configuration.
Make sure that the technical user can read the deployed view before connecting an agent.
Keep the OAuth credentials in the runtime secret store.
Do not send credential values or endpoint addresses to a model.

The fixture tests cover both service shapes, pagination, filters, token refresh, and failed requests.
Real tenant acceptance requires approved access and comparison with the source records.
A deployed A2A response must contain the expected business answer before the complete agent path passes.

The [adapter skill](../../../skills/sap-bdc-odata/SKILL.md) describes the same interface and access requirements.

The optional [local revenue A2A consumer](../../../samples/datasphere-reader/A2A.md)
provides a bounded deterministic reply and synthetic cross-process failure/recovery/cleanup tests.
It keeps tenant access and deployed acceptance separate.
