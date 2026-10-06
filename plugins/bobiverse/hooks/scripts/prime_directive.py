#!/usr/bin/env python3
"""
prime_directive.py — PreToolUse(Write|Edit|MultiEdit|NotebookEdit|Bash).
Non-interference zones. Paths that must not be touched without a human saying so.

Default protected zones are the places where a casual edit becomes an outage or
a compliance finding. Each match forces a permission prompt ("ask") — the human
approves per-edit. `deny` zones are absolutely off-limits to Claude.

Config: .bobnet/prime-directive.json
  {
    "ask":  [regex, ...],   # replaces defaults if present
    "deny": [regex, ...],
    "ask_extra": [regex, ...]   # appended to defaults
  }
"""
import re
from bobnet import read_event, pre_tool_decision, allow, load_config

ev = read_event()

DEFAULT_ASK = [
    r"(^|/)\.github/workflows/",
    r"(^|/)\.gitlab-ci\.ya?ml$", r"(^|/)Jenkinsfile$", r"(^|/)\.circleci/",
    r"(^|/)(infra|infrastructure|terraform|pulumi|cdk|cloudformation)/.*\b(prod|production)\b",
    r"(^|/)(prod|production)(\.|/|-)",
    r"(^|/)k8s/.*\b(prod|production)\b", r"(^|/)helm/.*values[-.](prod|production)",
    r"(^|/)(iam|policies|rbac)/", r"iam[-_]?polic", r"\.rego$",
    r"(^|/)(migrations?|alembic|db/migrate)/",
    r"(^|/)Dockerfile(\.prod)?$", r"(^|/)docker-compose\.(prod|production)",
    r"(^|/)(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|poetry\.lock|Cargo\.lock|go\.sum)$",
    r"(^|/)CODEOWNERS$", r"(^|/)SECURITY\.md$", r"(^|/)LICENSE",
    r"(^|/)\.claude/settings(\.local)?\.json$",
    r"(^|/)\.bobnet/(busters|prime-directive|suddar)\.json$",   # the hooks' own config
]
DEFAULT_DENY = [
    r"(^|/)\.git/(config|hooks/|objects/)",
]

cfg = load_config(ev, "prime-directive", {"ask": DEFAULT_ASK, "deny": DEFAULT_DENY, "ask_extra": []})
ASK = list(cfg.get("ask", DEFAULT_ASK)) + list(cfg.get("ask_extra", []))
DENY = list(cfg.get("deny", DEFAULT_DENY))


def check(path: str, how: str):
    for pat in DENY:
        if re.search(pat, path):
            pre_tool_decision("deny",
                f"PRIME DIRECTIVE: `{path}` is a no-interference zone (matched /{pat}/). "
                "Claude does not modify this. The human does it by hand if it needs doing.")
    for pat in ASK:
        if re.search(pat, path):
            pre_tool_decision("ask",
                f"PRIME DIRECTIVE: `{path}` is a protected zone (matched /{pat}/) — {how}. "
                "These files change production, CI, permissions, or dependency resolution. "
                "Confirm this specific change, or decline and ask Bill/Riker to justify it first.")


if ev.tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
    if ev.file_path:
        check(ev.file_path, f"{ev.tool} requested")
    allow()

if ev.tool == "Bash":
    cmd = ev.command
    # Only inspect commands that plausibly write: redirects, mv/cp/rm/sed -i/tee/touch into protected paths.
    if re.search(r"(>|>>|\bmv\b|\bcp\b|\brm\b|\bsed\s+-i|\btee\b|\btouch\b|\btruncate\b|\bchmod\b|\bchown\b|\bgit\s+(checkout|restore|rm|mv)\b)", cmd):
        tokens = re.findall(r"[\w./\-@:~]+", cmd)
        for t in tokens:
            if "/" in t or t.startswith("."):
                for pat in DENY:
                    if re.search(pat, t):
                        pre_tool_decision("deny", f"PRIME DIRECTIVE: shell command touches no-interference path `{t}` (/{pat}/). Denied.")
                for pat in ASK:
                    if re.search(pat, t):
                        pre_tool_decision("ask",
                            f"PRIME DIRECTIVE: shell command appears to modify protected path `{t}` (/{pat}/). "
                            "Confirm this specific command.")
    allow()

allow()
