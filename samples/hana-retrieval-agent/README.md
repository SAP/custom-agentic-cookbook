# HANA retrieval agent

This separate A2A sample reads documents by vector similarity and primary-contact relationships from an RDF graph.
MCP tools return bounded facts with source references.
The existing production-order sample keeps its interfaces and default mock behavior.

## Local fixture path

From this sample directory, run:

```bash
uv sync --frozen
uv run --frozen pytest -q
```

The tests start real A2A and MCP processes on loopback ports.
They require source references, metadata filters, failed requests, and exact process cleanup.
The fixture backend is synthetic. It does not prove HANA or AI Core access.

For containers, run:

```bash
docker compose up --build
```
Compose uses the supported linux/amd64 HANA image. ARM64 hosts need Docker amd64 emulation.


Send an A2A v1 SendMessage request to http://127.0.0.1:8000/ with one of these messages:

```text
vector:manufacturing:assembly delay
graph:customer-42
```

The vector reply cites https://example.com/source/doc-1.
The graph reply names contact-7 and cites https://example.com/source/customer-42.
After the test, run docker compose down --remove-orphans.

## Approved HANA path

Load HANA_HOST, HANA_PORT, HANA_USER, and HANA_PASSWORD from the approved runtime secret store.
Load the AI Core SDK credentials through its [supported credential configuration](https://github.com/SAP/ai-sdk-python/blob/main/packages/gen/docs/gen_ai_hub/README.md#configuration-for-using-sdk-on-sap-ai-core).
Set RETRIEVAL_BACKEND=hana, HANA_SCHEMA, HANA_GRAPH, and EMBEDDING_DIMENSION explicitly.
The application requires text-embedding-3-small through AI Core.
Make sure that the tenant offers this model before you select it.
Record the actual returned dimension. Do not substitute a different model.
The application rejects vectors that differ from the configured dimension.
Embedding HTTP transport operations use a 20-second timeout with no automatic SDK retries.
Authentication and deployment discovery remain outside this timeout.
The HANA client requires TLS and certificate validation.

Install the optional database and model dependencies:

```bash
uv sync --frozen --extra aicore
```

The runtime database user needs SELECT access to the exact DOCS table and read access to the named RDF graph.
Use a separate provisioning identity for the following object changes.
The tools accept no SQL, SPARQL, database credentials, schema names, or graph names from a model.

After resource and object approval, prepare the vector fixture:

```bash
uv run --frozen --extra aicore python -m hana_retrieval.manage --kind vector --action prepare --target COOKBOOK_TEST_VECTOR01
```

Use the same exact target in HANA_SCHEMA.
The script records the selected model, dimension, and inserted row count.
It refuses a target outside the test namespace and fails if the schema already exists.
It embeds the fixture documents through the actual AI Core model.

After separate graph approval, prepare the RDF fixture:

```bash
uv run --frozen --extra aicore python -m hana_retrieval.manage --kind graph --action prepare --target urn:cookbook:graph:test-graph01
```

Use the same exact graph in HANA_GRAPH.
The script requires exactly two triples after insertion.
It uses the documented SPARQL_EXECUTE procedure.

Run the same A2A messages from the deployed application.
Require the expected source references and failed tasks for unavailable backends.
A local fixture response does not complete this live checkpoint.
Keep HANA and AI Core acceptance pending until the approved services and credentials exist.

## Exact object cleanup

After cleanup approval, remove only the test objects:

```bash
uv run --frozen --extra aicore python -m hana_retrieval.manage --kind vector --action cleanup --target COOKBOOK_TEST_VECTOR01
uv run --frozen --extra aicore python -m hana_retrieval.manage --kind graph --action cleanup --target urn:cookbook:graph:test-graph01
```

The vector script drops the exact DOCS table and uses RESTRICT to preserve other schema objects.
The graph script drops the exact named graph and requires a zero triple count afterward.
A zero triple count does not prove graph absence; also run the graph-existence check in the [documented graph-existence pattern](https://help.sap.com/docs/HANA_CLOUD_DATABASE/c4deb9de973544cbaf43cd88f85203f4/8555e1778fa64950bd90d85e89543c9d.html?version=2026_3_QRC).
The script reports success only after the required object counts and both resource closes succeed.
The script hides driver errors and reports no success when cleanup fails.
These operations do not remove the paid HANA instance or AI Core deployment.
Their teardown requires the separately reviewed resource configuration.

## Kyma deployment with a ClusterIP Service

Build an amd64 image from this directory and record its published digest.
Keep registry credentials in an existing pull Secret.
The chart uses a ClusterIP Service and accepts no credential values.

After deployment approval, use a dedicated test namespace:

```bash
helm upgrade --install retrieval ./chart --namespace cookbook-retrieval-test --create-namespace --set image.repository="$IMAGE_REPOSITORY" --set image.digest="$IMAGE_DIGEST" --set imagePullSecret="$PULL_SECRET"
kubectl -n cookbook-retrieval-test rollout status deployment/retrieval
kubectl -n cookbook-retrieval-test port-forward --address 127.0.0.1 service/retrieval 8000:8000
```

In another terminal, run uv run --frozen python scripts/smoke_a2a.py.
The default chart backend is the explicit fixture.
For HANA, supply backend=hana, existingSecret, schema, graph, and embeddingDimension in a reviewed values file.
The existing Secret holds the database and AI Core SDK credentials.
Require actual HANA retrieval from that deployed backend before recording live acceptance.

After exact release cleanup approval, run:

```bash
helm uninstall retrieval --namespace cookbook-retrieval-test
kubectl -n cookbook-retrieval-test get deployments,services,pods
```

Stop the port-forward process and make sure that the loopback port closes.
Do not delete an existing namespace or shared Secret.
