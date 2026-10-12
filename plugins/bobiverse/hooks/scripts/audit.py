#!/usr/bin/env python3
"""
audit.py — hash-chained, append-only audit log of tool activity.

Two roles:
  • imported by bobnet.py: every ask/deny any gate hook returns is recorded
  • run as a PostToolUse hook (all tools): every tool call that executed is recorded

Each line of .bobnet/audit/audit-YYYY-MM.jsonl is a JSON object:
  {"ts", "session", "agent", "event", "hook", "tool", "target", "decision", "reason", "prev", "hash"}
where  hash = sha256(prev + canonical_json(entry_without_hash)).
The first entry of a month chains from the last hash of the previous month's
file (or "GENESIS"), so the whole history is one chain. Editing, deleting or
reordering any line breaks every hash after it — `audit_verify.py` finds where.

Targets and reasons pass through the PII redactor before they're written, so
the log itself never becomes a PHI store. The Prime Directive denies Claude
any edit under .bobnet/audit/.

This proves the log wasn't altered *after the fact by something that didn't
recompute the chain*. Anyone with write access can rewrite the whole chain;
for real tamper-evidence, ship the log off-box (a WORM bucket, your SIEM)
and anchor the latest hash somewhere you control — see `export` in
compliance_check.py.

Config: .bobnet/audit.json → {"enabled": true}
"""

import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

try:
    import fcntl  # POSIX advisory locks; parallel hooks write concurrently
except ImportError:  # Windows: best effort, no lock
    fcntl = None

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

GENESIS = "GENESIS"


def _canon(d: dict) -> str:
    return json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def entry_hash(prev: str, body: dict) -> str:
    return hashlib.sha256((prev + _canon(body)).encode()).hexdigest()


def audit_dir(ev) -> Path:
    from bobnet import bobnet_dir

    return bobnet_dir(ev) / "audit"


def _last_hash(d: Path) -> str:
    files = sorted(d.glob("audit-*.jsonl"))
    for f in reversed(files):
        try:
            with f.open("rb") as fh:
                fh.seek(0, os.SEEK_END)
                size = fh.tell()
                fh.seek(max(0, size - 8192))
                tail = fh.read().decode(errors="ignore").strip().splitlines()
            for line in reversed(tail):
                try:
                    return json.loads(line)["hash"]
                except Exception:
                    continue
        except Exception:
            continue
    return GENESIS


def _target(ev) -> str:
    i = ev.input if isinstance(ev.input, dict) else {}
    t = (
        i.get("file_path")
        or i.get("path")
        or i.get("notebook_path")
        or i.get("command")
        or i.get("url")
        or i.get("query")
        or i.get("pattern")
        or i.get("subagent_type")
        or i.get("description")
        or ""
    )
    if not t and i:
        t = _canon(i)
    return str(t).replace("\n", " ⏎ ")[:300]


def _scrub(s: str) -> str:
    try:
        from pii import redact

        return redact(s)[0]
    except Exception:
        return s


def record(ev, *, hook: str, decision: str, reason: str = "") -> None:
    """Append one entry. Never raises: audit trouble must not block work."""
    try:
        from bobnet import load_config

        if not load_config(ev, "audit", {"enabled": True}).get("enabled", True):
            return
        d = audit_dir(ev)
        d.mkdir(parents=True, exist_ok=True)
        lock_path = d / ".lock"
        with open(lock_path, "a+") as lock:
            if fcntl:
                fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                prev = _last_hash(d)
                body = {
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "session": ev.session,
                    "agent": ev.raw.get("agent_id") or ev.raw.get("agentId") or "",
                    "event": ev.event
                    or ("PostToolUse" if hook == "audit" else "PreToolUse"),
                    "hook": hook,
                    "tool": ev.tool,
                    "target": _scrub(_target(ev)),
                    "decision": decision,
                    "reason": _scrub(re.sub(r"\s+", " ", reason))[:300],
                    "prev": prev,
                }
                body["hash"] = entry_hash(prev, body)
                f = d / f"audit-{time.strftime('%Y-%m', time.gmtime())}.jsonl"
                with f.open("a", encoding="utf-8") as out:
                    out.write(_canon(body) + "\n")
            finally:
                if fcntl:
                    fcntl.flock(lock, fcntl.LOCK_UN)
    except Exception:
        pass


def verify(d: Path) -> tuple[bool, int, str]:
    """Walk every file in order. Returns (ok, entries_checked, message)."""
    prev, n = GENESIS, 0
    files = sorted(d.glob("audit-*.jsonl"))
    if not files:
        return True, 0, "no audit entries yet"
    for f in files:
        for lineno, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                e = json.loads(line)
            except Exception:
                return False, n, f"{f.name}:{lineno}: not valid JSON"
            h = e.pop("hash", None)
            if e.get("prev") != prev:
                return (
                    False,
                    n,
                    f"{f.name}:{lineno}: chain broken — prev does not match the entry before it (deleted or reordered line?)",
                )
            if entry_hash(prev, e) != h:
                return (
                    False,
                    n,
                    f"{f.name}:{lineno}: hash mismatch — this entry was modified",
                )
            prev, n = h, n + 1
    return True, n, f"chain intact: {n} entries, head {prev[:16]}…"


if __name__ == "__main__":
    # PostToolUse: record that a tool call executed, and whether it errored.
    from bobnet import read_event

    ev = read_event()
    r = ev.result
    errored = isinstance(r, dict) and bool(
        r.get("is_error") or r.get("isError") or r.get("error")
    )
    record(ev, hook="audit", decision="error" if errored else "executed")
    sys.exit(0)
