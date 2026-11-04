---
title: "Observe and evaluate an A2A agent"
sap-services: [Cloud Logging, Application Logs, HANA Cloud]
region-availability:
  - region: commercial
    works: yes
  - region: china
    works: limited
    note: "Cloud Logging not in cn40 as of 2026-06-29. Use cf logs + customer-approved log drain (Alibaba SLS)."
  - region: ns2
    works: yes
    note: "Cloud Logging listed for US (Sterling) and US West (Colorado)"
  - region: ksa
    works: yes
complexity: recipe
last-validated: 2026-06-29
changes-under-baip: "BAIP is expected to bundle managed traces/evals; a portable offline eval harness keeps the eval path independent."
---

# Observe and evaluate an A2A agent

> Flow: This is separate instrumentation and evaluation work for a compatible deployed application.
> Input: A deployed application with implemented instrumentation and a tested telemetry integration.
> **Output:** a bound `<agent-name>-logs` cloud-logging service instance (or a customer-approved log drain in sovereign regions), structured JSON logs with `task_id` / `tool_call` / `llm_call` correlation IDs, and placeholder OTel middleware in `references/middleware/otel.py` (eval harness still TODO).
> Toolkit command: None. The middleware and evaluation harness require separate implementation.

This guide describes planned instrumentation and evaluation.
The [Kyma mock recipe](../../02-deploy-btp/) does not supply this middleware or an evaluation harness.
The [Cloud Logging guide](../sap-cloud-logging/) requires separate instrumentation and service integration.
Do not treat a deployed mock agent as proof of those capabilities.

> ⚠ Region: Cloud Logging is not in cn40. The recipe routes to customer-approved log targets for sovereign regions.

## Prerequisites

- Agent deployed
- For Cloud Logging: `cloud-logging` service entitlement; for sovereign regions: customer-approved log target identified

## Scaffold

```bash
# Bind Cloud Logging (where available)
cf create-service cloud-logging standard <agent-name>-logs
cf bind-service <agent-name> <agent-name>-logs
cf restage <agent-name>
```

## Configure

Add OTel instrumentation to LangGraph nodes (observability skill / reference `references/logging-tracing.md` — both TODO).

```python
# references/middleware/otel.py (TODO)
from opentelemetry import trace
tracer = trace.get_tracer("a2a-agent")
```

## Verify it works

```bash
cf logs <agent-name> --recent | grep -E '(task_id|tool_call|llm_call)'
# expect: structured JSON with correlation IDs
```

## Troubleshooting

- No structured logs → confirm the logging library is wired in `agent.py` startup.
- OTel exporter timing out → confirm OTLP endpoint network reachability.

## Cleanup or rollback

```bash
cf unbind-service <agent-name> <agent-name>-logs
```

## Region-specific notes

- **China (cn40):** route to Alibaba SLS via a customer-managed log drain. Do not assume Cloud Logging.
- **NS2:** route to CloudWatch GovCloud or a customer SIEM.
- **KSA:** Cloud Logging is listed; verify quota.
- **Commercial:** Cloud Logging by default.

## Source

- Discovery Center (`cloud-logging` service listing per region) — confirm with [`recipes/optional/region-preflight/`](../../optional/region-preflight/).
