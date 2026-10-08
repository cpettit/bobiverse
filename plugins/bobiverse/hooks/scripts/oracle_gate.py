#!/usr/bin/env python3
"""
oracle_gate.py — PreToolUse(Agent|Task). The box Thoth lives in.

Some agents are expensive by design (top model, max effort). Launching one
should be a human decision, not something the main agent does because it
seemed like a good idea. This hook forces a permission prompt whenever an
agent on the gated list is about to be spawned — even in auto-accept mode.

Default gated list: thoth. Extend via .bobnet/oracle-gate.json:
  { "ask_agents": ["thoth", "my-other-expensive-agent"], "note": "optional extra text" }
A bare name matches both `thoth` and `bobiverse:thoth`.
"""

from bobnet import read_event, pre_tool_decision, allow, load_config

ev = read_event()
if ev.tool not in ("Agent", "Task"):
    allow()
if not isinstance(ev.input, dict):
    allow()

cfg = load_config(ev, "oracle-gate", {"ask_agents": ["thoth"], "note": ""})
gated = {a.lower() for a in cfg.get("ask_agents", [])}

sub = str(ev.input.get("subagent_type") or ev.input.get("agent") or "").strip().lower()
short = sub.split(":")[-1]
if short in gated or sub in gated:
    desc = str(ev.input.get("description") or "")[:120]
    extra = f" {cfg['note']}" if cfg.get("note") else ""
    pre_tool_decision(
        "ask",
        f"ORACLE GATE: about to spawn `{sub}` — the most capable model at maximum reasoning effort. "
        f"This is the expensive one; it answers a single question and takes no actions. "
        f'Task: "{desc}". Confirm this question is worth it, or decline and let a regular Bob take a pass first.{extra}',
    )
allow()
