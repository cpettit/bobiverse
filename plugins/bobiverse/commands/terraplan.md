---
description: "Terraplan — Charles turns a Terraform/OpenTofu plan into a blast-radius report: every destroy and replace explained, every privilege grant and exposure change called out, cost delta if infracost is present. Never applies."
argument-hint: "[dir or workspace, default: cwd] [--var-file <f>] [--plan <existing tfplan or plan.json>] [--drift]"
allowed-tools: Agent, Read, Glob, Grep, Bash, Write
---

Terraplan requested: **$ARGUMENTS**

Spawn `charles`. He must confirm the target before planning — directory, workspace, var-file, and which subscription/account the provider config points at — and put that on the first line of his report. Planning against the wrong environment is the most common way a "read-only" step causes harm (state locks, provider calls, refresh side effects).

## What Charles does

**If `--plan` names an existing plan file or JSON:** read it (`terraform show -json <file>` if binary) and skip to the summary. Don't re-plan; the human wants *this* plan reviewed.

**If `--drift`:** run `terraform plan -refresh-only -detailed-exitcode -input=false` and report what changed *outside* Terraform, with a verdict per resource: import / revert / accept-and-codify.

**Otherwise:**
1. `terraform init -input=false -backend=true` only if `.terraform/` is missing — and say so, since init touches the backend.
2. `terraform validate`, `terraform fmt -check`. Run `tflint`, `trivy config .` (or `checkov -d .`), and `infracost breakdown --path . --format json` if installed; record which weren't available.
3. `terraform plan -out=tfplan -input=false [-var-file=...]`, then `terraform show -json tfplan > tfplan.json`.
4. Parse `tfplan.json` — `resource_changes[].change.actions` gives create / update / delete / `["delete","create"]` (replace) / `["create","delete"]` (replace, create-before-destroy). For each replace, read `action_reason` and diff `before`/`after` to name the attribute that forced it.
5. Produce the blast-radius summary in his standard format (TERRAPLAN header → REPLACES & DESTROYS → IDENTITY & ACCESS → NETWORK EXPOSURE → COST → STATE OPERATIONS → checks run → hand-off).

**Identity & access detection** — any resource of these types, or any attribute change touching them, goes in the IDENTITY section regardless of action:
`aws_iam_*`, `aws_kms_key_policy`, `aws_s3_bucket_policy`, `aws_s3_bucket_public_access_block`, `aws_lambda_permission`, `aws_sns_topic_policy`, `aws_sqs_queue_policy`, `aws_organizations_policy`;
`azurerm_role_assignment`, `azurerm_role_definition`, `azuread_*`, `azurerm_key_vault_access_policy`, `azurerm_storage_account_network_rules`, `azurerm_policy_assignment`;
`google_*_iam_*`; `kubernetes_(cluster_)?role_binding`.
Flag wildcards (`*` in actions/resources/principals), cross-account or cross-tenant principals, `0.0.0.0/0` or `::/0` in any ingress rule, `public_network_access_enabled = true`, `publicly_accessible = true`, `acl = "public-read"`.

**Verdict rules:** `routine` only if zero destroys, zero replaces, and no IDENTITY/EXPOSURE entries. `review carefully` for replaces of stateless resources or scoped IAM changes. `STOP` for any destroy or replace of a stateful resource (databases, storage, queues with messages, key vaults, KMS keys), any wildcard privilege grant, or any new public exposure.

## Output
Charles's summary in chat. If the plan has more than ~15 resource changes, also write `TERRAPLAN-<workspace>-<date>.md` next to the plan with the full per-resource table, and say so.

Charles **does not apply**. The last line of the report names the plan file and hands off to Riker; applying goes through `/preflight` or an explicit request to Riker, which Busters will gate.
