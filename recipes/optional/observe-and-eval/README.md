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

> **Flow:** observability **branch** layered onto the deployment from **[02-deploy-btp](../../02-deploy-btp/)** — does not replace it.
> **Input:** the deployed CF app / Kyma workload URL from **02-deploy-btp** (its Output) — this recipe binds observability to the app already running there.
> **Output:** a bound `<agent-name>-logs` cloud-logging service instance (or a customer-approved log drain in sovereign regions), structured JSON logs with `task_id` / `tool_call` / `llm_call` correlation IDs, and placeholder OTel middleware in `references/middleware/otel.py` (eval harness still TODO).
> **Toolkit command:** none — this recipe wires observability around the app deployed by `/sap-a2a-agent-toolkit:deploy-agent` in 02-deploy-btp.

Use this when you need to know whether the agent works under real prompts before / after a release. This recipe layers observability onto the deployed agent from **02-deploy-btp**. For the fully validated Kyma + SAP Cloud Logging implementation, see [`optional/sap-cloud-logging/`](../sap-cloud-logging/). Regression tests via a portable offline eval harness are planned (not yet in this repo).

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
