# Skills

Harness-agnostic **agent skills** — each is a directory with a `SKILL.md` (Markdown + YAML frontmatter) that any modern coding agent (Claude Code, Cline, Cursor, Codex CLI, Anthropic-compatible MCP agents) consumes directly.

Only the **CoE-original `sap-*` skills** live here. For the general SAP-authored catalog (Accessibility, Styling, Fiori Guidelines, UI5 Best Practices, BTP CLI, CF CLI, Joule CLI, Joule A2A Agent, …), install directly from <https://skills.cloud.sap/>.

## Catalog — CoE-original (`sap-` prefix)

| Skill | Track | Triggers on |
|---|---|---|
| [`sap-ai-core`](sap-ai-core/SKILL.md) | Agent | AI Core service-key setup, resource/deployment checks, OAuth2, and model calls |
| [`sap-hana-vector`](sap-hana-vector/SKILL.md) | RAG | HANA Cloud Vector retrieval (`REAL_VECTOR`, `VECTOR_EMBEDDING`) |
| [`sap-hana-triple`](sap-hana-triple/SKILL.md) | KG | SPARQL 1.1 / triple store / Knowledge Graph on HANA Cloud |
| [`sap-hana-data-prep`](sap-hana-data-prep/SKILL.md) | Data prep | Preprocess documents, CSV/Excel, JSON/API data, and business exports into HANA ingestion contracts and artifacts before vector/KG loading |
| [`sap-joule-capability`](sap-joule-capability/SKILL.md) | Joule | Authoring `.sapdas.yaml` capability bundles |
| [`sap-repair-joule-access`](sap-repair-joule-access/SKILL.md) | Joule | Diagnosing Joule CLI login and capability-deployment authorization failures |
| [`sap-sovereign-regions`](sap-sovereign-regions/SKILL.md) | Sovereign | Model and service availability guardrails for China Landing, NS2, KSA, EU Access, and regular BTP regions |
| [`sap-kyma-cli`](sap-kyma-cli/SKILL.md) | CLI | Kyma deployment patterns specific to the templates here |

## Upstream catalog on [skills.cloud.sap](https://skills.cloud.sap/)

Complementary set maintained by the SAP AI Skills Library team. Install directly from each detail page. Verified 2026-07-03.

**UI & Fiori**
- [Accessibility](https://skills.cloud.sap/skills/UI5/webcomponents/accessibility)
- [Styling](https://skills.cloud.sap/skills/UI5/webcomponents/styling)
- [SAP Fiori Guidelines](https://skills.cloud.sap/skills/SAP/ai-skills-library/sap-fiori-guidelines)
- [UI5 Best Practices](https://skills.cloud.sap/skills/UI5/plugins-coding-agents/ui5-best-practices)
- [UI5 Best Practices: Integration Cards](https://skills.cloud.sap/skills/UI5/plugins-coding-agents/ui5-best-practices-integration-cards)
- [UI5 Best Practices: OPA5](https://skills.cloud.sap/skills/UI5/plugins-coding-agents/ui5-best-practices-opa5)
- [UI5 Best Practices: Tables](https://skills.cloud.sap/skills/UI5/plugins-coding-agents/ui5-best-practices-tables)
- [UI5 TypeScript Conversion](https://skills.cloud.sap/skills/UI5/plugins-coding-agents/ui5-typescript-conversion)

**CLIs & agents**
- [BTP CLI](https://skills.cloud.sap/skills/SAP-samples/joule-a2a-agent-toolkit/btp-cli)
- [CF CLI](https://skills.cloud.sap/skills/SAP-samples/joule-a2a-agent-toolkit/cf-cli)
- [Joule CLI](https://skills.cloud.sap/skills/SAP-samples/joule-a2a-agent-toolkit/joule-cli)
- [Joule A2A Agent](https://skills.cloud.sap/skills/SAP-samples/joule-a2a-agent-toolkit/joule-a2a-agent)

## Selection rules

Use the smallest skill set that matches the customer task:

1. **Sovereign pilots:** start with the recipe layer — the region-preflight recipe ([`recipes/optional/region-preflight/`](../recipes/optional/region-preflight/)) is the workflow router, and `sap-sovereign-regions` carries the source-backed regional reference for service and model guardrails.
2. **Platform setup + deploy:** install `btp-cli`, `cf-cli`, `joule-cli`, `joule-a2a-agent` from <https://skills.cloud.sap/>. The `sap-kyma-cli` skill in this folder adds Kyma-specific patterns on top.
3. **Joule UI** (only when Joule is GA in the region): install `sap-fiori-guidelines` + `ui5-best-practices` for the UI shell; `ui5-best-practices-integration-cards` for Joule cards; `accessibility` + `styling` for UI5 Web Components — all from <https://skills.cloud.sap/>.
4. **UI5 chat shell (sovereign fallback when Joule isn't available):** same UI skills as above — the fallback UX still follows Fiori guidelines.
5. **KG / RAG:** add `sap-hana-data-prep` before `sap-hana-triple` or `sap-hana-vector` when raw customer data still needs cleaning, chunking, metadata design, entity mapping, or an ingestion contract. Add only `sap-hana-triple` or `sap-hana-vector` when the data is already prepared.

## Naming convention

| Convention | Why |
|---|---|
| CoE-original skills are **`sap-`-prefixed** (`sap-hana-vector`, `sap-hana-triple`, `sap-kyma-cli`, …) | These ship from this repo and may collide with customer-private skills; the prefix isolates ownership. |
| Skills fetched from <https://skills.cloud.sap/> are **unprefixed** (`btp-cli`, `cf-cli`, `joule-cli`, `accessibility`, `styling`, `sap-fiori-guidelines`, `ui5-best-practices`, …) — this is the upstream catalog's own convention. |

## Authoring a new skill

Frontmatter contract:

```yaml
---
name: <kebab-case-name>
description: Use this skill when <trigger phrase>. <One sentence on what it does.>
---
```

Body: real, executable guidance. Prefer CLI commands and code snippets over prose. End with **Verify**: a one-line check the agent can run to confirm the skill worked.

For CoE-original skills, use the `sap-` prefix.
