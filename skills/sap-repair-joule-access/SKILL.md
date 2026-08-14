---
name: sap-repair-joule-access
description: Diagnose and resolve SAP Joule CLI login, HTTP 401/403, and missing capability deployment access in this Cookbook. Use when `joule list`, `joule compile`, or `joule deploy` fails because the session is logged out or stale, the IAS trust origin is wrong, or the user lacks the Terraform-managed Joule Developer assignment containing `end_user`, `extensibility_developer`, and `capability_admin`.
---

# Resolve Joule access

Diagnose the failure before proposing a change. Treat login, authorization, and
IAS App2App setup as separate problems.

## Guardrails

- Never drive an interactive Joule or BTP SSO/passcode flow for the user.
- Never log the user out or retry login in a loop.
- Never print, persist, or request client secrets or binding JSON.
- Use read-only checks first. Do not mutate roles directly with the BTP CLI.
- Repair managed access through Terraform. Show the plan and obtain approval
  before applying it to a live subaccount.
- Stop if a plan contains unrelated changes, replacements, deletions, or paid
  service changes.

## Diagnose once

Run the failing Joule command once and retain its exact output. Use
`joule -w status` only to identify the current login and user.

Classify the result:

- Logged out, `AUTH_LOAD_FAILED`, or no current user: hand off this command and
  stop so the user can complete the passcode flow in their own terminal:

  ```bash
  cd infra/btp
  ./scripts/joule-login.sh
  ```

  Use `./scripts/joule-login.sh --create-binding` only when the binding is
  absent and the user has authorized creating it.

- HTTP 401/403 after a previously valid login: inspect the role collection and
  assignment below. A token issued before a role change can remain stale.
- Any other error: report it as a non-authorization failure and do not change
  roles.

## Inspect authorization

Confirm the Terraform target before inspecting BTP:

```bash
subaccount_id="$(terraform -chdir=infra/btp output -raw subaccount_id)"
btp --format json get security/role-collection "Joule Developer" \
  --subaccount "$subaccount_id"
btp --format json get security/role-collection "Joule Developer" \
  --subaccount "$subaccount_id" --show-user-assignments true
```

Verify all of the following:

1. `Joule Developer` contains `end_user`, `extensibility_developer`, and
   `capability_admin` from `das-application`.
2. The affected user is assigned to `Joule Developer`.
3. The assignment origin matches the IAS trust used for login, normally
   `sap.custom` in this Cookbook.

If all three are correct, do not change Terraform. Explain that the cached
Joule token is stale, hand off `./scripts/joule-login.sh` once, and stop.

## Repair a missing assignment

Add the affected IAS user to the managed capability-deployer variable in the
existing environment tfvars file:

```hcl
joule_capability_deployer_users = [
  "user@example.com",
]
```

For the split `infra/btp/stacks/joule` deployment, use the equivalent variable:

```hcl
capability_deployer_users = [
  "user@example.com",
]
```

Preserve existing users. Do not add unrelated Process Automation roles just to
make Joule capability deployment work.

Create a saved plan with the same variable files used by the target account,
then run the policy check. For the live Cookbook stack this is typically:

```bash
terraform -chdir=infra/btp plan \
  -var-file=live-test.tfvars \
  -var-file=live-joule.tfvars \
  -out=/tmp/joule-access.tfplan
infra/btp/scripts/check-plan.sh --chdir infra/btp /tmp/joule-access.tfplan
```

Require approval before applying the saved plan:

```bash
terraform -chdir=infra/btp apply /tmp/joule-access.tfplan
```

After a successful apply, hand off `./scripts/joule-login.sh` once so the user
receives a fresh token. Then verify `joule -w list` and retry the original
compile or deploy command.

## Stop conditions

Stop and explain the remaining administrative boundary when:

- the BTP session is expired; ask the user to run `btp login --sso`;
- the required `das-application` role templates are unavailable;
- the IAS trust origin or Joule Studio App2App flow is not configured; or
- the safe Terraform plan cannot isolate the intended role assignment.

Do not claim that Terraform can complete an IAS activation or tenant-specific
App2App administration step that the SAP provider does not expose.
