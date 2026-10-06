#!/usr/bin/env python3
"""
bobs-log.py — Claude Code status line in "Bob's log" style.

  ⬢ bobtest · ⎇ main* +2 · ctx 34% · $0.42 · Busters ✓ · log 2h ago

Install (settings.json):
  "statusLine": { "type": "command", "command": "python3 /path/to/bobiverse/statusline/bobs-log.py" }

Reads Claude Code's status JSON on stdin. Every field is optional; the line
degrades gracefully. Colors via ANSI; set BOBS_LOG_NOCOLOR=1 to disable.
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

try:
    d = json.loads(sys.stdin.read() or "{}")
except Exception:
    d = {}

NOCOLOR = os.environ.get("BOBS_LOG_NOCOLOR") == "1"


def c(code, s):
    return s if NOCOLOR else f"\033[{code}m{s}\033[0m"


DIM, BOLD, GREEN, YEL, RED, CYAN, MAG = "2", "1", "32", "33", "31", "36", "35"

ws = d.get("workspace") or {}
cwd = ws.get("current_dir") or d.get("cwd") or os.getcwd()
root = Path(cwd)
parts = []

# Project
parts.append(c(BOLD, f"⬢ {root.name}"))

# Git
git = d.get("git") or {}
branch = git.get("branch")
dirty = None
if not branch:
    try:
        branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd, capture_output=True, text=True, timeout=1).stdout.strip() or None
        st = subprocess.run(["git", "status", "--porcelain"], cwd=cwd, capture_output=True, text=True, timeout=1).stdout
        dirty = len([l for l in st.splitlines() if l.strip()])
    except Exception:
        pass
else:
    s = git.get("status")
    if isinstance(s, dict):
        dirty = sum(v for v in s.values() if isinstance(v, int)) or None
if branch:
    b = f"⎇ {branch}"
    if dirty:
        b += c(YEL, f"* +{dirty}")
    parts.append(b)
if d.get("worktree"):
    parts.append(c(MAG, "⑂ worktree"))

# Model
m = d.get("model") or {}
name = m.get("display_name") or m.get("id") or ""
if name:
    parts.append(c(DIM, re.sub(r"^Claude\s+", "", name)))

# Context
cw = d.get("context_window") or {}
used = cw.get("used_percentage")
if used is None and cw.get("window_size") and cw.get("current_usage"):
    cu = cw["current_usage"]
    tot = cu if isinstance(cu, (int, float)) else sum(v for v in cu.values() if isinstance(v, (int, float)))
    used = 100 * tot / cw["window_size"]
if used is not None:
    col = GREEN if used < 60 else YEL if used < 85 else RED
    parts.append(c(col, f"ctx {int(used)}%"))

# Cost
cost = (d.get("cost") or {}).get("total_cost_usd")
if cost is not None:
    parts.append(c(DIM, f"${cost:.2f}"))

# Bobnet state
bn = Path(os.environ.get("BOBNET_DIR") or root / ".bobnet")
dis = bn / "busters.disarmed"
armed = "Busters ✓"
try:
    if dis.exists():
        exp = float(dis.read_text().strip())
        if time.time() < exp:
            armed = c(RED, f"Busters OFF {int((exp - time.time()) / 60)}m")
        else:
            armed = "Busters ✓"
except Exception:
    pass
parts.append(c(GREEN, armed) if "✓" in armed else armed)

journal = bn / "journal.md"
if journal.exists():
    age = time.time() - journal.stat().st_mtime
    if age < 3600:
        s = f"{int(age / 60)}m"
    elif age < 86400:
        s = f"{int(age / 3600)}h"
    else:
        s = f"{int(age / 86400)}d"
    parts.append(c(DIM, f"log {s} ago"))

research = bn / "research"
if research.exists():
    n = sum(1 for f in research.glob("*.md") if re.search(r"Status:\s*in-progress", f.read_text(errors="ignore")[:400]))
    if n:
        parts.append(c(CYAN, f"Bender ×{n}"))

print(" · ".join(parts))
