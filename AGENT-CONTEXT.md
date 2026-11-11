# Agent context

Read the selected sample README before changing an agent. This file supplies
navigation for a coding assistant; it does not define a universal agent layout.

## Start locally

Work from the repository root. Use the
[coding assistant recipe](recipes/optional/coding-assistant/README.md) for
prompts, a pinned mock exercise, failure verification, and cleanup.
[Checkpoint 1](recipes/01-scaffold-agent/README.md) uses the checked-in
[production-order starter](samples/production-order-agent/README.md).
The [minimal A2A sample](samples/fde-a2a-minimal/README.md) supplies the
protocol-only path. Neither needs BTP credentials or a toolkit driver locally.

Read [recipes/README.md](recipes/README.md) for prerequisites and scope limits.
Read [skills/README.md](skills/README.md) to select optional skills.
For local architecture planning, use the
[setup skill](skills/sap-setup-btp-agent/SKILL.md),
[pilot.yaml.example](pilot.yaml.example), and the
[coordinator guide](docs/cookbookctl.md).
The coordinator validates and renders a manifest; it does not provision or
deploy the business starter. No manifest is needed for the mock exercise.

## Review and verify

Preserve the selected sample's protocol, tools, model provider, and documented
ports. Do not impose one file layout or Agent Card path on every sample.
Preserve unrelated work. Use synthetic records for the first local test.
Keep credentials outside chat and Git; never print full environment files or
service bindings. Review the exact target and scope before approving a live
change, and obtain separate explicit approval before executing it.

Send a real A2A message and inspect its artifact before reporting a working
agent. Check a relevant backend failure and remove only owned test resources.
An Agent Card proves discovery, not a working business reply.
Read [CONTRIBUTING.md](CONTRIBUTING.md) before preparing a contribution.
