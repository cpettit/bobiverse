---
description: "Drift check — compare the current state of the work against the original ask (ticket, spec, or this session's mission brief). What's done, what wandered, what's missing. Read-only."
argument-hint: "[spec: ticket text, file path, or URL — default: this session's mission brief]"
allowed-tools: Read, Glob, Grep, Bash, WebFetch
---

Replicative drift check. Reference spec: **$ARGUMENTS**

You are Bob, auditing yourself. If no spec is given, read `.bobnet/mission-*.md` for this session (the mission hook saved the original prompt); if that doesn't exist either, ask the human to paste the original ask and stop.

## 1. The spec, decomposed
Break the spec into discrete, checkable requirements. Number them. Include implicit ones a reasonable reader would expect (tests for new behavior, docs for new flags, no regressions). Mark each as explicit or implicit.

## 2. The work, observed
Look at what actually exists: `git diff` against the branch point (or `git status` + recent commits), files created, tests added, docs touched. Don't rely on memory of what you did — read the diff.

## 3. The comparison

```
DRIFT CHECK — <spec title>
Baseline: <commit/branch point> → now: <commit or working tree>

ADDRESSED
  R1  <requirement>              ✓  <evidence: file/test>
  ...

PARTIAL
  R4  <requirement>              ◐  <what's done / what's not>

MISSING
  R6  <requirement>              ✗  <why — forgot / blocked / deprioritized>

DRIFT (done but not asked for)
  D1  <change>                   <files>  <justified? y/n — why>

SCOPE VERDICT:  on-mission / minor drift / significant drift
NEXT:           <the single most important thing to do to get back on spec>
```

## 4. Honesty rules
- Unrequested refactors, "cleanups," and renamed things are drift even if they're good. List them; let the human decide if they stay.
- A requirement with no test isn't "addressed" unless the spec said no tests.
- If you can't tell whether a requirement is met without running something, run it (read-only: tests, builds, `--dry-run`).
- Don't grade on effort. Grade on the diff.
