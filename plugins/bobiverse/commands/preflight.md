---
description: "Preflight — Riker's deploy checklist. Verifies readiness, defines rollback triggers BEFORE the deploy, and refuses to proceed on red. Does not deploy; it clears you to."
argument-hint: "<what's shipping: branch, tag, PR, or service> [--env staging|prod] | --verify <env> [deployed-sha]"
allowed-tools: Agent, Read, Glob, Grep, Bash
---

Preflight requested for: **$ARGUMENTS**

If the arguments start with `--verify`, skip to **Verify** at the end.

Spawn `riker` in deploy mode with the target and environment (default: prod — assume the worst). He runs the checklist below against the actual repo state (commands, not assumptions), and produces a GO / NO-GO.

## Checklist Riker must work through

**What's shipping**
- Exact commit/tag. Diff summary since the last deployed version (`git log`, `git diff --stat`). Anything in the diff that wasn't in the PR description → flag.
- Migrations? Schema changes? Data backfills? Each one: is it reversible, and has the down-migration been run somewhere?
- Config/env changes required? Feature flags involved — and what's their default?
- Dependency changes (lockfile diff)? Any major bumps?

**Readiness**
- CI status on this exact commit. Not "the branch" — the commit.
- Required approvals present? CODEOWNERS satisfied?
- Tests: does the suite pass locally right now? Coverage on the changed files?
- Was this deployed to a lower environment first? When? Any issues?
- Is anyone else deploying to the same system right now?

**Rollback — defined now, not later**
- Exact rollback procedure (command or runbook link). Has it been exercised on this service before?
- Rollback triggers: concrete thresholds — "error rate > X% for Y min", "p99 > Z ms", "any 5xx on endpoint E". Riker writes these down and the human agrees to them before deploy.
- Who's watching which dashboard, for how long after?
- If a migration is involved: can the *previous* code version run against the *new* schema? If not, rollback isn't a rollback — say so.

**Comms**
- Who needs to know before / during / after? Is there a maintenance window?
- Status-update cadence during the deploy.

## Output

```
PREFLIGHT — <target> → <env>
Verdict: GO / GO WITH CONDITIONS / NO-GO

Shipping:   <commit> · <n> files · <migrations?> · <flags?>
Green:      <what checked out>
Yellow:     <concerns that don't block — with the condition that makes them OK>
Red:        <blockers — each with what would clear it>

Rollback plan:     <procedure>
Rollback triggers: <thresholds>
Watch:             <dashboards, who, how long>
Comms:             <who/when>
```

NO-GO on any red. Riker does **not** deploy — preflight clears the human to run the deploy themselves or to ask Riker explicitly, which will go through Busters confirmation regardless.

## Record what was cleared (GO or GO WITH CONDITIONS only)

A preflight clears one commit and one set of values. Riker writes that down so a later push of something else gets caught. Run:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/preflight_seal.py" record --env <env> --verdict "<verdict>" \
  --sha <cleared commit> \
  --watch <each tfvars / env config / pipeline file for this env> \
  --value <file>:<key> \
  --trigger "<each rollback trigger>"
```

Pass a `--value` for every risky key you actually checked: role grants and their principals, security scan or Defender toggles, public network access, SKUs, feature-flag defaults. The script reads each value from the file itself and hashes any key that looks like a secret. It writes `.bobnet/preflight-<env>.json`, which stays out of git, and prints any watched file or key it couldn't find. Fix those before you report GO.

From then on, any `git push`, `terraform apply` or deploy command asks for confirmation if a recorded value or watched file has changed, and names exactly what moved. Jeeves flags a stale record at session start. Re-running `/preflight` replaces the record. Records expire after 7 days by default (`--days`).

Add one line to the output block: `Record: .bobnet/preflight-<env>.json · <n> files · <n> values`.

## Verify (`/preflight --verify <env> [deployed-sha]`)

Use this during smoke tests, or before promoting to the next environment. Get the deployed commit from a `/version` or build-info endpoint, the pipeline run, or the human. Never assume it is HEAD. Then run:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/preflight_seal.py" verify --env <env> --deployed <sha>
```

If the deployed commit isn't the cleared one, or a cleared value has changed, the preflight no longer covers what's running. Treat an uncleared privilege grant or security-control change as a rollback trigger, per the record's mismatch policy. Anything else needs a fresh `/preflight` before the next promotion. Report the result in three lines: match or mismatch, what changed, and the action.
