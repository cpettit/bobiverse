---
description: "Disarm Busters for a window (default 15 min) so a planned batch of destructive-but-intended commands doesn't prompt one by one. KILL-tier commands stay blocked. Use sparingly; say why."
argument-hint: "[minutes, default 15] <reason — required>"
allowed-tools: Bash, Read
---

Disarm request: **$ARGUMENTS**

Parse: optional leading integer = minutes (default 15, max 60); the rest is the reason. **If there is no reason, refuse** — "Busters stays armed until you tell me why" — and stop.

Then:
1. Echo back exactly what disarming means: the ASK tier (recursive deletes, force pushes to non-protected branches, DROP/TRUNCATE, terraform destroy, kubectl delete, docker prune, cloud `delete` commands, `sudo` with dangerous verbs, anything prod-flavored) will run **without a confirmation prompt** for N minutes. The KILL tier (`rm -rf /`, force-push to main/master/prod, mkfs, dd to a device, fork bombs) is still denied no matter what.
2. Ask the human to confirm with the word **disarm**. Wait for it. Do not proceed on anything else.
3. On confirmation, write the expiry:
   ```bash
   mkdir -p "${CLAUDE_PROJECT_DIR:-.}/.bobnet" && python3 -c "import time; print(time.time() + $MINUTES*60)" > "${CLAUDE_PROJECT_DIR:-.}/.bobnet/busters.disarmed"
   ```
4. Log it to `.bobnet/journal.md`: `## <timestamp> — Busters disarmed <N> min — <reason>`.
5. Confirm: "Busters disarmed until <HH:MM>. Reason logged. KILL tier still active. Re-arm early with `rm .bobnet/busters.disarmed`."

Riker's note, in his voice, one line: something to the effect that the gate exists because of the time someone skipped it.
