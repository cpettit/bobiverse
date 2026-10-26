#!/usr/bin/env python3
"""
bobnet.py — shared helpers for Bobiverse hooks.

Every hook does: `ev = read_event()` then inspects ev.tool / ev.input / etc.
Field names in Claude Code's hook JSON have varied across versions; this
normalizes the common spellings so the hooks don't care.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path


def utf8_stdio():
    """Hook output must be UTF-8 whatever the console code page is (Windows
    defaults to cp1252, which turns · and — into mojibake). Guarded: stdout may
    be a StringIO under gate.py, or missing reconfigure on old Pythons."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def read_stdin_text() -> str:
    """Read the hook event as UTF-8 bytes, not in the locale encoding. On Windows
    a non-ASCII character in the event used to fail decoding, read_event fell back
    to an empty Event, and every gate allowed the command."""
    buffer = getattr(sys.stdin, "buffer", None)
    if buffer is not None:
        return buffer.read().decode("utf-8", errors="replace")
    return sys.stdin.read()  # already text (gate.py passes a StringIO)


utf8_stdio()


def safe_id(value) -> str:
    """An agent id usable in a marker filename."""
    return re.sub(r"[^A-Za-z0-9_-]", "", str(value or ""))[:64]


class Event:
    def __init__(self, raw: dict):
        self.raw = raw or {}
        g = self.raw.get
        self.event = g("hook_event_name") or g("event") or ""
        self.session = g("session_id") or g("sessionId") or "nosession"
        self.cwd = g("cwd") or (g("workspace") or {}).get("current_dir") or os.getcwd()
        self.tool = g("tool_name") or g("tool") or ""
        self.input = g("tool_input") or g("input") or {}
        self.result = g("tool_response") or g("result")
        self.prompt = g("prompt") or g("text") or ""
        self.source = g("source") or ""
        self.stop_hook_active = bool(g("stop_hook_active"))
        self.transcript = g("transcript_path") or ""
        self.agent_id = safe_id(g("agent_id") or g("agentId") or "")
        if not self.agent_id:  # fall back to the subagent transcript name: agent-<id>.jsonl
            m = re.search(r"agent-([A-Za-z0-9_-]+)\.jsonl$", str(g("agent_transcript_path") or ""))
            self.agent_id = m.group(1) if m else ""
        self.message = g("message") or ""
        self.notification_type = g("notification_type") or g("type") or ""

    # Convenience accessors for the tools we gate most often
    @property
    def command(self) -> str:
        return (
            str(self.input.get("command", "")) if isinstance(self.input, dict) else ""
        )

    @property
    def file_path(self) -> str:
        if not isinstance(self.input, dict):
            return ""
        return str(
            self.input.get("file_path")
            or self.input.get("path")
            or self.input.get("notebook_path")
            or ""
        )

    @property
    def written_text(self) -> str:
        """Text about to be written by Write/Edit/MultiEdit/NotebookEdit."""
        if not isinstance(self.input, dict):
            return ""
        parts = []
        for k in ("content", "new_string", "new_source"):
            v = self.input.get(k)
            if isinstance(v, str):
                parts.append(v)
        for e in self.input.get("edits", []) or []:
            if isinstance(e, dict) and isinstance(e.get("new_string"), str):
                parts.append(e["new_string"])
        return "\n".join(parts)


_EVENT: "Event | None" = None


def read_event() -> Event:
    global _EVENT
    try:
        data = read_stdin_text()
        _EVENT = Event(json.loads(data) if data.strip() else {})
    except Exception:
        _EVENT = Event({})
    return _EVENT


def _audit(decision: str, reason: str):
    """Record a gate decision in the hash-chained audit log. Never raises."""
    if _EVENT is None:
        return
    try:
        import audit  # local module beside this one

        hook = Path(sys.argv[0]).stem
        audit.record(_EVENT, hook=hook, decision=decision, reason=reason)
    except Exception:
        pass


# ---------- .bobnet state directory ----------


def bobnet_dir(ev: Event) -> Path:
    """Project-local state dir. Override with BOBNET_DIR."""
    root = os.environ.get("BOBNET_DIR")
    if root:
        return Path(root)
    project = os.environ.get("CLAUDE_PROJECT_DIR") or ev.cwd
    return Path(project) / ".bobnet"


def ensure_bobnet(ev: Event) -> Path:
    d = bobnet_dir(ev)
    try:
        d.mkdir(parents=True, exist_ok=True)
        gi = d / ".gitignore"
        if not gi.exists():
            # Journal and research are meant to be committed; session markers are not.
            # The audit log and compliance packs may hold paths/commands from a real
            # environment; they're evidence to export deliberately, not to commit by accident.
            gi.write_text(
                "*.marker\nmission-*.md\nbusters.disarmed\naudit/\ncompliance/\npreflight-*.json\n",
                encoding="utf-8",
            )
        elif "preflight-*.json" not in gi.read_text(encoding="utf-8", errors="ignore"):
            # Added in v0.4.2: preflight records hold environment values; keep them out of git.
            with gi.open("a", encoding="utf-8") as f:
                f.write("preflight-*.json\n")
    except Exception:
        pass
    return d


def marker(ev: Event, name: str) -> Path:
    return ensure_bobnet(ev) / f"{name}-{ev.session}.marker"


def pending_agents(ev: Event, max_age_s: int = 3600) -> int:
    """Background Bobs spawned this session that haven't finished yet.

    bobnet_mark drops `agent.<id>` when an Agent/Task call returns, and drift
    drops `agentdone.<id>` when that subagent is allowed to stop. Either can
    land first, so this is a set difference, not a counter. A spawn older than
    max_age_s is ignored so a crashed or cancelled agent can't hold the journal
    prompt off forever. A finish without an id cancels one spawn by count.
    """
    try:
        d = bobnet_dir(ev)
        suffix = f"-{ev.session}.marker"
        cutoff = time.time() - max_age_s

        def ids(prefix: str, fresh_only: bool) -> set:
            out = set()
            for p in d.glob(f"{prefix}.*{suffix}"):
                if fresh_only and p.stat().st_mtime < cutoff:
                    continue
                out.add(p.name[len(prefix) + 1 : -len(suffix)])
            return out

        spawned = ids("agent", fresh_only=True)
        done = ids("agentdone", fresh_only=False)
        anonymous = {i for i in ids("agentdone", fresh_only=True) if i.startswith("anon")}
        return max(0, len(spawned - done) - len(anonymous))
    except Exception:
        return 0


def git_state(ev: "Event"):
    """Hash of the repo's git state, or None if git is unavailable or slow.

    Covers HEAD and ahead/behind (so commit, checkout and push count), every
    listed path (untracked files one by one, not collapsed to their directory),
    and each path's mtime (so re-editing an already-modified file counts).
    Paths under any .bobnet/ are left out, so writing the journal or markers
    never looks like a change. Paths are joined to the repo root, not the
    project dir, which may be a subdirectory.
    """
    root = os.environ.get("CLAUDE_PROJECT_DIR") or ev.cwd
    try:
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=root,
                             capture_output=True, timeout=2)
        if top.returncode != 0:
            return None
        top_dir = top.stdout.decode("utf-8", "replace").strip()
        r = subprocess.run(
            ["git", "--no-optional-locks", "status", "--porcelain=v2", "--branch", "-z",
             "--untracked-files=all"],
            cwd=top_dir, capture_output=True, timeout=2,
        )
    except Exception:
        return None
    if r.returncode != 0:
        return None
    h = hashlib.sha256()
    skip_next, statted = False, 0
    for rec in r.stdout.decode("utf-8", "replace").split("\0"):
        if skip_next:
            skip_next = False
            continue
        if rec.startswith(("# branch.oid", "# branch.head", "# branch.ab")):
            h.update(rec.encode())
            continue
        fields = {"1": 8, "2": 9, "u": 10, "?": 1}.get(rec[:1])
        if fields is None:
            continue
        skip_next = rec[:1] == "2"  # a rename's original path follows
        path = rec.split(" ", fields)[-1]
        if path.startswith(".bobnet/") or "/.bobnet/" in path:
            continue
        h.update(rec.encode())
        if statted < 2000:  # bound the cost in a huge dirty tree
            statted += 1
            try:
                h.update(str(os.stat(os.path.join(top_dir, path)).st_mtime_ns).encode())
            except OSError:
                pass
    return h.hexdigest()


def touch(p: Path):
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.touch()
    except Exception:
        pass


def load_config(ev: Event, name: str, default: dict) -> dict:
    """Read .bobnet/<name>.json, merged over defaults. Missing/invalid → defaults."""
    p = bobnet_dir(ev) / f"{name}.json"
    try:
        if p.exists():
            user = json.loads(p.read_text(encoding="utf-8"))
            merged = dict(default)
            merged.update(user)
            return merged
    except Exception:
        pass
    return dict(default)


# ---------- hook responses ----------


def allow():
    sys.exit(0)


def pre_tool_decision(decision: str, reason: str):
    """PreToolUse: decision in allow|deny|ask. Asks and denies are audited."""
    if decision != "allow":
        _audit(decision, reason)
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": decision,
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    sys.exit(0)


def block(reason: str):
    """Stop / SubagentStop / UserPromptSubmit style block with a reason Claude sees."""
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


def feedback(reason: str):
    """Exit 2: action is blocked and stderr goes to Claude as feedback."""
    sys.stderr.write(reason.rstrip() + "\n")
    sys.exit(2)


def context(text: str):
    """SessionStart / UserPromptSubmit: plain stdout is added to Claude's context."""
    sys.stdout.write(text.rstrip() + "\n")
    sys.exit(0)


def now() -> str:
    return time.strftime("%Y-%m-%d %H:%M")
