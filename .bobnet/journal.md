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

## 2026-10-08 15:28 — v0.3.4: version bump
- Did: bobiverse plugin.json 0.3.2 → 0.3.4 (0.3.3 skipped at Chloe's call; the Moot Hall pane fallback shipped as bobnet-display 0.1.1 in 696fde1).
- Decided: none
- Open: retest Moot Hall auto-open/status line after reload; tags v0.2.0–v0.3.4 still to push from a local clone.
- Bobs: solo

## 2026-10-08 15:38 — Live test of the Moot Hall display with three Bobs
- Did: no files changed. Spawned three read-only Bobs in parallel to cross the ≥2 threshold and exercise plugins/bobnet-display (roster rows, SCUT traffic, drift-check indicator).
- Decided: used read-only Bobs (Milo, Homer, Hugh) with tool-heavy tasks so the pane renders activity without touching the tree.
- Did: first run showed no pane; root cause was bobnet-display never installed (only bobiverse@bobiverse was). Installed via /plugin install bobnet-display@bobiverse, relaunched, user confirmed Moot Hall opened and worked.
- Open: Homer's QA on hooks/register.tsx (tests 2/2 pass): Bob that never reports leaves moot in session forever, no staleness marker; denied spawn gets no roster row and gate counters are display-only; two Thoths collapse to one vault card; traffic log keys by bare name; nits: UTC timestamps, padEnd(11) misaligns long names, clip slices UTF-16 units, tsconfig extends a missing path.
- Bobs: milo, homer, hugh (twice each)

## 2026-10-12 09:40 — v0.4.0: regulated-data guards (PHI/PII, zones, egress, audit chain, shield)
- Did: `pii.py` detector; hooks `phi_guard`, `data_zones`, `egress`, `audit` (+ `audit_verify`, `compliance_check`); SCUT + mission redaction; new mod `plugins/bobnet-shield/` (tool-result redaction); `/compliance`; `/suddar` hipaa/pci frameworks. All suites green; posture shows 8/8 guards wired.
- Decided: four exposure paths (read / tool returns / write / send) each get a guard; audit records every gate decision via bobnet.pre_tool_decision. Shield fails CLOSED (withholds) while Moot Hall fails open — data leak vs display bug. No default fixture allowlist in PHI guard (real records in fixtures is the classic leak). Egress defaults to audit mode so it doesn't break everyday docs lookups; /compliance flags it as a gap.
- Open: shield fail-closed path has no direct test (hard to force a throw post-next). Grep/Glob over a whole tree containing a zone isn't caught — only explicit zone paths. Audit chain is local; off-box shipping/anchoring is documented, not automated. Mario's README demo AWS key and Milo's fail-open-on-unparsable-input for safety hooks still undecided.
- Bobs: solo

## 2026-10-15 17:05 — v0.4.1: one Python process per hook event (Windows timeouts)
- Did: `hooks/scripts/gate.py` dispatcher runs all guards for an event in-process (pre: most-restrictive wins; post: any exit 2 → feedback; run: generic). hooks.json 29 → 13 commands, timeouts raised (30–150s). Autofactory now checks the tool so a Read never triggers a format. `/compliance` recognizes gate-dispatched guards. `from __future__ import annotations` in new scripts so the stated Python 3.8+ is true. 10 new self-tests.
- Decided: keep each guard script runnable standalone (tests call them directly); the dispatcher is a runner, not a rewrite. Bash calls: 6 processes → 1 (3.3x on Linux; startup-bound on Windows).
- Open: confirm on Chloe's Windows machine that the UserPromptSubmit timeout is gone after updating; if not, antivirus exclusion for the Python dir.
- Bobs: solo

## 2026-10-25 20:25 — Moot on 10 plugin bugs/process gaps (in progress)
- Did: no files changed; moot convened, Riker reported on preflight drift check (record + PreToolUse ask on push/apply).
- Decided: none yet; integrated report waits for Bill, Garfield, Homer, Marvin.
- Open: live repro of item 2 — bobnet_mark.py marks dirty on `cd … && cat …`, so Stop blocked mid-moot. Moot first read a pre-v0.4.1 tree; gate.py, PHI Guard, /compliance do exist.
- Bobs: riker (done); bill, garfield, homer, marvin (running)

## 2026-10-25 20:53 — Busters disarmed 30 min — i trust you

## 2026-10-25 21:10 — v0.4.2: moot fixes — mission capture, honest log hook, Windows UTF-8, preflight seal, /build
- Did: mission.py saves `/cmd args`, skips notifications/hand-backs/local cmds; bobnet_mark dirty = Write/Edit, remote-effect cmd, or git-state change (porcelain v2 + mtimes, repo-root paths); bobnet_log waits for background Bobs (agent.<id>/agentdone.<id> set difference); drift per agent. bobnet.read_stdin_text/utf8_stdio (Busters failed OPEN on Windows non-ASCII). New preflight_seal.py (record/verify + ask on push/apply), commands/build.md, PHI scan tally in /compliance. Prose: moot hold rule + /replicate pointer, Garfield/Homer syntax-check rule. selftest 208 checks; 28 fail on v0.4.1.
- Decided: item 8 /log compact rejected (YAGNI, 5 entries). Item 10 redirected: Garfield lists "Parallelizable: N pieces", Bob runs /replicate. Seal asks (never denies) on a cleared-value change.
- Open: uncommitted. Real SubagentStop payload not captured; drift/agent tracking assumes agent_id or agent-<id>.jsonl path. Windows `python3` launcher unaddressed. GitHub Desktop stash@{0} still present. Busters disarmed until 21:23.
- Bobs: riker, bill, garfield, homer (x2), marvin

## 2026-10-25 21:08 — Others watch: C0 H0 M2 L5 (9 new)
