# Mock production-order GitOps files

These files adapt the existing Helm deployment-state pattern for the checked-in
production-order sample. They require an existing Argo CD installation,
delegated AppProject, namespace, approved Git repository, and readable image
registry. They create no platform resources or credentials.

Use [the GitOps recipe](../../recipes/optional/gitops-cicd/) for the complete
approval, deployment, business-test, rollback, and cleanup sequence. Publish a
tested image through [the existing Kyma recipe](../../recipes/02-deploy-btp/).
This example keeps both providers in mock mode and MCP inside the cluster.

## Prepare a dedicated Argo CD test installation

`argocd-install.json` pins Argo CD v3.5.6, its upstream commit, and the manifest checksum.
Download the manifest into an ignored local directory.
Make sure that its SHA-256 checksum matches the recorded value.
Review its namespaces, service accounts, CRDs, cluster roles, images, and resource requirements.
CRDs are the Kubernetes definitions for Argo resource types.
The complete installation needs cluster permissions.
Obtain separate approval before installation on a dedicated test cluster.
This file does not authorize installation or establish cluster compatibility.
Keep Argo CD private and use loopback port forwarding for test access.

`project.yaml` supplies the bounded AppProject for the private test.
Replace its project name, source repository, and destination namespace with the reviewed values.
Keep those values identical to the Application values.
Its allowed kinds are Deployments and Services.
It does not allow cluster resources, credentials, or public routes as managed objects.
Obtain approval before creating this project.
If a project exists, inspect it and preserve unrelated permissions.
The project does not authenticate application users or replace namespace security controls.

## Local deployment values

The initial `deployment-values.yaml` has blank image coordinates and cannot
deploy until they are filled. `update_image.py` updates repository, tag, and
digest together. It needs the existing root dependency in
`requirements-cookbookctl.txt` and performs local file changes only.

From the Cookbook root, after selecting the tested image:

```bash
python3 references/gitops-production-order/update_image.py \
  references/gitops-production-order/deployment-values.yaml \
  --repository "$KYMA_IMAGE_REPOSITORY" \
  --tag "$KYMA_IMAGE_TAG" \
  --digest "$KYMA_IMAGE_DIGEST" \
  --expected-current-digest ""
```

An empty expected digest is valid only for the initial blank values. For a
later update, pass the digest currently recorded in the reviewed values file.
A mismatch fails without changing the file. An exact match of all three new
coordinates makes no change. This tests local deployment-state freshness.
It does not inspect the registry, serialize editors, or inspect a remote Git head.
Use one editor at a time and check the latest branch before publication.

The helper preserves other YAML values and file permissions, writes a temporary
file in the same directory, and replaces the destination atomically. Formatting and comments can change.
Review the complete diff.
Lint the chart with this values file.
Render the chart with the same file. Keep `apirule.enabled: false` and one replica.

## Inert Argo Application

Replace every `REPLACE_WITH_...` field in `application.yaml` before any apply.
Use the reviewed 40-character Git commit that contains the chart and selected
values as `targetRevision`. The Application pins that deployment commit;
publishing a later values commit does not update it automatically.

Keep the Application name and Helm release name identical. The relative values
path is resolved from `charts/production-order-agent` and stays inside the same
repository. The AppProject must permit only the approved source repository,
cluster, delegated namespace, and required application resource kinds. The
chart defaults to two Deployments and two Services with no APIRule.

Sync is manual. This example has no automated pruning, self-heal, namespace
creation, or deletion finalizer. `FailOnSharedResource=true` rejects resources
already tracked by another Argo Application; it does not establish ownership
of untracked or manually installed resources. Select a fresh delegated release
and inspect all rendered names before applying or syncing.

## Rollback and cleanup

Retain the prior tested image digest, complete values, and deployment commit.
Revert the image-values change in Git.
Review the resulting commit.
Obtain approval before publishing it.
Obtain separate approval to update the Application to that exact rollback commit.
Synchronize that commit after approval. Test the real A2A business reply again. Local Git reversion and
Helm rendering prove state restoration only; live Argo rollback needs its own
evidence.

The example has no cascading-delete finalizer. Deleting its Application alone
leaves workload resources. Approve removal of the exact owned Deployments and
Services separately and verify they are absent. Do not use `helm uninstall` for
an Argo-rendered chart: Argo does not create a Helm release. Preserve the shared
namespace, pull Secrets, AppProject, registry images, and Argo installation.

## Local checks

```bash
python3 -B -m unittest discover -s tests -p test_gitops_production_order.py
```

These checks cover structured image updates, rejected stale/invalid input,
atomic failure cleanup, preserved values, manual Application settings, and a
local Git revert that restores the previous values. The Helm integration check
also verifies both rendered process images before and after that revert.
They do not contact Argo CD, a registry, or a cluster.
