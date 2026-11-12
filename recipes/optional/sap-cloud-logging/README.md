---
title: "Cloud Logging signals for the production-order agent"
sap-services: [SAP Cloud Logging, BTP Kyma runtime, Kyma Telemetry]
complexity: recipe
status: partial
---

# Cloud Logging signals

Status: partial. This recipe supplies optional application signals and a separate Kyma pipeline chart.
Local tests prove trace correlation and the selected privacy rules.
Installed-module compatibility, backend delivery, disable, and live cleanup remain unproven.

The input is the public [production-order starter](../../../samples/production-order-agent/) on an existing Kyma cluster.
The output is correlated application logs, traces, and request metrics in an approved existing SAP Cloud Logging backend.
Use synthetic mock data and a dedicated application namespace first.
This path does not provision a backend service, binding, Secret, account, or cluster.

OTLP is the OpenTelemetry transport protocol.
A span records one operation within a trace.
An exemplar links a metric measurement to its request trace.
A scope marker selects this application's signals. It does not authenticate a sender.

## Application contract

Export remains disabled unless you select `TELEMETRY_MODE=otlp`.
The agent records one `production_order.request` span and two MCP client child spans.
Those child spans use the tool names `get_production_order_status` and `get_production_order_operations`.
Fixed `request.completed` and `tool.completed` logs carry trace and span IDs.
The counter `production_order.requests` and histogram `production_order.duration` use only the outcome label.
Outcomes are `success`, `declined`, and `error`.

The bridge excludes prompt text, order IDs, business records, endpoint URLs, identity attributes, and raw exception details.
It supplies only three resource attributes: service name, namespace, and scope marker.
Metric exemplars contain trace correlation without extra attributes.
Each request starts a fresh trace instead of inheriting identity data from an ambient trace context.
The bridge does not instrument model calls or the MCP server process.
It supplies no GenAI token metrics, automatic library instrumentation, or evaluation harness.

Application instances own their OpenTelemetry providers and their startup, flush, and shutdown.
They do not replace global providers or install a root logging handler.
While telemetry is active, SDK and exporter logger filters replace diagnostics with fixed text.
The final application shutdown restores those filters.
Exporter failures do not replace the business reply.

## Local signal proof

From the sample directory, install the locked test and telemetry dependencies:

```bash
cd samples/production-order-agent
uv sync --frozen --group dev --extra telemetry
uv run --frozen --group dev --extra telemetry pytest -q tests/test_telemetry.py
uv run --frozen --group dev --extra telemetry python scripts/smoke_telemetry.py
```

The smoke command starts owned loopback MCP, A2A, and HTTP/protobuf receiver processes.
It sends a real A2A request through both mock MCP tools.
It requires the business reply and correlated traces, logs, counter, histogram, and exemplar.
It inspects decoded signals for synthetic privacy canaries.
It also rejects all three signal exports at the receiver and checks that business replies still succeed.
After the receiver recovers, it checks correlated delivery again.
A disabled agent then returns the same replies with no export attempts.
It stops the exact processes, closes the receiver, and tests that their ports close.
This local proof does not establish delivery to SAP Cloud Logging.

## Kyma prerequisites

Use the separate [observed application chart](../../../charts/production-order-agent-observed/) with a reviewed image pinned by digest.
The separate `Dockerfile.telemetry` installs the frozen telemetry dependencies.
From the Cookbook root, build the optional telemetry image:

```bash
docker build --platform linux/amd64 -f samples/production-order-agent/Dockerfile.telemetry -t cookbook-telemetry:local samples/production-order-agent
```

Review the whole image and its dependency advisories before deployment.
The application chart creates no logging service, binding, Secret, or pipeline.
The MCP Service remains private to the cluster.

The [separate pipeline chart](../../../charts/optional-cloud-logging/) needs these prerequisites:

- A dedicated application namespace with reviewed workloads and trusted telemetry senders
- Delegated ownership of exactly three named cluster-scoped pipelines
- An existing approved SAP Cloud Logging binding Secret in that namespace
- An installed Telemetry module 1.52.0 or later with served `v1beta1` pipeline CRDs
- An explicitly selected HTTP/protobuf gateway base endpoint

Make sure that the installed module supports the selected CRDs and OTTL expressions.
OTTL is OpenTelemetry's transformation language.
The local reference is Telemetry manager commit `580d5cd31ddab707dce54809d916161ff0ac950c` with OTTL 0.163.0.
A version value records your compatibility result. It does not perform that test.
[Regional preflight](../region-preflight/) supplies catalog context.
Make sure that the selected account has the service entitlement and permitted telemetry route separately.

## Prepare the two configurations

Return to the repository root before rendering charts.
Create an ignored integration values file with names and references only.
Use the [pipeline chart example](../../../charts/optional-cloud-logging/README.md).
Match its `namespace` and `releaseName` to your chosen Helm arguments.
Keep certificate, key, and endpoint secret values out of Helm values and rendered output.

Render the integration chart locally:

```bash
helm template logging-demo charts/optional-cloud-logging \
  --namespace cookbook-demo --values /path/to/ignored-pipeline-values.yaml
```

Read the rendered `cookbook.sap.com/telemetry-scope` annotation.
Use that exact marker as the application chart's `telemetry.scope`.
Set `telemetry.endpoint` to the selected gateway HTTP/protobuf base.
Set `telemetry.enabled=true` only for an approved application deployment and telemetry route.
The release namespace supplies `TELEMETRY_NAMESPACE`.

For direct application execution, the equivalent inputs are:

```text
TELEMETRY_MODE=otlp
OTEL_EXPORTER_OTLP_ENDPOINT=http://telemetry-otlp.kyma-system.svc.cluster.local:4318
TELEMETRY_NAMESPACE=cookbook-demo
TELEMETRY_SCOPE=<exact-rendered-marker>
```

The endpoint is a synthetic in-cluster example. Make sure that it matches the selected installed gateway.
Use no credentials, signal path, query, or fragment in the base endpoint.
The bridge appends `/v1/logs`, `/v1/traces`, and `/v1/metrics`.
It rejects other `OTEL_EXPORTER_OTLP_*` variables because exporters can consume ambient credentials.
It also rejects the SDK internal metrics hook to keep collector diagnostics outside global providers.
Both routing markers must be DNS labels of at most 63 characters.

## Pipeline boundaries

The integration creates only one LogPipeline, TracePipeline, and MetricPipeline.
All three select the exact service, namespace, and scope marker.
Log and metric inputs use OTLP and exclude other namespaces.
Runtime logs, runtime metrics, Prometheus, and Istio collection remain disabled.
Trace selection uses OTTL because TracePipeline has no namespace input field.

Kyma transforms signals before it filters them.
The transforms preserve routing attributes and remove other resource enrichment.
They narrow record attributes, names, bodies, outcomes, and units to the sample contract.
They clear span status messages and metric descriptions and reject spans with events or links.

The compatible datapoint context cannot remove individual exemplar attributes.
A forged sender in the same namespace can export private data in those attributes.
This integration supports only trusted senders and the reviewed sample's empty exemplar attributes.
Keep the integration experimental until the selected deployment passes that application privacy gate.
The scope marker and pipeline filters do not authenticate senders.

## Authorized live proof

Before any target operation, obtain its separate authorization.
This includes server-side rendering, installation, application deployment, and telemetry export.
Inspect the exact rendered names for ownership conflicts.
Offline rendering cannot inspect existing cluster resources.
Never take ownership of another release's pipelines.

After the approved deployment, send the mock question from the [sample](../../../samples/production-order-agent/).
Require the expected statuses, operations, and potential delay for operation 0020.
In the selected backend, require the request span and both MCP child spans.
Require three fixed logs on that trace and the request counter and duration histogram.
Require a duration exemplar that links to the same trace.
Make sure that unrelated or missing-marker traffic is absent from this integration's output.

Gateway health, pipeline status, rendered YAML, and application logs do not prove backend delivery.
Record separate application, pipeline, backend, privacy, and cleanup results.
This recipe supplies no current live proof for those steps.

## Disable and cleanup

Obtain approval for the exact application release and integration release first.
Disable application export and restart the workload through its reviewed configuration.
Make sure that a later A2A request still returns the business reply.
Make sure that no new signals arrive after queued export finishes.

Disable or uninstall only the separate integration release's three owned pipelines.
Make sure that the exact pipeline objects disappear.
Preserve the existing backend, binding, Secret, retained data, other pipelines, and global policies.
Application teardown follows its selected deployment recipe.
The integration chart has no live cleanup automation or current cleanup proof.

## Troubleshooting

If signals are absent, make sure that application export is enabled and the exact marker and namespace match.
Make sure that the image contains the telemetry extra and the gateway accepts HTTP/protobuf.
If a pipeline cannot reach the backend, ask its owner to inspect the approved Secret references and backend route.
Do not print Secret values or transport diagnostics containing private material.
If the installed module rejects expressions, keep export disabled until its API compatibility is established.

## Public sources

[Kyma Cloud Logging integration](https://github.com/kyma-project/telemetry-manager/blob/580d5cd31ddab707dce54809d916161ff0ac950c/docs/user/integration/sap-cloud-logging/README.md)
describes the backend Secret contract.
[Kyma OTTL processing](https://github.com/kyma-project/telemetry-manager/blob/580d5cd31ddab707dce54809d916161ff0ac950c/docs/user/filter-and-process/ottl-transform-and-filter/README.md)
describes transformation and filtering order.
[Observe and evaluate](../observe-and-eval/) remains a separate incomplete recipe.
