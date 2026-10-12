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
import sys
from bobnet import (
    read_event,
    allow,
    context,
    bobnet_dir,
    ensure_bobnet,
    load_config,
    now,
)

mode = sys.argv[1] if len(sys.argv) > 1 else "save"
ev = read_event()
bn = ensure_bobnet(ev)
mission = bn / f"mission-{ev.session}.md"
start = bn / f"start-{ev.session}.marker"

if mode == "save":
    if not start.exists():
        start.touch()
    # Opt out entirely: .bobnet/mission.json {"enabled": false} or BOBNET_MISSION=0
    enabled = (
        load_config(ev, "mission", {"enabled": True}).get("enabled", True)
        and os.environ.get("BOBNET_MISSION", "1") != "0"
    )
    if enabled and not mission.exists() and ev.prompt.strip():
        p = ev.prompt.strip()
        # Skip trivial openers so the "mission" isn't "hi"
        if len(p) >= 12 and not p.startswith("/"):
            # The prompt is saved to disk: redact personal data first, so a pasted
            # record doesn't become PHI at rest.
            try:
                from pii import redact

                p, hits = redact(p, load_config(ev, "pii", {}))
                note = f" · {len(hits)} personal-data item(s) redacted" if hits else ""
            except Exception:
                p, note = "(mission not saved: redaction unavailable)", ""
            mission.write_text(f"Recorded {now()}{note}\n\n{p[:4000]}\n")
    allow()

if mode == "restore":
    if ev.source == "compact" and mission.exists():
        text = mission.read_text(errors="ignore").strip()
        context(
            "MISSION BRIEF (restored after context compaction — this is the original ask, verbatim):\n\n"
            f"{text}\n\n"
            "Re-anchor on this. If the work has drifted from it, say so and either steer back or "
            "confirm with the human that the drift is intended."
        )
    allow()

allow()
