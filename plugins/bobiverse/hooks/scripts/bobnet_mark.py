#!/usr/bin/env python3
"""
bobnet_mark.py — PostToolUse (all tools, via gate.py post).
Drops session markers the Stop hook relies on:
  dirty    — this session changed something: any Write/Edit, or a Bash command
             that changed git state or reaches beyond the machine
  logged   — the Bobnet journal was written this session
  agent.ID — a Bob was spawned; bobnet_log waits until it reports (drift.py
             drops agentdone.ID when it does)

What counts as a change for Bash:
  1. A remote-effect command anywhere in the line (terraform apply, kubectl,
     az, git push, a deploy script …). These change nothing locally but are
     exactly what the journal is for.
  2. Otherwise, git state before vs after: `git status --porcelain=v2 --branch`
     plus the mtime of every listed file, so commits, checkouts and re-edits of
     an already-modified file all count. Compared to a per-session snapshot.
  3. Outside a repo, or if git is slow or fails: each segment of the command
     is checked against a read-only list; anything else counts.
Reading, searching and running tests don't count, which was the bug: `cd x &&
cat y` and `git ls-files` used to mark the session dirty.
Blind spots: writes to gitignored files or outside the repo, when git works.
"""
from __future__ import annotations

import re
import time
from bobnet import read_event, allow, marker, touch, git_state, safe_id

ev = read_event()

if ev.tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
    touch(marker(ev, "dirty"))
    if re.search(r"(^|/)\.bobnet/journal\.md$", ev.file_path or ""):
        touch(marker(ev, "logged"))
    allow()

if ev.tool in ("Agent", "Task"):
    # Read the id from the structured result. Never search the report text: a
    # Bob whose report mentions "agentId: something" would leave a spawn that
    # never finishes, and the journal prompt would wait an hour.
    aid = ""
    if isinstance(ev.result, dict):
        aid = safe_id(ev.result.get("agentId") or ev.result.get("agent_id"))
    elif isinstance(ev.result, str):
        m = re.search(r'"agent_?id"\s*:\s*"([A-Za-z0-9_-]{6,})"', ev.result, re.I)
        aid = m.group(1) if m else ""
    if aid:
        touch(marker(ev, f"agent.{aid}"))
    allow()

if ev.tool != "Bash":
    allow()

cmd = ev.command.strip()
if re.search(r">>?\s*\S*\.bobnet/journal\.md", cmd):
    touch(marker(ev, "logged"))
dirty = marker(ev, "dirty")
if not cmd or dirty.exists():
    allow()  # already dirty: skip the git cost

# Global flags may sit between the tool and its verb: `terraform -chdir=x apply`, `git -C dir push`.
FLAGS = r"(\s+(-C|-c|-n|--namespace|--context|--kube-context|--kubeconfig|--git-dir|--work-tree)\s+\S+|\s+--?[\w-]+(=\S+)?)*"
REMOTE_EFFECT = re.compile(
    r"(^|[\s;&|(])("
    r"(terraform|tofu)" + FLAGS + r"\s+(apply|destroy|import|state\s+(rm|mv|push)|taint)"
    r"|az\s+(\S+\s+){1,3}(create|delete|update|set|assign|add|remove|deploy|start|stop|restart)"
    r"|aws\s+\S+\s+(create|delete|put|update|deploy|run|start|stop|terminate|invoke)"
    r"|aws\s+s3\s+(cp|mv|rm|sync)"
    r"|gcloud\s+.*\s(create|delete|update|deploy)"
    r"|kubectl" + FLAGS + r"\s+(apply|delete|patch|scale|rollout|create|replace|edit|label|annotate)"
    r"|helm" + FLAGS + r"\s+(install|upgrade|uninstall|rollback)"
    r"|docker\s+push|git" + FLAGS + r"\s+push|gh\s+workflow\s+run"
    r"|gh\s+(pr|issue)\s+(create|merge|close|edit|comment|review)|gh\s+release\s+(create|upload|delete|edit)"
    r"|(npm|yarn|pnpm|dotnet\s+nuget|cargo|twine)\s+publish"
    r"|dotnet\s+ef\s+database|psql|sqlcmd|mysql|ssh|scp|rsync"
    r"|(make\s+|(npm|yarn|pnpm)\s+run\s+|just\s+|task\s+|(ba)?sh\s+|\./)\S*(deploy|release|publish|migrate)"
    r")",
    re.I,
)
if REMOTE_EFFECT.search(cmd):
    touch(dirty)
    allow()


READ_ONLY = re.compile(
    r"^(ls|cat|head|tail|less|more|grep|egrep|rg|ag|find|fd|pwd|echo|printf|which|type|"
    r"wc|tree|du|df|ps|env|printenv|stat|file|jq|yq|awk|sed\s+-n|sort|uniq|cut|tr|diff|"
    r"date|whoami|uname|hostname|id|true|test|\[|sleep|realpath|dirname|basename|"
    r"git\s+(status|log|diff|show|branch|blame|grep|ls-files|ls-tree|rev-parse|remote|"
    r"describe|shortlog|cat-file|config\s+--get|worktree\s+list|stash\s+list|tag\s+-l)|"
    r"python3?\s+-c\s+['\"]?print|npm\s+(ls|list|view|outdated|test)|pip3?\s+(list|show|freeze)|"
    r"cargo\s+(tree|metadata|test|check)|go\s+(list|version|test|vet)|pytest|"
    r"dotnet\s+(test|build|--info|--version)|terraform\s+(show|plan|validate|fmt\s+-check|output)|"
    r"kubectl\s+(get|describe|logs|top))\b"
)


def changes_by_heuristic(command: str) -> bool:
    """True if any segment of the command isn't on the read-only list."""
    for seg in re.split(r"&&|\|\||;|\||\n", command):
        seg = seg.strip().lstrip("(").strip()
        if not seg or re.match(r"^cd(\s|$)", seg) or ".bobnet/journal.md" in seg:
            continue  # the journal write itself isn't work to log
        if re.search(r"(^|[^0-9&>])>{1,2}\s*(?!/dev/null|&)\S", seg):
            return True  # a redirect into a file
        if not READ_ONLY.match(seg) or re.search(r"\s-(delete|exec|execdir|ok)\b", seg):
            return True
    return False


snapshot, slow = marker(ev, "gitstate"), marker(ev, "gitslow")
state = None
if not slow.exists():
    started = time.time()
    state = git_state(ev)
    if state is None and time.time() - started > 1.5:
        touch(slow)  # git is too slow here: use the heuristic for the rest of the session
if state is None:
    if changes_by_heuristic(cmd):
        touch(dirty)
    allow()

try:
    previous = snapshot.read_text(encoding="utf-8").strip() if snapshot.exists() else None
    snapshot.write_text(state, encoding="utf-8")
except Exception:
    previous = None
if previous is None:
    # No baseline (mission.py takes one on the first prompt; this is the fallback).
    if changes_by_heuristic(cmd):
        touch(dirty)
elif previous != state:
    touch(dirty)
allow()
