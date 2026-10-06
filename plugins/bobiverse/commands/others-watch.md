---
description: "Others watch — scheduled dependency/CVE/secret sweep. Mario scans, writes findings to .bobnet/others-watch/, and pings via SCUT only if something is High or Critical. Designed to run unattended (claude -p '/others-watch')."
argument-hint: "[path(s) to scan — default: current repo] [--fail-on high|critical]"
allowed-tools: Agent, Read, Glob, Grep, Bash, Write
---

Others watch — scanning for what's eating the system while nobody's looking. Target: **$ARGUMENTS**

This command is designed to run **unattended** (from a scheduled task or cron via `claude -p "/others-watch"`). Make no decisions that need a human; make no changes; write everything down.

## 1. Inventory (you, fast)
Detect manifests present: `package.json`/lockfiles, `requirements*.txt`/`pyproject.toml`/`poetry.lock`, `go.mod`, `Cargo.toml`, `Gemfile.lock`, `composer.json`, `Dockerfile`(s), `*.tf`, GitHub Actions workflows. List them.

## 2. Scan (spawn `mario`)
Mario runs whatever scanners are installed — he **does not install anything**:
- Dependencies: `npm audit --json`, `pip-audit`, `osv-scanner`, `trivy fs`, `grype`, `cargo audit`, `govulncheck`, `bundle audit` — whichever apply and exist.
- Containers/IaC: `trivy config`, `checkov`, `tfsec`, `hadolint` if present.
- Secrets: `gitleaks detect` or `trufflehog filesystem` if present; otherwise his regex sweep.
- GitHub Actions: unpinned action versions (`uses: foo/bar@main` or `@v1` instead of a SHA), `pull_request_target` with checkout of PR head, secrets passed to forks.
- Staleness: lockfile age, any dependency more than 2 major versions behind.

He reports in his standard format, with severity and evidence, plus a line for every scanner he *couldn't* run and why.

## 3. Record (you)
Write `.bobnet/others-watch/<YYYY-MM-DD>.md`:
```markdown
# Others watch — <date> — <repo>
Scanners run: … · Not available: …
Critical: n · High: n · Medium: n · Low: n

## New since last run
<diff against the most recent previous file in the dir, by finding title — or "first run">

## Findings
<Mario's table>

## Resolved since last run
<titles present last time, absent now>
```
Append one line to `.bobnet/journal.md`: `## <timestamp> — Others watch: C<n> H<n> M<n> L<n> (<new> new)`.

## 4. Signal
- If any Critical or High (or whatever `--fail-on` says): print `OTHERS-WATCH: ALERT` as the first line of your final output, with the top finding on the second line. If SCUT is configured (`SCUT_NTFY_URL`/`SCUT_WEBHOOK_URL`), send it:
  ```bash
  python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/scut.py" notification <<< '{"message":"Others watch: <n> critical/high in <repo>. See .bobnet/others-watch/<date>.md","notification_type":"others-watch"}'
  ```
- Otherwise, print `OTHERS-WATCH: CLEAR` and the counts. No ping — silence means safe.

Exit by stopping. Do not fix anything. The dead systems are dead because nobody looked, not because nobody acted.
