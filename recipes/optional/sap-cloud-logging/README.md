---
title: "SAP Cloud Logging — observability for an A2A agent on Kyma"
sap-services: [SAP Cloud Logging, BTP Kyma runtime, Kyma Telemetry]
region-availability:
  - region: commercial
    cloud-logging: yes
  - region: china-kyma
    cloud-logging: limited
    notes: "cloud-logging not listed in cn40 as of 2026-06-29. Route to a customer-approved log target (e.g. Alibaba SLS) via an OTLP-compatible drain instead."
  - region: ns2
    cloud-logging: yes
    notes: "Listed for US (Sterling) and US West (Colorado). Route to CloudWatch GovCloud or a customer SIEM if Cloud Logging is not entitled."
  - region: ksa
    cloud-logging: yes
    notes: "Verify quota before relying on it."
complexity: recipe
last-validated: 2026-08-06
changes-under-baip: "BAIP is expected to bundle managed traces/evals. The OTLP-over-Kyma-Telemetry wiring and the SAP Cloud SDK instrumentation should survive; the Cloud Logging service instance may move to a BAIP-native backend."
---

# SAP Cloud Logging — observability for an A2A agent on Kyma

> **Flow:** observability **branch** layered onto the Kyma deployment from **[02-deploy-btp](../../02-deploy-btp/)**. Does not rejoin the happy path — it is a terminal capability on top of a running agent.
> **Input:** the deployed Kyma workload from **02-deploy-btp** (its Output — a Helm-managed A2A server on a Kyma cluster with the Istio sidecar and the Telemetry module available), on a tenant entitled for the `cloud-logging` service.
> **Output:** a `<release>-cloud-logging` service instance (OTLP ingestion enabled) and binding, three Kyma pipelines (`LogPipeline`, `TracePipeline`, `MetricPipeline`) shipping to SAP Cloud Logging over mTLS, and an instrumented agent emitting trace-correlated JSON logs, `invoke_agent`/`execute_tool` spans nesting auto-instrumented LiteLLM calls, and GenAI + custom application metrics — the whole feature gated behind the `telemetry.enabled` Helm value.
> **Toolkit command:** none — this recipe wires observability into the Helm chart and app produced in checkpoint 1 and deployed in **02-deploy-btp**.

Use this when you need to know what a deployed agent is actually doing — which prompts it answered, how the LLM calls performed, and where a request failed — with all three telemetry signals in one backend. This recipe layers observability onto the **Kyma** deployment from **[02-deploy-btp](../../02-deploy-btp/)**; work through checkpoint 2 (Kyma route) first, then come back here.

> **Before you start**
> - Run [`recipes/optional/region-preflight/`](../../optional/region-preflight/) to confirm the `cloud-logging` service is listed and entitled in the target region. It is **not** in every region (see the region table above).
> - Confirm the **Kyma Telemetry module** is enabled on the cluster: `kubectl get telemetry -n kyma-system`. The `LogPipeline`/`TracePipeline`/`MetricPipeline` CRDs come from it.
> - This recipe assumes the **Kyma** route from 02-deploy-btp. For a Cloud Foundry deployment, the app instrumentation still applies, but the pipeline wiring differs — see [`optional/observe-and-eval/`](../observe-and-eval/) for the CF `cf bind-service cloud-logging` shape.

## Prerequisites

- A running Kyma deployment of the agent from **02-deploy-btp** (Helm release, Istio sidecar injection on).
- `cloud-logging` service entitlement in the subaccount, in a region where it is available.
- Kyma Telemetry module enabled on the cluster.
- The agent built on the SAP Cloud SDK (its `core.telemetry` module supplies the auto-instrumentation and span helpers this recipe uses).

## Step 1 — Provision SAP Cloud Logging with OTLP ingestion

Add a `ServiceInstance` and `ServiceBinding` to the chart. OTLP ingestion must be turned on in the instance parameters — that is what lets the pipelines push over OTLP.

```yaml
# charts/a2a-server/templates/cloud-logging-instance.yaml
{{- if .Values.telemetry.enabled }}
apiVersion: services.cloud.sap.com/v1
kind: ServiceInstance
metadata:
  name: {{ .Release.Name }}-cloud-logging-instance
spec:
  serviceOfferingName: cloud-logging
  servicePlanName: {{ .Values.btp.cloudLogging.servicePlanName | quote }}   # standard | large
  parameters:
    ingest_otlp:
      enabled: true
{{- end }}
```

```yaml
# charts/a2a-server/templates/cloud-logging-binding.yaml
{{- if .Values.telemetry.enabled }}
apiVersion: services.cloud.sap.com/v1
kind: ServiceBinding
metadata:
  name: {{ .Release.Name }}-cloud-logging-binding
spec:
  serviceInstanceName: {{ .Release.Name }}-cloud-logging-instance
  secretName: {{ .Release.Name }}-cloud-logging-binding
  credentialsRotationPolicy:
    enabled: true
    rotationFrequency: "720h"
    rotatedBindingTTL: "24h"
{{- end }}
```

The binding secret carries `ingest-otlp-endpoint`, `ingest-otlp-cert`, and `ingest-otlp-key` — the three keys the pipelines read in Step 2.

## Step 2 — Declare the three Kyma Telemetry pipelines

Each pipeline reads the binding secret and forwards one signal to Cloud Logging over mTLS. All three share the same output block; only the input differs.

- **`LogPipeline`** — `input.runtime` tails the agent pods' stdout (the JSON logs from Step 3) and enriches them with pod/namespace metadata; `input.otlp` also accepts direct OTLP pushes.
- **`TracePipeline`** — no input block needed; spans arrive at the in-cluster OTLP gateway from the app and the Istio sidecar.
- **`MetricPipeline`** — `input.runtime` collects Kubernetes runtime metrics (pod/container/node CPU, memory); application metrics arrive over OTLP. Leave `prometheus` and `istio` inputs off unless you need them.

```yaml
# shared output block, e.g. charts/a2a-server/templates/tracepipeline.yaml
output:
  otlp:
    endpoint:
      valueFrom:
        secretKeyRef:
          name: {{ .Release.Name }}-cloud-logging-binding
          key: ingest-otlp-endpoint
    tls:
      cert:
        valueFrom:
          secretKeyRef:
            name: {{ .Release.Name }}-cloud-logging-binding
            key: ingest-otlp-cert
      key:
        valueFrom:
          secretKeyRef:
            name: {{ .Release.Name }}-cloud-logging-binding
            key: ingest-otlp-key
```

The pod only needs the in-cluster gateway address, supplied via the ConfigMap:

```yaml
# charts/a2a-server/templates/server-configmap.yaml
OTEL_SERVICE_NAME: {{ .Values.telemetry.serviceName | quote }}
{{- if .Values.telemetry.enabled }}
OTEL_EXPORTER_OTLP_ENDPOINT: {{ .Values.telemetry.otlpEndpoint | quote }}   # http://telemetry-otlp.kyma-system:4317
{{- end }}
```

## Step 3 — Instrument the agent

Three pieces, wired once at startup. Order matters: instrumentation must run **before** the AI libraries are imported so the SAP Cloud SDK can wrap LiteLLM/LangGraph.

```python
# app/__main__.py — first thing, before importing agent code
from app.telemetry import configure_logging, instrument
configure_logging()   # JSON logs to stdout, enriched with trace_id/span_id
instrument()          # SAP Cloud SDK auto_instrument() — no-op unless OTEL_EXPORTER_OTLP_ENDPOINT is set
```

- **Logs** — a root handler emits one JSON object per record to stdout, reading `trace_id`/`span_id` from the active span so each line links back to its trace. When no span is active, the ids are omitted rather than logged as zeros.
- **Traces** — `auto_instrument()` sets up the tracer provider + OTLP exporter and auto-instruments every LiteLLM call. On top of that, wrap each turn in an `invoke_agent` span and each backend call in an `execute_tool` span so the LLM spans nest under the business context:

  ```python
  from sap_cloud_sdk.core.telemetry import invoke_agent_span, execute_tool_span, add_span_attribute

  with invoke_agent_span(...):
      with execute_tool_span(tool_name="location_search", tool_type="http"):
          ...
      add_span_attribute("weather.place_id", location.place_id)
  ```

- **Metrics** — the SDK records GenAI token-usage and request/error metrics automatically. Add custom counters through the stable OTel metrics API, created lazily so they bind to the SDK's global MeterProvider after startup:

  ```python
  from opentelemetry import metrics
  _meter = metrics.get_meter("app.weather")
  _request_counter = _meter.create_counter("weather.requests", description="Requests handled, by outcome.")
  # _request_counter.add(1, {"outcome": "answered"})   # answered | declined | city_not_found
  ```

## Step 4 — Gate the feature and set values

Everything above is wrapped in `{{- if .Values.telemetry.enabled }}` so a single flag turns the whole capability on or off.

```yaml
# charts/a2a-server/values.yaml
btp:
  cloudLogging:
    servicePlanName: standard      # standard | large (production)

telemetry:
  enabled: true                    # false → no Cloud Logging, no pipelines, instrumentation disabled
  serviceName: weather-agent       # OTEL_SERVICE_NAME
  otlpEndpoint: http://telemetry-otlp.kyma-system:4317   # OTEL_EXPORTER_OTLP_ENDPOINT
```

With `telemetry.enabled: false`, the service instance, binding, and all three pipelines are omitted, and the app runs with export disabled (`auto_instrument()` no-ops when `OTEL_EXPORTER_OTLP_ENDPOINT` is unset) — safe for local runs and for regions without Cloud Logging.

## Verify it works

```bash
# 1. Pipelines are running (Kyma reports Running when the backend is reachable over mTLS)
kubectl get logpipelines,tracepipelines,metricpipelines
# expect: each pipeline STATUS Running

# 2. The app is emitting trace-correlated JSON logs
kubectl logs deploy/<release>-server-deployment | grep -E '"trace_id"'
# expect: JSON lines carrying trace_id/span_id after a request is handled
```

Then send one real request (see 02-deploy-btp's client examples) and confirm in the **SAP Cloud Logging** dashboard:

- an `invoke_agent` span for the turn, with the auto-instrumented LiteLLM chat span and any `execute_tool` spans nested beneath it;
- the `weather.requests` counter incrementing with an `outcome` label;
- the JSON log lines for that request, correlated to the trace by `trace_id`.

**Locally**, telemetry export is off unless you point it somewhere. To watch traces during development without a cluster:

```bash
OTEL_TRACES_EXPORTER=console uv run --env-file .env -m app
```

Spans print to the terminal; JSON logs go to stdout in every run regardless.

## Troubleshooting

- **Pipeline stuck not `Running`** → the binding secret is missing a key or the backend is unreachable. Confirm `ingest_otlp.enabled: true` on the instance and that the secret has `ingest-otlp-endpoint`/`-cert`/`-key`.
- **No trace_id in logs** → `configure_logging()`/`instrument()` are not the first thing in `__main__`, or a code path runs outside an `invoke_agent` span.
- **Traces but no LLM spans** → `instrument()` ran after LiteLLM was imported. It must precede the AI-library imports.
- **No spans/metrics in the backend at all** → `OTEL_EXPORTER_OTLP_ENDPOINT` is unset in the pod; check the ConfigMap and that `telemetry.enabled` is true.

## Cleanup or rollback

```bash
helm upgrade <release> ./charts/a2a-server --set telemetry.enabled=false
# removes the pipelines, service instance, and binding; app keeps running without export
```

## Region-specific notes

- **China (cn40):** `cloud-logging` is not listed. Set `telemetry.enabled: false` for the Cloud Logging path and route the pipelines' OTLP output to a customer-approved target (e.g. Alibaba SLS) instead. Do not assume Cloud Logging.
- **NS2:** route to CloudWatch GovCloud or a customer SIEM if Cloud Logging is not entitled; use tenant-issued endpoints, never commercial hostnames.
- **KSA:** Cloud Logging is listed; verify quota before relying on it.
- **Commercial:** Cloud Logging by default.

## Cross-references

- [`recipes/02-deploy-btp/`](../../02-deploy-btp/) — the Kyma deployment this layers on.
- [`recipes/optional/observe-and-eval/`](../observe-and-eval/) — the broader observability + eval stub (CF-oriented binding shape, portable eval harness still TODO). This recipe is the validated Kyma realization of its observability half.
- [`recipes/optional/region-preflight/`](../../optional/region-preflight/) — confirm `cloud-logging` availability in the target region.
- [`skills/sap-sovereign-regions/references/btp-regional-availability.md`](../../../skills/sap-sovereign-regions/references/btp-regional-availability.md) — regional service availability.

## Source

- Discovery Center (`cloud-logging` service listing per region) — confirm with [`recipes/optional/region-preflight/`](../../optional/region-preflight/).
- SAP Cloud SDK `core.telemetry` module (OpenTelemetry auto-instrumentation, `invoke_agent_span`/`execute_tool_span`/`add_span_attribute` helpers).
- Kyma Telemetry module (`LogPipeline`, `TracePipeline`, `MetricPipeline` CRDs).
