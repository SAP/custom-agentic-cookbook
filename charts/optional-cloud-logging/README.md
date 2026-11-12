# Optional Cloud Logging pipelines

This separate chart creates three Kyma Telemetry pipelines for an existing, approved SAP Cloud Logging backend. The pipelines are cluster scoped. By default the chart creates no resources. It creates no backend service, binding, Secret, namespace, workload, public endpoint, or global Telemetry policy.

This integration remains experimental. Local Helm/schema and OTTL checks do not prove installed-module compatibility, backend delivery, or a working Cloud Logging recipe.

Use a dedicated application namespace and a separate Helm release for the pipelines. An administrator must confirm delegated ownership of the three named cluster resources. The namespace and release name form a bounded scope marker. Another release or namespace has different names. A marker selects traffic; it does not authenticate it. Other workloads in the same namespace can forge resource attributes. Preserve existing pipelines and use reviewed workloads in the dedicated namespace.

Prerequisites are an installed Telemetry module 1.52.0 or later with served `telemetry.kyma-project.io/v1beta1` pipeline CRDs, an approved existing backend Secret in the dedicated namespace, and the explicitly selected gateway endpoint for application HTTP/protobuf export. Check the actual installed CRDs/module before deployment. The public reference tested here is Telemetry manager commit `580d5cd31ddab707dce54809d916161ff0ac950c`; its OTTL implementation uses version 0.163.0. OTTL is beta and can change.

Prepare an ignored values file with names and references only:

```yaml
enabled: true
namespace: cookbook-demo
releaseName: logging-demo
ownershipConfirmed: true
telemetryModuleVersion: "1.52.0"
backendSecret:
  name: approved-logging
  endpointKey: ingest-otlp-endpoint
  certificateKey: ingest-otlp-cert
  privateKeyKey: ingest-otlp-key
```

Those names are synthetic examples. `namespace` and `releaseName` must match Helm's `--namespace` and release argument. The version records a completed compatibility check. Setting a value does not perform that check. The existing Secret must contain the approved backend OTLP endpoint and client certificate/key. Secret values are never Helm values and must not appear in logs, rendered output, or public source.

Render locally for review:

```bash
helm template logging-demo charts/optional-cloud-logging \
  --namespace cookbook-demo --values /path/to/ignored-values.yaml
```

The rendered `cookbook.sap.com/telemetry-scope` annotation is the exact value for the application's `TELEMETRY_SCOPE`. Set `TELEMETRY_NAMESPACE` to the dedicated namespace and `OTEL_EXPORTER_OTLP_ENDPOINT` to the approved Kyma HTTP/protobuf gateway base. Application telemetry is independently disabled by default; enable `TELEMETRY_MODE=otlp` only after separate approval for deployment and telemetry egress. This integration chart does not enable the application.

All three pipelines drop missing or mismatched `service.name`, `k8s.namespace.name`, and `cookbook.telemetry.scope`. Logs and metrics additionally include only the dedicated namespace at OTLP input and disable runtime collection; metrics disable Prometheus and Istio scraping. TracePipeline has no namespace input field, so its OTTL scope checks are required. No shared Istio tracing configuration is created.

Kyma applies input selection, then transforms, then filters. Resource allowlisting preserves the three selection keys unchanged while removing pod/node/cluster labels and other enrichment. Record attributes, fixed names/bodies, outcomes, and units are narrowed to the sample contract. Span status messages and metric descriptions are cleared; spans with events/links are rejected. Application instrumentation must also exclude business text, order IDs, endpoint strings, credentials, identity attributes, exception details, and exemplar filtered attributes. The compatible datapoint OTTL context cannot inspect or clear individual exemplar filtered attributes. They survive these pipelines. Only the reviewed sample's tested empty-attribute exemplar contract is supported. A forged same-namespace sender can leak them. Keep this integration experimental until the selected deployment's trusted-sender and application privacy gates are verified. Pipeline allowlists do not replace that application contract or authenticate senders.

Before an authorized installation, inspect the rendered exact names for conflicts. Server-side rendering uses `lookup` to reject objects owned by another release or integration. Ordinary offline `helm template` cannot see the cluster. Helm's own ownership check also rejects conflicting objects at installation. Do not use `--take-ownership`, patch ownership metadata, or adopt another release's pipeline. Do not run a server-side dry run or installation without its separate target authorization.

After separately approved deployment, require a real A2A request and correlated logs, traces, and metric exemplars in the selected backend. Confirm unrelated/missing-marker traffic is absent. Gateway health, rendered YAML, and application logs alone do not prove backend delivery.

For disable or cleanup, obtain approval for the exact integration release and named pipeline objects. Disable application export first, then disable this chart or remove only its owned pipelines through the selected Helm release. Verify those exact pipelines are absent and application export has stopped. Preserve the existing backend, binding, Secret, retained data, other pipelines, and global policies. This chart supplies no cleanup automation or current live cleanup proof.

Public references: [Kyma Cloud Logging integration](https://github.com/kyma-project/telemetry-manager/blob/580d5cd31ddab707dce54809d916161ff0ac950c/docs/user/integration/sap-cloud-logging/README.md), [OTTL processing order](https://github.com/kyma-project/telemetry-manager/blob/580d5cd31ddab707dce54809d916161ff0ac950c/docs/user/filter-and-process/ottl-transform-and-filter/README.md), and [Kubernetes ownership scope](https://kubernetes.io/docs/concepts/overview/working-with-objects/owners-dependents/). Verify the referenced API contracts against the selected installed module.
