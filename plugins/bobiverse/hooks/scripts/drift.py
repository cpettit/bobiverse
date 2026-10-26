#!/usr/bin/env python3
"""
drift.py — SubagentStop. Replicative drift check.

The Bobs diverge from the original over generations; subagents diverge from the
task they were given over a long run. When a subagent tries to stop, this hook
blocks it exactly once and makes it append a DRIFT CHECK — a self-audit of
output vs. assignment. The second stop attempt (stop_hook_active) is allowed.

No external model call; the subagent grades itself against its own instructions,
which is cheap and surprisingly effective at catching "I fixed something else."
"""
import uuid
from bobnet import read_event, allow, block, marker, touch

ev = read_event()


def finished():
    """This subagent is allowed to stop: tell bobnet_log it has reported."""
    touch(marker(ev, f"agentdone.{ev.agent_id or 'anon' + uuid.uuid4().hex[:12]}"))
    allow()


if ev.stop_hook_active:
    finished()
# One check per subagent. Subagents share the session id, so keying on the
# session alone meant only the first Bob in a moot was ever checked.
m = marker(ev, f"drift.{ev.agent_id}" if ev.agent_id else "drift")
if m.exists():
    finished()
touch(m)
block(
    "REPLICATIVE DRIFT CHECK (Bobnet protocol — do this once, then stop):\n"
    "Before you finish, append a short section titled `DRIFT CHECK` to your final report:\n"
    "  1. The task as you were given it, in one sentence.\n"
    "  2. Requirements addressed — list each.\n"
    "  3. Requirements NOT addressed, or only partially — list each, with why.\n"
    "  4. Anything you did that was OUTSIDE the assignment (files touched, scope added) — list, or 'none'.\n"
    "  5. Confidence that the integrator can use this as-is: high / medium / low, one reason.\n"
    "Be literal. This is for Bob to integrate correctly, not to make you look good."
)
