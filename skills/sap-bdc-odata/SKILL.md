---
name: sap-bdc-odata
description: Use the checked-in Datasphere OAuth/OData reader for bounded read access and controlled fixture tests.
---

# Datasphere OAuth/OData reader

Use [samples/datasphere-reader](../../samples/datasphere-reader/) for the public adapter and runnable example.
Read its configuration contract before integrating a selected view.
Do not request or print OAuth secret values.
Ask the owner to load approved credentials into the runtime secret store.
Missing tenant access does not block the controlled fixture tests.

## Access requirements

The owner supplies the exact tenant service URL and OAuth token endpoint.
The owner identifies the space, view, and endpoint shape.
The technical user needs read access to the deployed view.
The example requires Region and Revenue fields.
Do not guess an authentication host from a region name.

Shape A has one space-level service and reads the view entity set directly.
Shape B has a view-level service with one discovered inner entity set.
The adapter requires explicit A or B selection.
It rejects unsupported or ambiguous service listings.

## Adapter boundary

The reader accepts an explicit field projection, bounded string equality filters, and a row limit.
It escapes string literals and rejects invalid field identifiers.
It follows only continuation links within the configured collection.
It refreshes tokens before expiry and retries HTTP 401 once.
Errors exclude endpoints, secrets, and backend response bodies.
Every caller uses the async context manager to close the HTTP client.

The MCP tool exposes only read_region_revenue(region, limit).
Models receive bounded business rows and a source label.
They do not receive raw query access or credentials.

## Acceptance

Run the sample fixture tests from a clean clone.
Record real acceptance only after approved Datasphere access returns expected source records.
Require a deployed A2A reply for an agent integration.
The adapter tests do not replace that deployment proof.

See [SAP Datasphere documentation](https://help.sap.com/docs/SAP_DATASPHERE/) for tenant access and consumption services.
See [OData documentation](https://www.odata.org/documentation/) for service documents and continuation links.


## Optional A2A integration

Use the sample's [revenue A2A guide](../../samples/datasphere-reader/A2A.md) for one deterministic consumer.
The local fixture proof uses synthetic OAuth/OData only and creates no tenant resources.
Keep real Datasphere verification, runtime selection, deployment and deployed cleanup as separate gates.
