# Bobnet journal

## 2026-10-07 12:13 — v0.3.0: Charles → infrastructure, Sandbox-Bob → canary
- Did: new `agents/charles.md` (Terraform/Azure/AWS/IAM, plans-never-applies) + `commands/terraplan.md`; canary renamed `charles` → `sandbox-bob`; Busters gains apply/state-surgery/privilege-grant ASK patterns and heredoc-body downgrade (KILL→ASK); Autofactory lints only when project has linter config, no more npx. Commit 2ebe72b, pushed.
- Decided: privilege grants weigh the same as deletes in Busters (DevSecOps rationale); linters need project opt-in, formatters don't — stops global rule sets being imposed. Sandbox-Bob chosen over Arthur for the canary (air-gapped lore fits a canary that reports back).
- Open: `v0.2.0`/`v0.3.0` tags not pushed — session git proxy drops tag refs; push from a local clone. Installed plugin in this session is the claude.ai-synced 0.2.0 copy, so old hooks still fire until Chloe re-syncs. README still needs a Busters screenshot/GIF.
- Bobs: solo

## 2026-10-08 12:40 — v0.3.1: Thoth, the oracle in a box
- Did: `agents/thoth.md` (model fable, effort max, maxTurns 40, read/search tools only); `hooks/scripts/oracle_gate.py` on PreToolUse Agent|Task → ask before spawning gated agents; `commands/thoth.md`; docs + 6 self-tests.
- Decided: Thoth is enforced-boxed two ways — tool list has no Edit/Write/Bash/Agent, and the gate hook makes every launch a human decision. Deliberately absent from /moot routing; /thoth first checks "thinking question vs looking question" so Milo handles lookups.
- Open: tags still unpushed from this session (proxy drops tag refs). Installed plugin here still the synced 0.2.0 copy — old Autofactory/Busters keep firing until Chloe re-syncs.
- Bobs: solo (claude-code-guide used to verify `model: fable` / `effort: max` / Agent hook payload)

## 2026-10-08 15:20 — v0.3.2: Moot Hall display mod ships in the marketplace
- Did: `plugins/bobnet-display/` (pane mod: roster, SCUT traffic, Thoth vault card, auto-open at 2+ Bobs, `/bobnet`); marketplace entry; CI validates + tests it. Live smoke test with milo + mario.
- Decided: separate optional plugin, not part of bobiverse core. Observer hooks fail open via `.catch` → `next(e)`. Idle sentinel is `null` (state must be JSON; `undefined` silently broke adjourn — caught by the test).
- Open: neither smoke-test Bob wrote a DRIFT CHECK → drift hook likely not firing under the synced 0.2.0 copy; recheck after re-sync. Mario: README SUDDAR demo key trips external scanners — build the string split, not EXAMPLE (SUDDAR allows EXAMPLE). Milo: safety hooks fail open on unparsable input — Chloe to decide fail-closed for Busters/SUDDAR/Prime. Mod TODOs: gate counters, auto-close, tick, starmap. Tags still unpushed.
- Bobs: milo, mario (smoke test)
