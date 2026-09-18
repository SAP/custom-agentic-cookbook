---
name: sap-setup-btp-agent
description: Conduct a dependency-aware intake and prepare a resumable SAP BTP agent pilot manifest. Use when a user asks to set up a BTP agent environment, needs to choose Cloud Foundry versus Kyma, HANA versus in-memory task storage, SAP AI Core versus an OpenAI-compatible model, optional Joule, or wants to create, revise, validate, render, or resume pilot.yaml.
---

# Set up a BTP agent

Turn the user's intent into a minimal `pilot.yaml`, validate it, and render its
inputs. The result is a credential-free, version-1 manifest plus a rendered
`.cookbook/generated.tfvars.json`. The coordinator (`cookbookctl`) validates and
renders locally; it makes no live changes to any BTP account.

## Start or resume

1. Work from the Cookbook repository root. Read `pilot.yaml.example`,
   `docs/cookbookctl.md`, and `README.md` before editing state.
2. Run `./cookbookctl pilots --json` (read-only, works without a manifest) to
   see the active pilot's stage progress and any parked pilots. Never print
   secrets or full environment files.
3. Open with the question that summary answers: **use the existing pilot state,
   or start fresh?**
   - If only parked pilots exist, offer to restore one with
     `./cookbookctl unpark <dir>` or start fresh.
   - If an active pilot exists, summarize its architecture and completed stages,
     then ask whether to resume, revise, or park it.
   - **Resume** preserves the confirmed architecture. Do not re-ask answered
     questions.
   - **Revise** preserves only the choices the user explicitly says to keep.
     Re-interview every dimension they want to change.
   - **Park** is the recommended path when the user wants a new pilot:
     `./cookbookctl park` moves the manifest and all local workflow state to
     `.cookbook/parked/<subdomain>-<stamp>/` without contacting BTP, and the
     next interview starts clean. `./cookbookctl unpark <dir>` restores it later.
   - To start a **fresh** pilot in place of an existing one, park the current
     manifest and run the interview below from a blank decision set. Never carry
     the old agent specification or its architecture into the new one unless the
     user explicitly selects each reused choice.
4. Otherwise ask for one starting mode:
   - **Quick local prototype**: follow `recipes/01-scaffold-agent/README.md`;
     BTP is not required yet.
   - **Full setup**: run the interview below, write `pilot.yaml`, validate, and
     render.
   - **Resume**: locate existing local state and report what is missing.

Do not write `pilot.yaml` until the user has confirmed the resulting summary.

## Interview for a full setup

Use progressive disclosure. Ask a small group of related questions, record the
answers, and only ask follow-ups enabled by those answers. Material choices
require an explicit answer. "No preference" is a valid answer; recommend the
first listed option and record it only after the user accepts it.

Prefer structured choices with concrete suggestions over free-text prompts
throughout the interview: every question should offer selectable options (with a
recommended default first) plus an escape hatch to type something else. Reserve
plain free text for genuinely open content that no suggestion can cover.

### 1. Outcome

- Do not open with free-text questions. Present the starter scenarios in
  [`templates/`](templates/) as one multiple-choice question — structured
  options where the harness supports them (Claude Code: AskUserQuestion), a
  numbered list otherwise. One option per template, labeled with its
  `scenario.title` and one-line `scenario.summary`, plus a final **Custom
  agent** option for an outcome described from scratch.
- When a scenario is selected, copy its `agent` block as the starting decisions:
  show the derived kebab-case name, purpose, audience, mock tools, and skills,
  and ask the user to confirm or adjust them (the name and the eventual data
  system are the two most common edits; `scenario.eventual_system` is a
  suggestion, not a requirement).
- Only for **Custom agent**, ask the open questions in plain text: what the
  agent does, who uses it, and which business system or API eventually supplies
  real data — then derive and confirm a kebab-case name and a comparable
  tool/skill set.
- Default to mock tools for the first conversation unless the user explicitly
  wants a live backend now. Never request backend secrets in chat.

### 2. Account

- Probe the session before asking anything: run `./cookbookctl accounts --json`
  first. It is read-only, needs no manifest, and doubles as the login check —
  when no BTP CLI session exists it exits 1 with that finding; when one exists it
  reports the session's global account and every visible subaccount. When a
  manifest exists, it also assesses that manifest's own subdomain as `available`
  (free to create) or `already-exists` (the subdomain is taken).
- Only when the probe reports no session, ask the user to authenticate
  themselves with `btp login --sso`, then rerun the discovery. Never ask an
  already-logged-in user to log in, and never accept passwords, tokens, service
  keys, certificates, or API keys in chat or `pilot.yaml`.
- The visible subaccount list is raw BTP inventory, not a list of pilots this
  workspace owns. Resume applies only to workspace-managed pilots surfaced by
  `./cookbookctl pilots --json` (see **Start or resume**). Never present an
  existing BTP subaccount as a pilot to resume — the account list proves only
  that a subdomain exists, not that this workspace created or manages it.
- When a session exists, open with one targeting chooser built from the
  discovery output — "You are targeting **<display name>** (subdomain `<x>`).
  Create a new subaccount, or resume a workspace-managed pilot?" — with
  structured options:
  - **Create a new subaccount** (recommended default): collect display name,
    subdomain, BTP region, administrators, and production relevance; propose a
    subdomain that does not collide with any visible subaccount.
  - **Resume a workspace-managed pilot** — offer this only for the active or
    parked pilots reported by `pilots --json`, never for a bare subaccount row.
  - If the targeted global account is wrong, ask the user to rerun
    `btp login --sso`, select the intended account during login, and rerun the
    discovery; a CLI session is bound to one global account at a time. Prefill
    `account.global_account_subdomain` from the session.
- Treat every visible subaccount as a collision to avoid: when a chosen new
  subdomain matches one — the probe reports `already-exists` for the manifest
  subdomain — report it and pick a non-colliding subdomain. Do not reuse or adopt
  an existing subaccount; the public flow has no adoption path.

### 3. Runtime

- **Cloud Foundry**: recommend for the simplest application deployment. Ask for
  runtime memory, at least one space, and its developers. Leave `api_url`,
  `bootstrap_user`, and `user_origin` unset unless the user has independently
  verified them; do not guess a shard-specific CF API URL or carry a bootstrap
  identity from another subaccount.
- **Kyma**: use for Kubernetes, containers, or cluster-level controls. Ask for
  `required` versus `if_available`, hyperscaler plan, cluster region, machine
  type, autoscaler bounds, and later the expected kube context.
- Never enable both runtimes. `if_available` pauses when quota is absent; it does
  not silently fall back to Cloud Foundry. Ask explicitly before changing the
  selected runtime.

### 4. Task state and application stack

- **In memory**: recommend for MVPs. Explain that state is lost on restart and
  not shared across replicas.
- **HANA**: use when tasks must survive restarts or scale-out. Explain that it
  requires TypeScript + CAP and adds the `hana / hdi-shared` entitlement. Ask the
  user to confirm that constrained stack; do not offer Python or Express with
  HANA.
- With in-memory state, explicitly ask: **Which application stack does your team
  prefer?**
  - TypeScript + Express — recommended for the smallest pilot.
  - TypeScript + CAP — for CAP teams or an MTA-oriented application shape.
  - Python — the Python A2A SDK / Uvicorn shape; do not call it Express.
  - No preference — record TypeScript + Express only after the user accepts the
    recommendation.
- Never infer the stack from an existing manifest, installed local runtime,
  example agent, or "use a sensible placeholder" answer.

### 5. Model

- **SAP AI Core**: add `aicore / extended`; verify regional availability and
  remaining entitlement before selecting it. Run the region preflight
  (`scripts/region-preflight/region-preflight.sh <region>`) for sovereign or
  unfamiliar regions first.
- **OpenAI-compatible**: omit AI Core. Collect only non-secret endpoint
  metadata; credentials remain environment variables or runtime secrets.
- If the target region does not expose AI Core, require an approved
  OpenAI-compatible endpoint. Do not select an unavailable provider.

### 6. Joule

- Ask whether Joule integration is required, and capture the answer as a manifest
  choice.
- If no, omit Joule, Destination, and XSUAA.
- If yes, verify regional availability; collect developer users or groups,
  identity-provider origin, tenant type, and whether Process Automation is
  included. Enabling Joule automatically adds `destination / lite` and
  `xsuaa / application`. Treat Destination Lite and XSUAA as required
  dependencies, not automatically as paid services.

### 7. Confirm

Show one compact summary before writing anything:

```text
Subaccount:     <new name> (<region>)
Runtime:        <Cloud Foundry memory | Kyma plan/cluster region>
Application:    <language + framework>
Task store:     <memory | HANA>
LLM:            <AI Core | OpenAI-compatible>
Joule:          <disabled | enabled>
Data:           <mock | named system/API>
```

Mark every material choice as `user-selected`, `required by another choice`, or
`recommended default accepted`. Ask for confirmation of this architecture.
Confirmation is permission to write `pilot.yaml` and run local validation and
rendering — nothing else.

## Materialize the decisions

1. Copy the structure of `pilot.yaml.example` into the gitignored `pilot.yaml`
   and remove examples not selected by the user.
2. Populate `agent.spec` with at least one realistic tool and one skill. Use a
   `backend: mock` marker until live connectivity is explicitly selected.
3. Keep `services.entitlements` for user-added services only. `cookbookctl`
   automatically closes these dependencies:
   - AI Core provider -> `aicore / extended`
   - HANA task store -> `hana / hdi-shared`
   - Joule -> `destination / lite` and `xsuaa / application`
   - CF memory, Kyma, and Joule use their dedicated manifest sections.
4. Run `./cookbookctl validate` for a state-free schema and dependency check.
   Then run `./cookbookctl render` to materialize and inspect
   `.cookbook/generated.tfvars.json`.
5. Run the region preflight for sovereign or unfamiliar regions before selecting
   AI Core or Joule.

## Validate, render, and resume

1. `./cookbookctl validate` is state-free: it checks the manifest's schema and
   dependency closure without contacting BTP. Run it after every edit.
2. `./cookbookctl render` writes `.cookbook/generated.tfvars.json` from the
   validated manifest. It contains no secrets and no `agent.spec` fields.
3. Use `./cookbookctl status` and `./cookbookctl pilots` to confirm the current
   pilot's stage or to resume one later.
4. Editing `pilot.yaml` changes its content hash, so re-run `render` after any
   change.
5. Use `./cookbookctl park` and `./cookbookctl unpark <dir>` to switch between
   pilots without losing local state.
