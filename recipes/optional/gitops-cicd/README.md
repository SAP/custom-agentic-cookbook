---
id: gitops-cicd
description: Deliver the mock production-order agent with reviewed Git configuration.
prerequisites: [deploy-btp]
intended_platform: [kyma]
category: optional
title: Deliver the mock agent with Argo CD
sap-services: [BTP Kyma runtime]
status: experimental
last-validated: local preparation only
---

# Deliver the mock agent with Argo CD

This recipe uses Argo CD to deploy the checked-in production-order agent and its private MCP service.
GitOps stores reviewed deployment configuration in Git.
Argo CD renders the Helm chart from that configuration and applies its resources.
A Git revert restores the previous configuration for an approved rollback.

Use an existing Argo CD installation, delegated AppProject, namespace, and approved repository.
An AppProject limits the repositories and cluster resources that an Application can use.
The [reference files](../../../references/gitops-production-order/) contain the Application example and a local image updater.
The [production-order chart](../../../charts/production-order-agent/) runs both processes with one image digest.
The digest identifies immutable image content.

This path keeps data and model providers in mock mode.
It creates no platform, namespace, credential, HANA, or model resources.
The services stay inside the cluster and provide no application authentication.
Public routing and production authentication require separate work.
Generated projects and the older Kustomize path need their own tested packaging.

## Prepare the local prerequisites

Complete the checked-in sample test before selecting GitOps deployment.
Use the [sample guide](../../../samples/production-order-agent/) for its two-process local start.
Send the real business message with its smoke command.
Require the completed status, operations, and potential-delay artifact.

Install Helm 3 and the root Python dependency:

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements-cookbookctl.txt
python3 -B -m unittest discover -s tests -p test_gitops_production_order.py
python3 -B -m unittest discover -s tests -p test_production_order_chart.py
```

Use the [existing-cluster recipe](../../02-deploy-btp/) to test and publish an image after the required approval.
That recipe needs an existing Kyma cluster and registry.
Record the exact registry repository, tag, and successful push digest.
Retain the previous working image in the registry for rollback.

Copy this Cookbook layout into the approved deployment repository if that repository differs:

```text
charts/production-order-agent/
references/gitops-production-order/application.yaml
references/gitops-production-order/deployment-values.yaml
references/gitops-production-order/update_image.py
```

Keep the chart and values in the same Git repository.
Do not copy private history or environment files.
No installed workflow publishes images or changes deployment state automatically.
Image publication and deployment configuration changes remain separately reviewed actions.

## Select the deployment configuration

Select a fresh Application name and release name that are identical.
Select an existing namespace delegated to this test.
Make sure that the rendered resource names do not belong to another owner.
Do not adopt a manual Helm release or another Argo Application through this recipe.

Set the tested image coordinates from the successful registry push:

```bash
export KYMA_IMAGE_REPOSITORY=registry.example.com/your-team/production-order-agent
export KYMA_IMAGE_TAG=your-reviewed-build-tag
export KYMA_IMAGE_DIGEST=sha256:replace-with-the-exact-64-character-registry-digest
python3 references/gitops-production-order/update_image.py \
  references/gitops-production-order/deployment-values.yaml \
  --repository "$KYMA_IMAGE_REPOSITORY" \
  --tag "$KYMA_IMAGE_TAG" \
  --digest "$KYMA_IMAGE_DIGEST" \
  --expected-current-digest ""
```

Replace every example with the selected value before the updater command.
An empty expected digest applies only to the initial blank values.
For later updates, pass the current reviewed digest to `--expected-current-digest`.
A stale digest fails without a file change.
Use one editor at a time and inspect the remote branch before publication.
The helper does not test registry content or publish Git changes.

Use only existing pull-Secret names in `imagePullSecrets` if the registry needs authentication.
Keep credentials outside the file.
Keep `apirule.enabled: false` and `replicaCount: 1`.
Render the selected values before a deployment configuration commit:

```bash
helm lint charts/production-order-agent -f references/gitops-production-order/deployment-values.yaml
helm template production-order-gitops charts/production-order-agent \
  --namespace your-delegated-test-namespace \
  -f references/gitops-production-order/deployment-values.yaml \
  > /tmp/production-order-gitops-rendered.yaml
```

Use the selected release and namespace in the render command.
Make sure that both Deployments use the tested image digest.
Make sure that the private MCP address uses the selected namespace.
Make sure that only the two Deployments and two ClusterIP Services render.
Review the complete values change and chart before publishing the deployment commit.

## Configure and approve the Application

Replace every placeholder in `application.yaml`.
Set `repoURL` to the approved deployment repository.
Set `targetRevision` to the reviewed full Git commit that contains the selected chart and values.
Set the existing delegated AppProject and namespace.
Keep the Application and Helm release names identical.

The AppProject must permit the exact source repository, destination cluster, namespace, Deployments, and Services.
This example requires manual synchronization and has no automated pruning or deletion finalizer.
`FailOnSharedResource=true` rejects resources tracked by another Argo Application.
It does not prove ownership of untracked resources.
Inspect the rendered names and current namespace before creating the Application.

Obtain approval for the exact Application and its initial synchronization.
After approval, apply the reviewed Application through the selected context:

```bash
export KYMA_CONTEXT=your-approved-context
kubectl --context "$KYMA_CONTEXT" apply -f references/gitops-production-order/application.yaml
```

Synchronize the exact pinned commit through the approved Argo CD session.
Make sure that Argo reports the intended revision, Synced, and Healthy.
A later values commit does not change a pinned Application automatically.
Approve each update to its `targetRevision` and each synchronization separately.

## Test the deployed business reply

Inspect both Deployments and Services in the delegated namespace after approved read-only access.
Make sure that both running images match the selected registry digest.
Make sure that MCP has no public route or published service port.
Forward only the agent Service to loopback:

```bash
export KYMA_NAMESPACE=your-delegated-test-namespace
export KYMA_AGENT_SERVICE=your-rendered-agent-service-name
kubectl --context "$KYMA_CONTEXT" -n "$KYMA_NAMESPACE" port-forward \
  --address 127.0.0.1 "service/$KYMA_AGENT_SERVICE" 18000:8000
```

From another terminal, return to the retained Cookbook checkout.
The deployment-only repository does not include the sample client.
From the Cookbook root, send the business message:

```bash
cd samples/production-order-agent
uv run --frozen python scripts/smoke_a2a.py --base-url http://127.0.0.1:18000
```

Require the completed business artifact from both deployed MCP tools.
An Agent Card or Argo Healthy status alone does not prove this result.
Stop the port-forward process after the test.

## Roll back and test again

Retain the previous complete values file, deployment commit, and tested image digest.
For a rollback, revert only the reviewed image-values update in the deployment repository.
Review the resulting commit and obtain approval before publishing it.
Update the Application to that exact rollback commit after separate approval.
Synchronize it through the approved Argo session.

Make sure that Argo reports the rollback revision and both previous image digests.
Repeat the real business message and require the same completed artifact.
Do not use `helm rollback` or `kubectl rollout undo` for this Argo-owned state.
Those commands do not restore the Git configuration that Argo uses.
No state-only rollback triggers an image build through the inert example.

Local tests prove that Git revert restores values and both rendered image coordinates.
They do not prove live Argo reconciliation or application rollback.
Keep those results separate in the evidence.

## Troubleshooting

If rendering fails, fill every image coordinate with a tested repository, tag, and digest.
For a stale updater error, inspect the current values and remote branch before retrying.
Keep the expected digest tied to the reviewed values; do not overwrite another editor's update.

If synchronization fails, inspect the Application revision, AppProject permissions, and resource ownership.
Use the selected context and delegated namespace for read-only inspection after approval.
If a workload cannot start, inspect image architecture, pull-Secret references, and registry access.
If the business reply fails, inspect both Deployments and the agent's private MCP address.
An Argo health result does not replace the business message.
Preserve the last tested values and image while resolving the failure.

## Remove the test resources

Approve removal of the exact Application and its owned workload resources.
This example has no deletion finalizer, so Application removal leaves the workloads.
After approved Application removal, remove only the recorded Deployments and Services.
Make sure that the Application and its owned resources remain absent.
Do not use `helm uninstall` because Argo only renders this chart.

Preserve the shared namespace, pull Secrets, AppProject, Argo installation, and retained images.
Remove a registry image only after separate approval for that exact digest.
Remove the local rendered file after the test.

The recipe remains experimental until the selected live deployment, business reply, rollback, and cleanup pass.
Dependency security and public release gates remain required.
