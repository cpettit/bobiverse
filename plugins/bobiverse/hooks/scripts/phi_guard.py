#!/usr/bin/env python3
"""
phi_guard.py — PreToolUse(Write|Edit|MultiEdit|NotebookEdit|Bash).
Stops PII/PHI from being written into files or typed into commands.

  Write/Edit:  HIGH hit (SSN, card, NPI, MBI, DEA, MRN/member ID) → deny
               MEDIUM hit (DOB+name, diagnosis code, phone+name, bulk emails) → ask
  Bash:        any HIGH hit in the command text → ask (it's already in context;
               the question is whether it should go into a file, a DB, or a request)

There is deliberately no default allowlist for test fixtures: real patient data
copied into tests/fixtures is the classic leak. Synthetic data should use the
documented test values (123-45-6789, 4111 1111 1111 1111, …), which the
detector ignores. If you have a vetted synthetic-data directory, allow it
explicitly:

  .bobnet/phi-guard.json → {"allow_paths": ["^synthetic/"], "medium": "ask"|"allow"|"deny"}
Detector tuning lives in .bobnet/pii.json (see pii.py).
"""
from __future__ import annotations


import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bobnet import allow, load_config, pre_tool_decision, read_event  # noqa: E402
from pii import scan, summarize  # noqa: E402

ev = read_event()
cfg = load_config(ev, "phi-guard", {"allow_paths": [], "medium": "ask"})
pii_cfg = load_config(ev, "pii", {})

if ev.tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
    path = ev.file_path
    if path and any(re.search(p, path) for p in cfg.get("allow_paths", [])):
        allow()
    text = ev.written_text
    hits = scan(text, pii_cfg)
    if not hits:
        allow()
    high = [h for h in hits if h.severity == "high"]
    if high:
        pre_tool_decision(
            "deny",
            f"PHI GUARD: refusing to write personal identifiers into `{path or '(unknown)'}`:\n"
            f"{summarize(high, text)}\n"
            "Use synthetic data (documented test values like 123-45-6789 or 4111 1111 1111 1111 are ignored), "
            "a reference to where the record lives, or a tokenized ID. If this is a vetted synthetic-data path, "
            "add it to .bobnet/phi-guard.json allow_paths.",
        )
    mode = cfg.get("medium", "ask")
    if mode == "allow":
        allow()
    pre_tool_decision(
        "deny" if mode == "deny" else "ask",
        f"PHI GUARD: this write to `{path or '(unknown)'}` combines fields that identify a person:\n"
        f"{summarize(hits, text)}\n"
        "Confirm this is synthetic or de-identified data before approving.",
    )

if ev.tool == "Bash":
    cmd = ev.command
    high = [h for h in scan(cmd, pii_cfg) if h.severity == "high"]
    if high:
        pre_tool_decision(
            "ask",
            "PHI GUARD: this command contains personal identifiers:\n"
            f"{summarize(high, cmd)}\n"
            "Check where it sends them — a file, a database, a request, a log — before approving.",
        )

allow()
