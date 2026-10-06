#!/usr/bin/env python3
"""
bobnet_log.py — Stop. The Bobnet journal.

If this session did real work (an Edit/Write/Bash happened — the autofactory and
mission hooks drop a `dirty` marker) and no journal entry has been written yet,
block the stop ONCE and ask Claude to append a "Bob's log" entry to
.bobnet/journal.md. The companion PostToolUse hook (`bobnet_mark.py`) notices the
journal being written and drops a `logged` marker so the next stop goes through.

Also fires the SCUT ping if configured (see scut.py; called here to avoid a
second Stop hook racing this one).
"""
import subprocess
import sys
from pathlib import Path
from bobnet import read_event, allow, block, marker, bobnet_dir, now

ev = read_event()

# Always try to ping, regardless of logging state.
try:
    subprocess.run([sys.executable, str(Path(__file__).with_name("scut.py")), "stop"],
                   input=__import__("json").dumps(ev.raw), text=True, timeout=10, capture_output=True)
except Exception:
    pass

if ev.stop_hook_active:
    allow()
if not marker(ev, "dirty").exists():
    allow()            # nothing changed this session; no log needed
if marker(ev, "logged").exists():
    allow()
if marker(ev, "logreq").exists():
    allow()            # we already asked once; don't nag
marker(ev, "logreq").touch()

journal = bobnet_dir(ev) / "journal.md"
block(
    "BOBNET LOG (do this, then stop): this session changed things. Append an entry to "
    f"`{journal}` (create the file with a `# Bobnet journal` heading if missing) in this exact shape:\n\n"
    f"## {now()} — <one-line title>\n"
    "- Did: <what changed, 1–3 bullets, file/PR refs>\n"
    "- Decided: <decisions made and why, or 'none'>\n"
    "- Open: <loose threads the next session should know, or 'none'>\n"
    "- Bobs: <which agents were used, or 'solo'>\n\n"
    "Keep it under 10 lines. Facts, not narrative. Then you're done."
)
