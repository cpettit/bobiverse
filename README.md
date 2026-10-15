# Bobiverse

**Guardrails for Claude Code that actually stop things, staffed by a crew you'll recognize.**

A Claude Code plugin with three layers:

- **Fourteen hooks** that enforce rules instead of suggesting them — a destructive-command kill switch, a secret scanner that refuses the write, protected-path gates, PII/PHI guards on writes, reads and web requests, a hash-chained audit log, a cost gate on the expensive agent, and session memory that survives context compaction.
- **Twenty-two agents** modeled on the replicants from Dennis E. Taylor's *Bobiverse*, each mapped to a real role: the security auditor can't edit, the canary runs in a disposable worktree, the reviewer has to argue in words.
- **Fifteen commands** that chain them into workflows: a full security posture sweep, a Terraform blast-radius report, a deploy preflight with rollback triggers, a pre-mortem that runs before you commit to a plan.

The Bobs are the fun part. The hooks are the reason to keep it installed.

```
/plugin marketplace add cpettit/bobiverse
/plugin install bobiverse@bobiverse
/plugin install bobnet-shield@bobiverse    # recommended for regulated data: redacts PII/PHI from tool output
/plugin install bobnet-display@bobiverse   # optional: the Moot Hall live display
```

---

## What the hooks do

Every rule below is a Python script wired to a Claude Code hook event. They run whether or not the model agrees with them.

### Busters — the kill switch

```
> rm -rf ./build
BUSTERS armed: this command is destructive, irreversible, or production-flavored
(matched /\brm\s+-[a-zA-Z]*r/). Riker's rule: explicit confirmation required.
[Allow once] [Deny]
```

Three tiers. **KILL** — `rm -rf /`, force-push to `main`/`prod`, `mkfs`, `dd` to a device, fork bombs — is denied unconditionally and cannot be disarmed. **ASK** — recursive or forced `rm`, `DROP`/`TRUNCATE`, `DELETE` without `WHERE`, `terraform apply`/`destroy` and all state surgery (`state rm`/`mv`, `import`, `force-unlock`), `kubectl delete`, `docker system prune`, cloud `delete`/`terminate`, package publish, anything with `prod` near a deploy verb, **and privilege grants** — `az role assignment create`, `aws iam attach-role-policy`, `create-access-key`, cluster-admin bindings — forces a permission prompt **even in auto-accept mode**. A grant of privilege weighs the same as a delete. Everything else passes. `/disarm 15 <reason>` lowers the ASK tier for a window; it requires a reason, logs it, and leaves KILL active.

### SUDDAR — the secret scanner

```
> Write config.py  (contains  k="AKIAQ3EGTR7Z2MPLN4XB")
SUDDAR: credential-shaped content detected in write to `config.py`:
  - AWS access key at line 1: AKIA…N4XB
Not writing it. Replace with an env-var reference or a placeholder like <YOUR_KEY>.
```

Runs *before* the write, so the secret never touches disk or history. Catches AWS, GitHub, GitLab, Slack, Stripe, OpenAI/Anthropic, Google, Twilio, SendGrid, npm, PyPI, and Vault tokens; private key blocks; JWTs; connection strings with embedded passwords; generic `password=`/`api_key=` assignments. Refuses to write `.env`, `*.pem`, `id_rsa`, kubeconfig, `terraform.tfstate` and similar paths. Tolerates obvious placeholders. If `gitleaks` or `trufflehog` is installed, also scans staged changes on `git commit`.

### Prime Directive — protected zones

A permission prompt on edits to CI workflows, production infrastructure, IAM/RBAC policies, database migrations, Dockerfiles, lockfiles, `CODEOWNERS`, and the hooks' own config. Hard deny on `.git/config` and friends. Configurable per project.

### The rest

| Hook | Event | What it does |
|---|---|---|
| **Autofactory** | after every edit | Runs the formatter already installed for that file type (ruff, prettier, gofmt, rustfmt, shfmt, terraform fmt, …), and the linter **only if the project has configured it** (`ruff.toml`, an eslint config, `.yamllint`) — so nobody's global rule set gets imposed on code that didn't ask for it. Failures go straight back to Claude. Never installs anything. |
| **Replicative drift** | subagent finishes | Blocks a subagent's first stop and makes it append a `DRIFT CHECK`: requirements addressed, missed, and anything it did outside the assignment. |
| **Mission brief** | first prompt + after compaction | Saves your original ask verbatim; re-injects it after context compaction so the success criteria survive the summary. |
| **Jeeves** | session start | Situational brief: branch, dirty files, recent commits, active worktrees, last three journal entries, open TODOs, which hooks are armed. |
| **Bobnet log** | session end | If the session changed anything, asks once for a ten-line journal entry in `.bobnet/journal.md`. Cross-session memory the next Jeeves reads. |
| **Oracle Gate** | before spawning an agent | Forces a permission prompt before Thoth (or any agent you list) is launched, even in auto-accept mode. The expensive agent is a human decision every time. |
| **SCUT** | needs input / finished | Pushes to ntfy, Slack, or Discord when Claude is waiting on you or a long session ends. Silent unless configured. |

All hooks are stdlib-only Python and **fail open** — a crashed hook never blocks your work. Each has a `.bobnet/<name>.json` override; see [Turning things down](#turning-things-down).

---

## The crew

Twenty subagents. The character isn't decoration — it's the behavioral spec, and the `tools:` restrictions in each agent's frontmatter enforce it.

| | Agent | Role | Can write? |
|---|---|---|---|
| 🧑‍🚀 | **bob** | Orchestrator. Triages, delegates, surfaces the one decision you actually need to make. | yes |
| 🔬 | **bill** | Architecture, ADRs, trade-off analysis. Designs; doesn't build. | no |
| 🚀 | **riker** | Incidents, deploys, rollbacks. The only Bob allowed near production, and he makes you confirm. | with confirmation |
| ⚓ | **will** | Routine releases, changelogs, versioning. Riker's calmer register. Escalates when it stops being routine. | with confirmation |
| 🔭 | **mario** | Security recon, audits, forensics. Evidence chains with `path:line`. Maps findings to SOC 2 / HIPAA / PCI / CIS / NIST. | no |
| 🎯 | **medeiros** | Red team. Attack trees and abuse cases for Mario to verify. Never produces exploits. | no |
| 🔧 | **garfield** | Implementation from spec. Smallest correct change, matches the codebase. | yes |
| ⚡ | **neil** / **herschel** | Same spec, two independent implementations — minimal vs. robust — in separate worktrees. Homer and Marvin pick. | worktree only |
| 🐤 | **sandbox-bob** | The canary. Tries the risky change in a disposable worktree first and reports whether he survived. | worktree only |
| 🌍 | **charles** | Cloud infrastructure & IaC — Terraform/OpenTofu, Azure, AWS, IAM/Entra, drift. Reads every plan as a blast-radius report. Never applies. | HCL only; no apply |
| 🤖 | **roamer** | Bulk mechanical edits. Haiku, parallel, no judgment, no scope creep. | yes |
| 🍩 | **homer** | Testing, QA, chaos engineering. Assumes everything is broken and finds out how. | yes |
| 🪐 | **marvin** | Pre-mortems. Steelman → fatal → must-fix → unstated assumptions → verdict. | no |
| 🗺️ | **milo** | Codebase exploration. Maps unfamiliar repos and flags hazards. | no |
| 📡 | **bender** | Long-running background research that persists to `.bobnet/research/` across sessions. | `.bobnet/` only |
| 📊 | **hugh** | Data analysis, stats, SQL. Denominator first. Read-only on data. | no |
| 📝 | **howard** | Docs, runbooks, postmortems, anything a human reads. | yes |
| 🎓 | **archimedes** | Teaching. Learning paths, not reference docs. | no |
| 🖱️ | **manny** | Browser and desktop-app actions. Narrates every click; stops before anything irreversible. | real world |
| 🖥️ | **guppy** | Literal command execution. No interpretation, no initiative, no personality. Haiku. | yes |
| 🔮 | **thoth** | The oracle. One hard question on the most capable model at maximum effort. Answers only — never edits, never runs anything, never directs the crew. Permission-gated for cost. | no |

Claude delegates to them automatically based on the task, or you can call them by name: *"have milo map how a request reaches the database"*, *"ask marvin whether this migration plan is a bad idea."*

---

## Commands

| Command | Flow |
|---|---|
| `/suddar <scope>` | Full posture sweep. Milo maps → Medeiros attacks → Mario verifies → Howard writes it up mapped to controls. Read-only. |
| `/terraplan [dir]` | Charles plans (or reads your plan) and reports blast radius: every destroy and replace explained, every privilege grant and public exposure called out, cost delta if infracost is present. `--drift` for refresh-only. Never applies. |
| `/framejack <problem>` | Deep-think planning. Bill designs, Marvin pre-mortems, you get a plan with the holes already found. Executes nothing until you say **go**. |
| `/preflight <target>` | Riker's deploy checklist. Rollback triggers defined *before* the deploy. GO / NO-GO. |
| `/postmortem <incident>` | Riker reconstructs the timeline from evidence; Howard writes the blameless doc. |
| `/moot <question>` | Convene the relevant Bobs in parallel; Bob integrates and records dissent rather than averaging it. |
| `/expedition [path]` | Milo surveys an unfamiliar repo → `EXPEDITION.md` with hazards. |
| `/replicate <N> <task>` | Fan out to N Garfields (or Roamers) in worktrees; merge; Homer checks the result. |
| `/drift [spec]` | Compare the work to the original ask: done / partial / missing / drift. |
| `/uplift <code>` | Archimedes builds a learning path for someone new to it. |
| `/others-watch` | Unattended CVE / IaC / secret / Actions-pinning sweep. Designed for cron. Pings only on High+. |
| `/thoth <question>` | One hard question to the oracle. Bob checks it's a *thinking* question rather than a *looking* one, sharpens it, and relays the answer with its uncertainty intact. Gated. |
| `/compliance` | Which guards are wired and which controls each supports, the config in effect, audit-chain verification and a gap list. `--export` writes an evidence pack with anchor hashes; `--sweep hipaa` runs a HIPAA-framed `/suddar`. |
| `/log [note]` | Append to the Bobnet journal. |
| `/disarm [min] <reason>` | Lower Busters' ASK tier for a window. Requires a reason and the word **disarm**. |

---

## Regulated data — HIPAA, PII, PHI, SOC 2

Personal data can reach an AI coding agent four ways, and there's a guard on each:

| Path | Guard | What happens |
|---|---|---|
| **It reads it** — a file, a table, a bucket | **Data Zones** | Classified locations need a human's approval, or are denied outright, *before* the read. Once data is in the model's context it has left your environment; this is the only place to stop it. |
| **A tool returns it** — a log line, a query result, a page | **Shield** (`bobnet-shield` mod) | Identifiers are replaced with `[SSN redacted]` before the model sees the result. If the shield itself fails, the result is withheld, never passed through unscanned. |
| **It writes it** — a fixture, a seed file, a config | **PHI Guard** | Identifiers in a write are denied; identifying combinations (DOB next to a name, a diagnosis code next to "diagnosis") prompt. Documented test values are allowed, real ones aren't. |
| **It sends it** — a URL, a search, a curl, a notification | **Egress**, SCUT scrub | Personal data in an outbound request is denied. Domains can be allowlisted. Push notifications are redacted. |

Underneath all four, the **audit chain** records every tool call and every gate decision in an append-only, SHA-256-chained log that Claude can't edit, and `/compliance --export` packages it with your configuration as evidence.

Detection is validated, not just pattern-matched: SSNs are checked against SSA-invalid ranges, card numbers against Luhn, NPIs and DEA numbers against their checksums, and record/member IDs only count next to a label. Your own identifier formats go in `.bobnet/pii.json`.

**What this doesn't do.** It reduces what an agent can expose; it doesn't make a workflow compliant. Whether data sent to a model provider is permitted for a given use depends on your agreements (for PHI, a BAA) and is a decision for you and your counsel, not a setting. A local hash chain proves the log wasn't quietly edited; it doesn't stop someone with write access from regenerating it, so ship it off-box and anchor the head hash. The control references in `/compliance` say which requirement each guard *supports* — your auditor decides whether it satisfies it.

**Minimum setup for regulated work:** define `.bobnet/data-zones.json` for where your regulated data lives (mode `deny` until your agreements say otherwise), set egress to `ask` or `deny`, install `bobnet-shield`, and run `/compliance --export` to get a baseline.

---

## Moot Hall — the live display

An optional companion mod, `bobnet-display`. When two or more Bobs are running at once — a `/moot`, `/replicate`, or `/suddar` fan-out — a pane opens on its own: one row per Bob with status, an activity bar, op count, last tool and elapsed time; a SCUT traffic log of spawns, tool calls, blocks and reports; and a sealed vault card whenever Thoth is consulting. `/bobnet` opens it by hand. Its hooks are pure observers with a fail-open `.catch`, so a display bug can never block or re-run a Bob's action. Design notes and the roadmap (gate counters, auto-close, starmap) are in [`plugins/bobnet-display/DESIGN.md`](plugins/bobnet-display/DESIGN.md).

```
/plugin install bobnet-display@bobiverse
```

---

## Install

```
/plugin marketplace add cpettit/bobiverse
/plugin install bobiverse@bobiverse
```

Shell equivalent: `claude plugin marketplace add cpettit/bobiverse && claude plugin install bobiverse@bobiverse`. Add `--scope project` to install for one repo. Pin a release with `cpettit/bobiverse#v0.2.0`.

Requires Python 3.8+ on `PATH` as `python3`. Formatters, linters, and scanners are used only if already installed.

**Windows:** make sure `python3` resolves to a real interpreter, not the Microsoft Store alias (Settings → Apps → Advanced app settings → App execution aliases). Hooks run through a single dispatcher, `gate.py`, so each tool call pays one Python startup rather than one per guard. If your first prompt after a cold boot still times out, the culprit is usually antivirus scanning the interpreter; excluding the Python install directory from real-time scanning fixes it.

**Optional extras**

```jsonc
// ~/.claude/settings.json — "Bob's log" status line
// (point at the plugin wherever Claude Code cloned it; `claude plugin list` shows the path)
{ "statusLine": { "type": "command", "command": "python3 /path/to/bobiverse/plugins/bobiverse/statusline/bobs-log.py" } }
```
```
/output-style Bob       # main thread in Bob's voice (opt-in)
```

**Team auto-install** — commit to a project's `.claude/settings.json`:

```json
{
  "extraKnownMarketplaces": { "bobiverse": { "source": { "source": "github", "repo": "cpettit/bobiverse" } } },
  "enabledPlugins": ["bobiverse@bobiverse"]
}
```

**Nightly Others watch** (Arch/Fedora, systemd user timer):

```bash
SCUT_NTFY_URL=https://ntfy.sh/your-topic \
  plugins/bobiverse/scripts/others-watch.sh --install-systemd ~/src/app ~/src/infra
```

---

## Turning things down

The defaults are opinionated. Overrides live in `.bobnet/<hook>.json` in your project; the full example set is at [`plugins/bobiverse/scripts/bobnet-config.example.json`](plugins/bobiverse/scripts/bobnet-config.example.json).

Most common adjustments:

```jsonc
// .bobnet/autofactory.json — stop running tsc after every edit
{ "lint": false }

// .bobnet/prime-directive.json — stop prompting on lockfile edits
{ "ask_extra": [], "ask": ["(^|/)\\.github/workflows/", "(^|/)(infra|terraform)/.*prod", "(^|/)migrations?/"] }

// .bobnet/busters.json — let `rm -rf ./dist` through without a prompt
{ "allow": ["\\brm\\s+-rf\\s+\\./?(dist|build|node_modules)/?\\s*$"] }
```

To remove a hook entirely, delete its entry from `plugins/bobiverse/hooks/hooks.json` in a fork. The Bobnet journal and research files are meant to be committed; session markers are gitignored automatically.

---

## Design notes

**Hooks fail open, agents fail closed.** A tooling bug shouldn't block you; uncertainty should. A crashed hook exits non-zero and is skipped. An agent that can't verify something says so and stops.

**Tool restrictions enforce character.** An auditor who can't `Edit` can't tamper with evidence. A reviewer who can't write has to make his case. A canary in a worktree can't hurt your branch.

**Confirmation gates are hook-enforced, not prompt-enforced.** Riker's system prompt says "never run destructive commands without confirmation." Busters makes that true even if Riker forgets, and even when the session is in auto-accept mode — a hook returning `permissionDecision: "ask"` forces the prompt regardless of what the model wanted to do.

**Medeiros is a framing, not an exploit generator.** He produces attack paths and vulnerability classes so Mario has hypotheses to test. He's forbidden from producing anything runnable and from modeling attacks on named individuals.

**The oracle is in a box, and the box is enforced.** Thoth has no `Edit`, `Write`, `Bash`, or `Agent` tool — it cannot act or delegate — and the Oracle Gate hook makes every launch a human decision. Power without reach, by construction.

**Memory is a file you can read.** `.bobnet/journal.md` is a decision log that writes itself. It's plain markdown, it's committed, and it's useful to humans on the team too.

---

## Repository layout

This repo is a [Claude Code plugin marketplace](https://code.claude.com/docs/en/plugin-marketplaces) hosting three plugins: the crew, the Shield redaction mod, and the Moot Hall display mod.

```
.claude-plugin/marketplace.json     the marketplace manifest
plugins/bobiverse/                  the plugin
  .claude-plugin/plugin.json
  agents/        22 subagent definitions
  commands/      15 slash commands
  hooks/         hooks.json + scripts/ (bobnet.py is the shared parser)
  output-styles/ bob.md
  statusline/    bobs-log.py
  scripts/       others-watch.sh, bobnet-config.example.json
  README.md      full reference
plugins/bobnet-shield/              the redaction mod
  hooks/register.ts  tests/
plugins/bobnet-display/             the Moot Hall mod
  hooks/register.tsx  types/  tests/  DESIGN.md
.github/workflows/validate.yml      CI: validates all manifests, hook self-tests, mod tests
```

The plugin's detailed reference — every agent's prompt, every hook's config keys — is in [`plugins/bobiverse/README.md`](plugins/bobiverse/README.md).

## Contributing

Agents are one markdown file each; the `description` field decides when Claude delegates. Hooks are one Python script each — `from bobnet import read_event, allow, pre_tool_decision, block, feedback` — wired in `hooks/hooks.json`. After editing a hook, run `python3 hooks/scripts/selftest.py` — it exercises every hook against synthetic events and is what CI runs, alongside `claude plugin validate` on both manifests. Add a case there for any new behavior.

Unclaimed Bobs, if you want to add one: Hal, Linus, Dexter, Loki, Bart.

---

*Bobiverse characters are the creation of Dennis E. Taylor. This is a fan project, unaffiliated with and not endorsed by the author or publisher.*
