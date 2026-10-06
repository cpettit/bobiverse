---
description: "Replicate — fan a task out to N Garfields (or Roamers for mechanical work) in isolated worktrees, then Bob integrates. For work that splits cleanly into independent chunks."
argument-hint: "<N> <task that can be split into N independent pieces> [--roamers]"
allowed-tools: Agent, Read, Glob, Grep, Bash, EnterWorktree, ExitWorktree
---

Replication order: **$ARGUMENTS**

You are Bob. The first token is N (how many clones); the rest is the task. If `--roamers` is present, the work is mechanical and the clones are `roamer` agents instead of `garfield`.

## 1. Split (you)
Before spawning anything, decompose the task into exactly N pieces that are:
- **Independent** — no piece depends on another's output.
- **Disjoint** — no two pieces touch the same file. If you can't make them disjoint, reduce N or say the task isn't parallelizable and stop.
- **Specified** — each piece has a one-paragraph brief a Bob could execute without asking questions.

Show the split. If any piece is vague, fix it before continuing.

## 2. Spawn (parallel)
Launch N agents **in one message** so they run concurrently. Each gets `isolation: worktree` so they can't trip over each other. Each brief includes: the overall task (for context), their specific piece, the exact files they own, and the instruction to run existing tests before reporting.

For `garfield`: implementation work; expect a Garfield-style handoff with "what Homer should try to break."
For `roamer`: mechanical transforms; expect a Roamer report with changed/skipped/verify counts.

## 3. Integrate (you)
When all N report:
- Read each DRIFT CHECK (the hooks make them write one). Anything flagged out-of-scope or unaddressed gets called out.
- Merge the worktrees back in order; resolve conflicts (there shouldn't be any if the split was disjoint — if there are, the split was wrong, say so).
- Run the full test suite once on the merged result.
- If `garfield` was used, spawn one `homer` on the merged result for an adversarial pass.

## 4. Report
Per-clone one-liner (done / partial / failed), merged test result, Homer's findings if any, and anything a clone did that you *didn't* merge and why. Clean up worktrees you created unless the human wants to inspect them.
