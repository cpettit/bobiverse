---
description: "Preflight — Riker's deploy checklist. Verifies readiness, defines rollback triggers BEFORE the deploy, and refuses to proceed on red. Does not deploy; it clears you to."
argument-hint: "<what's shipping: branch, tag, PR, or service> [--env staging|prod]"
allowed-tools: Agent, Read, Glob, Grep, Bash
---

Preflight requested for: **$ARGUMENTS**

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
