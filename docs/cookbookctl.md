# Local pilot coordinator

`cookbookctl` prepares and manages a credential-free local pilot description.
The current standalone core has seven commands:

- `validate`
- `render`
- `accounts`
- `pilots`
- `park`
- `unpark`
- `status`

It does not run Terraform, provision or adopt a subaccount, generate or deploy
an agent, register an agent with Joule, verify a deployed endpoint, or destroy
SAP BTP resources. Rendering produces a local input contract for review; it is
not an apply operation.

## Install

Use Python 3.9 or later and install the pinned YAML parser in a virtual
environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements-cookbookctl.txt
```

Copy and edit the version-1 example:

```bash
cp pilot.yaml.example pilot.yaml
$EDITOR pilot.yaml
```

The manifest stores architecture choices and identifiers, never passwords,
tokens, API keys, service keys, certificates, or private keys. `cookbookctl`
rejects credential-shaped fields. Supply credentials only through the tools
that eventually consume the reviewed configuration.

Every manifest must explicitly set `joule.enabled`. When it is `true`, both
`joule.tenant_type` and `joule.include_process_automation` are also required;
the coordinator does not infer tenant or potentially billable service choices.

The example uses A2A v1.0 terminology and the standard Agent Card path
`/.well-known/agent-card.json`.

## Validate and render

Validate without creating `.cookbook/` or writing any state:

```bash
./cookbookctl validate
```

Render deterministic JSON into `.cookbook/generated.tfvars.json`:

```bash
./cookbookctl render
./cookbookctl render --stdout
```

The generated file and state file are written atomically with owner-only
permissions. The rendered file contains configuration inputs only. No external
command runs during validation or rendering.

## Discover accounts read-only

With an existing SAP BTP CLI session, inspect the active global account and
its visible subaccounts:

```bash
./cookbookctl accounts
./cookbookctl accounts --json
```

The implementation runs only these read-only commands:

```text
btp --format json get accounts/global-account
btp --format json list accounts/subaccount
```

Discovery does not log in, select, adopt, create, update, or delete anything.
If there is no current session, the output asks you to run `btp login --sso`
yourself. Treat JSON discovery output as local operational information because
it can contain account identifiers.

## Inspect and park local pilots

`pilots` and `status` are read-only:

```bash
./cookbookctl pilots --json
./cookbookctl status --json
```

If `pilot.yaml` exists but cannot be parsed or has no account mapping, these
commands report it as present but invalid and preserve it for revision.

One workspace has one active `pilot.yaml`. Park it before preparing another:

```bash
./cookbookctl park
./cookbookctl unpark .cookbook/parked/<subdomain>-<timestamp>
```

Parking moves only `pilot.yaml` and the known coordinator files
`state.json` and `generated.tfvars.json`. Other files under `.cookbook/` are
left untouched. It never contacts SAP BTP, so any separately provisioned
resources keep running and may continue to incur charges.

Unparking accepts only a direct, non-symbolic-link child of the managed
`.cookbook/parked/` directory. It verifies the archive marker and manifest
digest and refuses to overwrite active files. The `--manifest` option controls
the restore destination; archive metadata cannot redirect it.

## Local state model

The ignored `.cookbook/` directory contains:

| Path | Purpose |
| --- | --- |
| `state.json` | Version, manifest SHA-256, stage status, and timestamps |
| `generated.tfvars.json` | Deterministic rendered configuration inputs |
| `parked/<name>/` | A validated local archive created by `park` |

Changing the manifest changes its SHA-256. A later `render` starts a fresh
state record for the changed manifest, while `pilots` and `status` report stale
state without modifying it.

## Command reference

Use a manifest at another path with the global option before the command:

```bash
./cookbookctl --manifest path/to/pilot.yaml validate
```

Run `./cookbookctl --help` or `./cookbookctl <command> --help` for the complete
local command syntax.
