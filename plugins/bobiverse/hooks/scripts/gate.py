#!/usr/bin/env python3
"""
gate.py — run several Bobnet hook scripts in ONE Python process.

Every hook used to be its own `python3 script.py` process. On Linux that's
~50 ms each; on Windows an interpreter cold start plus antivirus scanning can
take seconds, and a single Bash call fired six of them. This runs them all
in-process instead:

    python3 gate.py pre  busters prime_directive suddar phi_guard data_zones egress
    python3 gate.py post bobnet_mark autofactory audit
    python3 gate.py run  mission:save          # any event; script:arg passes argv

The hook scripts themselves are unchanged and still run standalone (the
self-tests call them directly). Each is executed with runpy against the same
event JSON; its stdout, stderr and exit code are captured.

  pre   PreToolUse. Most restrictive decision wins: deny > ask > allow.
        Stops at the first deny. Reasons from scripts at the winning level are
        joined. A script that crashes is skipped (fails open, as before).
  post  PostToolUse. Every script runs. Any exit 2 → exit 2 with the
        combined stderr (Autofactory's feedback to Claude).
  run   Anything else (UserPromptSubmit, SessionStart, Stop, …). Every script
        runs; the first one that prints a JSON decision or exits 2 wins;
        plain stdout (context) is concatenated.
"""
from __future__ import annotations


import contextlib
import io
import json
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

RANK = {"allow": 0, "ask": 1, "deny": 2}


def run_one(spec: str, raw: str):
    """Execute one hook script in-process. Returns (exit_code, stdout, stderr)."""
    name, _, arg = spec.partition(":")
    path = HERE / f"{name}.py"
    out, err = io.StringIO(), io.StringIO()
    old_argv, old_stdin = sys.argv, sys.stdin
    sys.argv = [str(path)] + ([arg] if arg else [])
    sys.stdin = io.StringIO(raw)
    code = 0
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            runpy.run_path(str(path), run_name="__main__")
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    except Exception as e:  # a broken hook is skipped, never blocks
        code = 1
        err.write(f"{name}: {type(e).__name__}: {e}\n")
    finally:
        sys.argv, sys.stdin = old_argv, old_stdin
    return code, out.getvalue(), err.getvalue()


def decision_of(stdout: str):
    try:
        d = json.loads(stdout)
    except Exception:
        return None, ""
    h = d.get("hookSpecificOutput") or {}
    return h.get("permissionDecision"), h.get("permissionDecisionReason", "")


def main():
    if len(sys.argv) < 3:
        sys.exit(0)
    mode, scripts = sys.argv[1], sys.argv[2:]
    raw = sys.stdin.read()

    if mode == "pre":
        best, reasons = "allow", []
        for s in scripts:
            code, out, _ = run_one(s, raw)
            if code != 0:
                continue  # crashed or errored: fail open, as standalone hooks do
            d, why = decision_of(out)
            if d not in RANK:
                continue
            if RANK[d] > RANK[best]:
                best, reasons = d, [why]
            elif RANK[d] == RANK[best] and d != "allow":
                reasons.append(why)
            if best == "deny":
                break
        if best != "allow":
            print(
                json.dumps(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "PreToolUse",
                            "permissionDecision": best,
                            "permissionDecisionReason": "\n\n".join(
                                r for r in reasons if r
                            ),
                        }
                    }
                )
            )
        sys.exit(0)

    if mode == "post":
        feedback = []
        for s in scripts:
            code, _, err = run_one(s, raw)
            if code == 2 and err.strip():
                feedback.append(err.strip())
        if feedback:
            sys.stderr.write("\n\n".join(feedback) + "\n")
            sys.exit(2)
        sys.exit(0)

    # run: generic events
    context = []
    for s in scripts:
        code, out, err = run_one(s, raw)
        if code == 2:
            sys.stderr.write(err)
            sys.exit(2)
        stripped = out.strip()
        if stripped.startswith("{"):
            print(stripped)  # a JSON decision (e.g. Stop's block) — first one wins
            sys.exit(0)
        if stripped:
            context.append(stripped)
    if context:
        print("\n\n".join(context))
    sys.exit(0)


if __name__ == "__main__":
    main()
