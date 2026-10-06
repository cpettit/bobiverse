#!/usr/bin/env python3
"""
jeeves.py — SessionStart(startup|resume). The VR butler.

Prints a situational brief to stdout, which Claude Code adds to context:
  - repo, branch, dirty files, recent commits
  - last Bobnet journal entries + any in-progress Bender research
  - open TODO/FIXME count
  - which hooks are armed
Keep it short; this is a brief, not a report.
"""
import os
import re
import subprocess
import time
from pathlib import Path
from bobnet import read_event, context, bobnet_dir

ev = read_event()
cwd = ev.cwd
root = os.environ.get("CLAUDE_PROJECT_DIR") or cwd


def sh(cmd, timeout=5):
    try:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, shell=isinstance(cmd, str)).stdout.strip()
    except Exception:
        return ""


lines = ["JEEVES — situational brief", ""]

# Git
if sh("git rev-parse --is-inside-work-tree") == "true":
    branch = sh("git rev-parse --abbrev-ref HEAD")
    dirty = sh("git status --porcelain")
    ndirty = len([l for l in dirty.splitlines() if l.strip()])
    ahead = sh("git rev-list --count @{u}..HEAD 2>/dev/null") or "?"
    behind = sh("git rev-list --count HEAD..@{u} 2>/dev/null") or "?"
    lines.append(f"Repo: {Path(root).name} · branch `{branch}` · {ndirty} uncommitted · ahead {ahead} / behind {behind}")
    recent = sh("git log --oneline -5 --no-decorate")
    if recent:
        lines.append("Recent commits:")
        lines += [f"  {l}" for l in recent.splitlines()]
    wt = sh("git worktree list")
    if wt and len(wt.splitlines()) > 1:
        lines.append(f"Worktrees active: {len(wt.splitlines()) - 1} (canaries/Thor pairs may be running)")
else:
    lines.append(f"Directory: {root} (not a git repo)")

# Bobnet
bn = bobnet_dir(ev)
journal = bn / "journal.md"
if journal.exists():
    entries = [l for l in journal.read_text(errors="ignore").splitlines() if l.startswith("## ")]
    if entries:
        lines.append("")
        lines.append(f"Bobnet journal — last {min(3, len(entries))} of {len(entries)} entries:")
        for e in entries[-3:]:
            lines.append(f"  {e[3:]}")
research = bn / "research"
if research.exists():
    inprog = []
    for f in research.glob("*.md"):
        head = f.read_text(errors="ignore")[:400]
        if re.search(r"Status:\s*in-progress", head):
            inprog.append(f.stem)
    if inprog:
        lines.append(f"Bender research in progress: {', '.join(inprog)}  (see .bobnet/research/)")
mission = bn / f"mission-{ev.session}.md"
if ev.source == "resume" and mission.exists():
    lines.append("")
    lines.append("Original mission for this session:")
    lines.append("  " + mission.read_text(errors="ignore").strip().replace("\n", "\n  ")[:600])

# TODOs
todo = sh("git grep -c -E 'TODO|FIXME|XXX|HACK' -- ':!*.lock' ':!*.min.*' 2>/dev/null | awk -F: '{s+=$2} END {print s+0}'")
if todo and todo != "0":
    lines.append("")
    lines.append(f"Open TODO/FIXME/HACK markers in tree: {todo}")

# Hooks armed
armed = ["Busters (destructive-command gate)", "SUDDAR (secret scan)", "Prime Directive (protected paths)"]
if (bn / "busters.disarmed").exists():
    try:
        exp = float((bn / "busters.disarmed").read_text().strip())
        if time.time() < exp:
            armed[0] = f"Busters DISARMED for {int((exp - time.time()) / 60)} more min"
    except Exception:
        pass
lines.append("")
lines.append("Armed: " + " · ".join(armed))
lines.append("Crew: /moot /suddar /framejack /expedition /preflight /postmortem /drift /uplift /replicate /log /disarm /others-watch — `/agents` lists the Bobs.")

context("\n".join(lines))
