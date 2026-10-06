#!/usr/bin/env python3
"""
bobnet.py — shared helpers for Bobiverse hooks.

Every hook does: `ev = read_event()` then inspects ev.tool / ev.input / etc.
Field names in Claude Code's hook JSON have varied across versions; this
normalizes the common spellings so the hooks don't care.
"""
import json
import os
import sys
import time
from pathlib import Path


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
        self.message = g("message") or ""
        self.notification_type = g("notification_type") or g("type") or ""

    # Convenience accessors for the tools we gate most often
    @property
    def command(self) -> str:
        return str(self.input.get("command", "")) if isinstance(self.input, dict) else ""

    @property
    def file_path(self) -> str:
        if not isinstance(self.input, dict):
            return ""
        return str(self.input.get("file_path") or self.input.get("path") or self.input.get("notebook_path") or "")

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


def read_event() -> Event:
    try:
        data = sys.stdin.read()
        return Event(json.loads(data) if data.strip() else {})
    except Exception:
        return Event({})


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
            gi.write_text("*.marker\nmission-*.md\nbusters.disarmed\n")
    except Exception:
        pass
    return d


def marker(ev: Event, name: str) -> Path:
    return ensure_bobnet(ev) / f"{name}-{ev.session}.marker"


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
            user = json.loads(p.read_text())
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
    """PreToolUse: decision in allow|deny|ask."""
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        }
    }))
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
