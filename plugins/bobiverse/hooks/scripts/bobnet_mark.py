#!/usr/bin/env python3
"""
bobnet_mark.py — PostToolUse(Write|Edit|MultiEdit|Bash).
Drops session markers the Stop hook relies on:
  dirty  — this session changed something (any Edit/Write, or a Bash command
           that isn't obviously read-only)
  logged — the Bobnet journal was written this session
"""
import re
from bobnet import read_event, allow, marker, touch

ev = read_event()

if ev.tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
    touch(marker(ev, "dirty"))
    if re.search(r"(^|/)\.bobnet/journal\.md$", ev.file_path or ""):
        touch(marker(ev, "logged"))
    allow()

if ev.tool == "Bash":
    cmd = ev.command.strip()
    READ_ONLY = r"^(ls|cat|head|tail|less|grep|rg|find|fd|git\s+(status|log|diff|show|branch|blame|grep|worktree\s+list)|pwd|echo|which|type|wc|tree|du|df|ps|env|printenv|stat|file|jq|yq|awk|sed\s+-n|sort|uniq|cut|tr|date|whoami|uname|python3?\s+-c\s+['\"]?print|npm\s+(ls|list|view|outdated)|pip\s+(list|show|freeze)|cargo\s+(tree|metadata)|go\s+(list|version)|terraform\s+(show|plan|validate|fmt\s+-check)|kubectl\s+(get|describe|logs|top))\b"
    if cmd and not re.match(READ_ONLY, cmd) and not re.search(r"\.bobnet/journal\.md", cmd):
        touch(marker(ev, "dirty"))
    if re.search(r">>?\s*\S*\.bobnet/journal\.md", cmd):
        touch(marker(ev, "logged"))
    allow()

allow()
