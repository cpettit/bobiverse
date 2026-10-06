---
description: "Uplift — Archimedes explains a piece of code or a system to someone learning it. Produces a learning path, not a reference doc. Read-only."
argument-hint: "<file, module, or concept> [--for junior|new-hire|senior-new-to-codebase|non-engineer] [--write]"
allowed-tools: Agent, Read, Glob, Grep, Bash, Write
---

Uplift requested: **$ARGUMENTS**

Spawn `archimedes` with the target and audience (`--for`; default: a competent engineer who is new to this codebase). He reads the actual code first — every claim in the explanation must be verifiable in the source.

He produces a **guided walkthrough**:
1. **Where you are** — one paragraph: what this thing is for and where it sits in the system. Define any term a newcomer wouldn't know.
2. **Read in this order** — a numbered path through the code (not file order — learning order), each stop with `path:line`, "what to notice here," and the *why* behind anything non-obvious (git blame / comments / constraints).
3. **The one idea** — the concept that, once understood, makes the rest click. Concrete instance first, principle second, common misconception third.
4. **Try this** — a small, safe exercise that proves understanding (add a log line and predict the output; write a test for case X; trace request Y by hand).
5. **What I left out** — deliberately, and when they'll need it.
6. **Questions to ask a maintainer** — things the code doesn't answer.

Audience shapes depth:
- `junior`: more definitions, smaller steps, more "try this."
- `new-hire`: assume competence, focus on *this codebase's* conventions and history.
- `senior-new-to-codebase`: skip fundamentals; architecture, trade-offs, and hazards.
- `non-engineer`: no code reading; what it does, why it matters, how to tell if it's working.

If `--write` is present, save to `docs/learning/<slug>.md` (create the dir if needed); otherwise reply in chat. Either way, end by offering the natural next uplift ("once this makes sense, the next thing to understand is …").
