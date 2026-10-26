#!/usr/bin/env python3
"""
mission.py — UserPromptSubmit (save) and SessionStart(compact) (restore).
The mission brief — anti-Gamers measure.

The Gamers were the Bobs who wandered into VR and never came back to the job.
Long sessions do the same: after a context compaction the original ask is a
blurry summary and the session drifts. This hook:

  save    — on the FIRST user prompt of a session, writes it verbatim to
            .bobnet/mission-<session>.md (and drops the session start marker
            used by SCUT timing).
  restore — after compaction, re-injects that original prompt into context,
            labeled, so the success criteria survive the summary.
"""

import os
import re
import sys
from bobnet import (
    read_event,
    allow,
    context,
    bobnet_dir,
    ensure_bobnet,
    load_config,
    now,
    git_state,
    marker,
)

# Prompts that are not the human's ask: harness notifications and subagent hand-backs.
SKIP_PREFIXES = (
    "<agent-message",
    "<task-notification",
    "[SYSTEM NOTIFICATION",
    "<system-reminder",
    "<local-command",
)
# Commands that never carry a mission: Claude Code's local commands plus the
# Bobnet housekeeping commands.
NOT_A_MISSION = {
    "add-dir", "agents", "bug", "clear", "compact", "config", "context", "cost",
    "doctor", "effort", "exit", "export", "fast", "feedback", "help", "hooks", "ide",
    "login", "logout", "mcp", "memory", "model", "output-style", "permissions",
    "plugin", "plugins", "quit", "release-notes", "rename", "resume", "status",
    "statusline", "terminal-setup", "theme", "upgrade", "usage", "vim",
    "disarm", "log",
}
# A command name has no second slash, so "/var/log/app.log is broken" is a prompt.
SLASH_COMMAND = re.compile(r"^/([A-Za-z][\w.-]*(?::[\w.-]+)*)(?:\s+(.*))?$", re.S)
MIN_LENGTH = 12  # so the mission isn't "hi" or "go ahead"


def mission_text(prompt: str) -> str:
    """The text worth saving as the mission, or "" if this prompt isn't one."""
    p = prompt.strip()
    if not p or p.startswith(SKIP_PREFIXES):
        return ""
    if p.startswith(("<command-message>", "<command-name>")):  # expanded slash-command form
        name = re.search(r"<command-name>/?([^<\s]+)</command-name>", p)
        args = re.search(r"<command-args>(.*?)</command-args>", p, re.S)
        name, args = (name.group(1) if name else ""), (args.group(1) if args else "")
    else:
        m = SLASH_COMMAND.match(p)
        if not m:
            return p if len(p) >= MIN_LENGTH else ""
        name, args = m.group(1), m.group(2) or ""
    if name.split(":")[-1] in NOT_A_MISSION or len(args.strip()) < MIN_LENGTH:
        return ""
    return f"/{name} {args.strip()}"


mode = sys.argv[1] if len(sys.argv) > 1 else "save"
ev = read_event()
bn = ensure_bobnet(ev)
mission = bn / f"mission-{ev.session}.md"
start = bn / f"start-{ev.session}.marker"

if mode == "save":
    if not start.exists():
        start.touch()
    # Baseline for bobnet_mark: git state before any tool runs this session.
    snapshot = marker(ev, "gitstate")
    if not snapshot.exists():
        state = git_state(ev)
        if state:
            try:
                snapshot.write_text(state, encoding="utf-8")
            except Exception:
                pass
    # Opt out entirely: .bobnet/mission.json {"enabled": false} or BOBNET_MISSION=0
    enabled = (
        load_config(ev, "mission", {"enabled": True}).get("enabled", True)
        and os.environ.get("BOBNET_MISSION", "1") != "0"
    )
    if enabled and not mission.exists():
        p = mission_text(ev.prompt)
        if p:
            # The prompt is saved to disk: redact personal data first, so a pasted
            # record doesn't become PHI at rest.
            try:
                from pii import redact

                p, hits = redact(p, load_config(ev, "pii", {}))
                note = f" · {len(hits)} personal-data item(s) redacted" if hits else ""
            except Exception:
                p, note = "(mission not saved: redaction unavailable)", ""
            if len(p) > 4000:
                p = p[:4000] + "\n[truncated]"
            mission.write_text(f"Recorded {now()}{note}\n\n{p}\n", encoding="utf-8")
    allow()

if mode == "restore":
    if ev.source == "compact" and mission.exists():
        text = mission.read_text(encoding="utf-8", errors="ignore").strip()
        context(
            "MISSION BRIEF (restored after context compaction — this is the original ask, verbatim):\n\n"
            f"{text}\n\n"
            "Re-anchor on this. If the work has drifted from it, say so and either steer back or "
            "confirm with the human that the drift is intended."
        )
    allow()

allow()
