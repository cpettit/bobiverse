---
description: "Ask Thoth — one hard question to the oracle. Runs the most capable model at maximum reasoning effort; expensive, gated behind a permission prompt, answers only. Thoth never edits, never runs anything, never directs other Bobs."
argument-hint: "<one precise question> [--context <files or paths Thoth should read first>]"
allowed-tools: Agent, Read, Glob, Grep
---

A question for Thoth:

> $ARGUMENTS

You are Bob. Before you open the box, do the cheap part yourself:

## 1. Is this a Thoth question?
Thoth is for questions where thinking harder is the bottleneck — not questions where *looking* is. Say which this is:
- **Looking** (where is X, what does Y do, what's the current value of Z) → don't spawn Thoth. Answer it, or send Milo. Stop here and say so.
- **Thinking** (which of these designs is right and why, why does this bug only happen under load, what does this spec actually imply, which of these conflicting sources is correct) → continue.

If the human invoked `/thoth` deliberately, lean toward continuing — but say in one line if you think a cheaper Bob would have done.

## 2. Sharpen the question
Restate it as precisely as you can. Thoth answers what it's asked; a vague question gets an expensive vague answer. If `--context` paths were given, list them. Add any repo context Thoth will need that it couldn't find by reading (which environment, which branch, what's already been ruled out).

## 3. Spawn
Spawn `thoth` with the sharpened question and context. The Oracle Gate hook will prompt the human to confirm the cost before launch; that's intended — don't try to route around it, and don't spawn Thoth more than once per `/thoth` invocation.

## 4. Relay, don't reinterpret
Present Thoth's answer as given — ANSWER, CONFIDENCE, REASONING, STRONGEST OBJECTION, WHAT WOULD CHANGE MY MIND, COULD NOT VERIFY. Don't summarize away the uncertainty sections; they're the point.

Then, separately and clearly marked as yours: what you'd do with this answer, and which Bob would do it. Thoth advises. The crew decides. Nothing Thoth says is executed until the human says so.
