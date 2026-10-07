# Bobiverse — a crew for Claude Code

A Claude Code plugin modeled on Dennis E. Taylor's *Bobiverse*. Twenty-one agents, thirteen commands, nine hooks, a status line, and an output style. Every Bob's personality maps onto a real role in a dev/sec/ops workflow, and the hooks turn the crew's safety rules from polite requests into enforced ones.

```
bobiverse/
├── .claude-plugin/plugin.json
├── agents/          21 subagents
├── commands/        13 slash commands
├── hooks/           hooks.json + 9 Python hook scripts (stdlib only)
├── output-styles/   bob.md — main thread in Bob's voice
├── statusline/      bobs-log.py
└── scripts/         others-watch.sh (scheduler), bobnet-config.example.json
```

## Install

```bash
# Try it on one project
claude --plugin-dir /path/to/bobiverse

# Validate the manifest
claude plugin validate /path/to/bobiverse
```

To make it permanent, add it to a marketplace or copy `agents/` and `commands/` into `~/.claude/` (the hooks need the plugin form so `${CLAUDE_PLUGIN_ROOT}` resolves — or hand-edit the paths in `hooks/hooks.json` into your `settings.json`).

Optional extras:
```jsonc
// ~/.claude/settings.json
{
  "statusLine": { "type": "command", "command": "python3 /path/to/bobiverse/statusline/bobs-log.py" }
}
```
```
/output-style Bob        # main thread talks like Bob-1
```

Requirements: Python 3.8+ on PATH (hooks are stdlib-only). Formatters/linters/scanners are used only if already installed — nothing is ever auto-installed.

## The crew

| Agent | Character | Role | Writes? |
|---|---|---|---|
| `bob` | The original | Orchestrator / triage / delegation | yes |
| `bill` | Epsilon Eridani R&D | Architecture, ADRs, trade-offs | no |
| `riker` | Took command at Earth | Incidents, deploys, rollback, prod | yes* |
| `will` | Riker, post-war | Routine release management, changelogs | yes* |
| `mario` | Hunted the Others | Security recon, audits, forensics, control mapping | no |
| `medeiros` | The Brazilian probe (under truce) | Red-team threat modeling, attack trees | no |
| `garfield` | Bill's lab partner | Implementation | yes |
| `neil` / `herschel` | The Thor crew | Paired implementers: minimal vs. robust, same spec, separate worktrees | yes (worktree) |
| `sandbox-bob` | The air-gapped Bob for dangerous data | Canary — tries risky changes in a disposable worktree | yes (worktree) |
| `charles` | Leads Reclamation, terraforming Sol | Cloud infrastructure & IaC — Terraform/OpenTofu, Azure, AWS, IAM/Entra, drift; reads plans as blast-radius reports; never applies | HCL yes; apply never |
| `roamer` | Grunt-work drones | Bulk mechanical edits, Haiku, parallel | yes |
| `homer` | The clown who held the line | Testing, QA, chaos engineering | yes |
| `marvin` | The Paranoid Android | Pre-mortems, critical review | no |
| `milo` | The scout | Codebase exploration & mapping | no |
| `bender` | Lost in Heaven's River | Long-running background research → `.bobnet/research/` | `.bobnet/` only |
| `hugh` | Joined the Skippies | Data analysis, stats, SQL — read-only on data | no |
| `howard` | Ran Vulcan, became human-adjacent | Docs, runbooks, human-facing comms | yes |
| `archimedes` | Bob's Deltan protégé | Teaching, onboarding, learning paths | no |
| `manny` | Howard's android | Browser / desktop-app actions; stops before anything irreversible | real world |
| `guppy` | The ship AI | Literal, exact command execution, Haiku | yes |

\* with explicit confirmation before anything destructive or production-affecting — and Busters enforces it.

## Commands

| Command | What happens |
|---|---|
| `/moot <question>` | Bob frames it, spawns the relevant Bobs in parallel, integrates, records dissent |
| `/suddar <scope>` | Full posture sweep: Milo maps → Medeiros attacks → Mario verifies → Howard writes it up mapped to SOC 2 / CIS / NIST |
| `/terraplan [dir]` | Charles turns a Terraform plan into a blast-radius report — destroys/replaces explained, privilege grants and exposure flagged, cost delta; `--drift` for refresh-only; never applies |
| `/framejack <problem>` | Deep-think planning. Bill designs, Marvin pre-mortems, you get a plan. Executes nothing until you say **go** |
| `/replicate <N> <task>` | Fan out to N Garfields (or `--roamers`) in worktrees, merge, Homer checks the result |
| `/expedition [path]` | Milo surveys an unfamiliar repo → `EXPEDITION.md` with hazards |
| `/preflight <target>` | Riker's deploy checklist with rollback triggers defined *before* the deploy. GO / NO-GO |
| `/postmortem <incident>` | Riker reconstructs the timeline from evidence, Howard writes the blameless doc |
| `/drift [spec]` | Compare the work to the original ask. Done / partial / missing / drift |
| `/uplift <code>` | Archimedes builds a learning path for someone new to it |
| `/log [note]` | Append to the Bobnet journal |
| `/disarm [min] <reason>` | Lower Busters' ASK tier for a window. Requires a reason and the word **disarm** |
| `/others-watch` | Unattended CVE / IaC / secret / Actions-pinning sweep → `.bobnet/others-watch/<date>.md`, pings on High+ |

## Hooks — where the rules become real

| Hook | Event | Behavior |
|---|---|---|
| **Busters** | `PreToolUse` Bash | Three tiers. **KILL** (`rm -rf /`, force-push to main/prod, `mkfs`, `dd` to a device, fork bomb) → denied, cannot be disarmed. **ASK** (recursive/forced `rm`, `DROP`/`TRUNCATE`, `DELETE` without `WHERE`, `terraform apply`/`destroy`/state surgery/`import`, `kubectl delete`, docker prune, cloud `delete`, publish, anything prod-flavored, and privilege grants — `az role assignment create`, `aws iam attach-*-policy`, `create-access-key`, cluster-admin bindings) → forces a permission prompt even in auto-accept mode. Everything else → allowed. |
| **SUDDAR** | `PreToolUse` Write/Edit, `git commit` | Denies writes containing credential-shaped strings (AWS/GitHub/Slack/Stripe/OpenAI keys, private key blocks, JWTs, DB URLs with passwords, generic `password=`/`api_key=`) and writes to secret-bearing paths (`.env`, `*.pem`, `id_rsa`, kubeconfig, tfstate…). Tolerates placeholders. Runs `gitleaks`/`trufflehog` on staged changes at commit if installed. |
| **Prime Directive** | `PreToolUse` Write/Edit/Bash | Protected zones → permission prompt: CI workflows, prod infra, IAM/RBAC, migrations, Dockerfiles, lockfiles, CODEOWNERS, the hooks' own config. `.git/config` and friends → denied outright. |
| **Autofactory** | `PostToolUse` Write/Edit | Runs the formatter already installed for the file type (ruff/black, prettier, gofmt, rustfmt, shfmt, terraform fmt). Runs the linter **only when the project has configured it** (`ruff.toml`/`[tool.ruff]`, eslint config, `.yamllint`); compile-style checks with no rule set to argue about (go vet, cargo check, terraform validate, shellcheck, hadolint, tsc) always run. Failures go straight back to Claude as feedback. |
| **Replicative drift** | `SubagentStop` | Blocks a subagent's first stop and makes it append a `DRIFT CHECK` — requirements addressed / missed / out-of-scope work — so Bob integrates correctly. |
| **Jeeves** | `SessionStart` | Situational brief: branch, dirty files, recent commits, worktrees, last 3 journal entries, Bender research in progress, TODO count, which hooks are armed. |
| **Mission brief** | `UserPromptSubmit` + `SessionStart(compact)` | Saves the first prompt of the session verbatim; re-injects it after context compaction so the original success criteria survive the summary. |
| **Bobnet log** | `Stop` | If the session changed anything and no journal entry was written, blocks once and asks for a 10-line "Bob's log" entry in `.bobnet/journal.md`. Never nags twice. |
| **SCUT** | `Notification`, `Stop` | Pushes to ntfy / Slack / Discord webhook when Claude is waiting on you or a long session finishes. Silent unless `SCUT_NTFY_URL` or `SCUT_WEBHOOK_URL` is set. |

Every hook is a standalone Python script in `hooks/scripts/`; `bobnet.py` is the shared parser so field-name changes in Claude Code's hook JSON only need fixing in one place. All hooks fail **open** on their own errors (a broken hook never blocks work) except where the whole point is to block.

### `.bobnet/` — the plugin's state directory

Created in the project root on first use.

```
.bobnet/
├── journal.md            ← commit this. Cross-session memory.
├── research/<slug>.md    ← Bender's findings. Commit these too.
├── others-watch/<date>.md
├── busters.json          ← optional overrides (see scripts/bobnet-config.example.json)
├── prime-directive.json
├── suddar.json
├── autofactory.json
├── scut.json
├── .gitignore            ← auto-written; ignores the session markers below
├── mission-<session>.md
├── busters.disarmed
└── *.marker
```

Set `BOBNET_DIR` to put it somewhere else.

## Scheduling the Others watch

```bash
# cron
17 3 * * *  /path/to/bobiverse/scripts/others-watch.sh ~/src/app ~/src/infra

# systemd user timer (Arch/Fedora)
SCUT_NTFY_URL=https://ntfy.sh/your-topic \
  /path/to/bobiverse/scripts/others-watch.sh --install-systemd ~/src/app ~/src/infra
```

The script runs `claude -p "/others-watch"` per repo with `--allowedTools` restricted to read-only tools, the known scanners, and writes under `.bobnet/`. Exit code 2 means ALERT. Scanners are used only if installed: `osv-scanner`, `trivy`, `grype`, `pip-audit`, `npm audit`, `cargo audit`, `govulncheck`, `checkov`, `tfsec`, `hadolint`, `gitleaks`, `trufflehog`.

## Design notes

**Tool restrictions enforce character.** Read-only Bobs (Bill, Mario, Marvin, Milo, Medeiros, Hugh, Archimedes) can't `Edit` or `Write`. A security auditor who can't remediate can't tamper with evidence; a reviewer who can't edit has to make his case in words.

**Worktree isolation enforces independence.** Sandbox-Bob, Neil, and Herschel each run in their own worktree. The canary can't hurt your branch; the Thor pair can't peek at each other's answer.

**Hooks fail open, agents fail closed.** A crashed hook script exits non-zero and Claude Code skips it — work continues. An agent that can't verify something says so and stops. That's the right asymmetry: tooling bugs shouldn't block you; uncertainty should.

**Medeiros is a framing, not an exploit generator.** He produces attack trees and abuse cases so Mario has hypotheses to test. He's forbidden from producing anything runnable against a real target, and he won't model attacks on named individuals.

**Guppy and Roamers run on Haiku.** Literal execution and bulk edits need fast and non-improvisational, not big. Change `model:` if your account lacks it.

**The Bobnet journal is meant to be committed.** It's the crew's shared memory and it's useful to humans too — a decision log that writes itself. Secrets never go in it (SUDDAR will stop them anyway).

## Extending

Each agent is one markdown file: frontmatter (`name`, `description`, `model`, `tools`, optionally `isolation: worktree` or `background: true`) plus a system prompt. The `description` decides when Claude delegates automatically — tune it to make a Bob fire more or less often.

Hooks: add a script to `hooks/scripts/`, import `from bobnet import read_event, allow, pre_tool_decision, block, feedback, context`, wire it in `hooks/hooks.json`. Test with `printf '{"tool_name":"Bash","tool_input":{"command":"..."}}' | python3 hooks/scripts/yours.py`.

Still unclaimed in the books, if you want more: **Hal** (the hidden Bob), **Linus**, **Dexter**, **Loki**, **Bart**, the **Pav**, the **Quinlans**.

---
*Bobiverse characters are the creation of Dennis E. Taylor. This is a fan project; nothing here is affiliated with or endorsed by the author or publisher.*
