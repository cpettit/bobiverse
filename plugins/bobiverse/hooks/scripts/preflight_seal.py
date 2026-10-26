#!/usr/bin/env python3
"""
preflight_seal.py — the preflight receipt, and the check that it still holds.

A preflight clears one commit and one set of values. Nothing used to check
that what shipped was what got cleared: Riker cleared f428ea2 for qa, qa then
deployed 71e78ce, which turned a scan on and granted ADF db_owner. This closes
that gap.

  record  — /preflight writes .bobnet/preflight-<env>.json: the cleared commit,
            a sha256 of every watched file (tfvars, env config, pipeline yml),
            and the exact value of each key Riker checked. A value whose key
            looks secret is stored as a hash, never in clear. The file is
            gitignored.

            python3 preflight_seal.py record --env qa --verdict GO \
                --watch envs/qa.tfvars --value envs/qa.tfvars:security_scan_enabled \
                --trigger "5xx rate > 2% for 5 min" [--sha <commit>] [--days 7]

  verify  — for smoke tests or `/preflight --verify`: prints the record, what
            changed since, and whether the deployed commit is the cleared one.

            python3 preflight_seal.py verify [--env qa] [--deployed <sha>]

  (hook)  — PreToolUse(Bash), via gate.py. On a push / apply / deploy command,
            if any unexpired record no longer matches the tree, it asks, naming
            each key or file that moved. It never denies: the plugin can't see
            the pipeline, so the human makes the call. Silent when there are no
            records. Re-running /preflight replaces the record.

Values are read from HCL-style `key = value` assignments (tfvars), including
multi-line lists and maps, compared with whitespace normalized.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bobnet import Event, allow, bobnet_dir, pre_tool_decision, read_event, utf8_stdio  # noqa: E402

SECRET_KEY = re.compile(
    r"(pass(word)?|secret|token|api_?key|private_?key|conn(ection)?_?str)", re.I
)
# Global flags may sit between the tool and its verb: `terraform -chdir=x apply`, `git -C dir push`.
FLAGS = r"(\s+(-C|-c|-n|--namespace|--context|--kube-context|--kubeconfig|--git-dir|--work-tree)\s+\S+|\s+--?[\w-]+(=\S+)?)*"
DEPLOYS = re.compile(
    r"(^|[\s;&|(\"'/])("
    r"git[\"']?" + FLAGS + r"\s+push|(terraform|tofu|terragrunt)[\"']?" + FLAGS + r"\s+apply"
    r"|az\s+(pipelines\s+run|deployment\s+\S+\s+create|webapp\s+deploy)"
    r"|gh\s+workflow\s+run|kubectl" + FLAGS + r"\s+apply|helm" + FLAGS + r"\s+(upgrade|install)"
    r"|(make\s+|(npm|yarn|pnpm)\s+run\s+|\./|(ba)?sh\s+)\S*deploy"
    r")",
    re.I,
)


def project_root(ev: Event) -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or ev.cwd)


def file_hash(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


HEREDOC = re.compile(r"<<-?([A-Za-z_]\w*)[ \t]*\n")


def _mask(text: str) -> str:
    """Same length as text. String contents and heredoc bodies become "x", comments
    become NUL, so brackets inside them don't count and comments can be dropped."""
    out, i, n = list(text), 0, len(text)
    while i < n:
        c = text[i]
        if c in "\"'":
            i += 1
            while i < n and text[i] not in (c, "\n"):
                if text[i] == "\\" and i + 1 < n and text[i + 1] != "\n":
                    out[i] = "x"
                    i += 1
                out[i] = "x"
                i += 1
            i += 1
            continue
        if c == "#" or text.startswith("//", i):
            while i < n and text[i] != "\n":
                out[i] = "\0"
                i += 1
            continue
        if text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            for k in range(i, j):
                out[k] = "\n" if text[k] == "\n" else "\0"
            i = j
            continue
        m = HEREDOC.match(text, i)
        if m:
            end = re.compile(rf"(?m)^[ \t]*{re.escape(m.group(1))}[ \t]*$").search(text, m.end())
            stop = end.end() if end else n
            for k in range(m.end() - 1, stop):
                out[k] = "x"
            i = stop
            continue
        i += 1
    return "".join(out)


def read_value(path: Path, key: str) -> str | None:
    """The value assigned to top-level `key` in an HCL/tfvars file, comments
    dropped and whitespace normalized. Keys nested inside a map don't count."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    masked = _mask(text)
    assign = re.compile(rf"[ \t]*(\"?){re.escape(key)}\1[ \t]*=(?!=)[ \t]*")
    depth, at_line_start, i, n = 0, True, 0, len(text)
    while i < n:
        if at_line_start and depth == 0:
            m = assign.match(text, i)
            if m:
                k = m.start() + len(m.group(0)) - len(m.group(0).lstrip())
                if masked[k] == text[k]:  # not inside a comment, string or heredoc
                    j, d, buf = m.end(), 0, []
                    while j < n:
                        mc = masked[j]
                        if mc in "[{(":
                            d += 1
                        elif mc in "]})":
                            d -= 1
                        if mc == "\n" and d <= 0:
                            break
                        if mc != "\0":
                            buf.append(text[j])
                        j += 1
                    return re.sub(r"\s+", " ", "".join(buf)).strip().rstrip(",").strip()
        mc = masked[i]
        if mc in "[{(":
            depth += 1
        elif mc in "]})":
            depth = max(0, depth - 1)
        at_line_start = mc == "\n"
        i += 1
    return None


def stored(key: str, value: str | None) -> str | None:
    if value is None or not SECRET_KEY.search(key):
        return value
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def records(ev: Event, env: str | None = None) -> list[dict]:
    out = []
    for p in sorted(bobnet_dir(ev).glob("preflight-*.json")):
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if env and r.get("env") != env:
            continue
        r["_path"] = str(p)
        out.append(r)
    return out


def expired(r: dict) -> bool:
    return time.time() > float(r.get("expires_epoch") or 0)


def deltas(ev: Event, r: dict) -> list[str]:
    """Human-readable differences between the record and the tree right now."""
    root = project_root(ev)
    out = []
    for v in r.get("values", []):
        now_v = stored(v["key"], read_value(root / v["file"], v["key"]))
        if now_v != v.get("value"):
            shown = (
                "(secret changed)"
                if str(v.get("value", "")).startswith("sha256:")
                else f"`{now_v}`"
            )
            out.append(
                f"{v['file']}: `{v['key']}` cleared as `{v.get('value')}`, now {shown if now_v is not None else 'missing'}"
            )
    for w in r.get("watched", []):
        if file_hash(root / w["path"]) != w.get("sha256"):
            out.append(f"{w['path']} changed since the preflight")
    return out


def git(ev: Event, *args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=project_root(ev),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        ).stdout.strip()
    except Exception:
        return ""


def cmd_record(ev: Event, a) -> None:
    root = project_root(ev)
    sha = a.sha or git(ev, "rev-parse", "HEAD")
    values = []
    for spec in a.value:
        file, _, key = spec.rpartition(":")
        if not file or not key:
            sys.exit(f"--value must be <file>:<key>, got {spec!r}")
        values.append(
            {
                "file": file,
                "key": key,
                "value": stored(key, read_value(root / file, key)),
            }
        )
    watched = sorted({*a.watch, *(v["file"] for v in values)})
    record = {
        "env": a.env,
        "verdict": a.verdict,
        "cleared_sha": sha,
        "cleared_at": time.strftime("%Y-%m-%d %H:%M"),
        "expires_epoch": int(time.time() + a.days * 86400),
        "watched": [{"path": w, "sha256": file_hash(root / w)} for w in watched],
        "values": values,
        "rollback_triggers": a.trigger,
        "mismatch_policy": "A cleared value or watched file that changes needs a fresh /preflight "
        "before it ships. An uncleared privilege grant or security-control change "
        "that reaches the environment is a rollback trigger.",
    }
    missing = [w["path"] for w in record["watched"] if w["sha256"] is None]
    unread = [f"{v['file']}:{v['key']}" for v in values if v["value"] is None]
    path = bobnet_dir(ev) / f"preflight-{a.env}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"Preflight record written: {path}")
    print(
        f"  {a.env} · {a.verdict} · {sha[:12]} · {len(watched)} watched file(s) · {len(values)} value(s) · expires in {a.days} days"
    )
    for m in missing:
        print(f"  ⚠ watched file not found: {m}")
    for u in unread:
        print(f"  ⚠ value not found (recorded as missing): {u}")


def cmd_verify(ev: Event, a) -> None:
    rs = records(ev, a.env)
    if not rs:
        print("No preflight records" + (f" for {a.env}" if a.env else "") + ".")
        return
    head = git(ev, "rev-parse", "HEAD")
    for r in rs:
        print(
            f"PREFLIGHT RECORD — {r.get('env')} · {r.get('verdict')} · cleared {str(r.get('cleared_sha'))[:12]} at {r.get('cleared_at')}"
            + (" · EXPIRED" if expired(r) else "")
        )
        deployed = a.deployed
        if deployed:
            same = str(r.get("cleared_sha", "")).startswith(
                deployed
            ) or deployed.startswith(str(r.get("cleared_sha", "")))
            print(
                f"  Deployed: {deployed[:12]} — {'matches the cleared commit' if same else 'NOT the cleared commit'}"
            )
        else:
            print(
                "  Deployed: unknown (pass --deployed <sha> from the pipeline or a /version endpoint)"
            )
        print(f"  HEAD:     {head[:12] or 'unknown'}")
        d = deltas(ev, r)
        print(
            "  Since the preflight: " + ("nothing cleared has changed" if not d else "")
        )
        for line in d:
            print(f"    - {line}")
        for t in r.get("rollback_triggers", []):
            print(f"  Rollback trigger: {t}")


def hook(ev: Event) -> None:
    if ev.tool != "Bash" or not DEPLOYS.search(ev.command or ""):
        allow()
    findings = []
    for r in records(ev):
        if expired(r):
            continue
        d = deltas(ev, r)
        if d:
            findings.append(
                f"`{r.get('env')}` was cleared at {str(r.get('cleared_sha'))[:12]} on {r.get('cleared_at')}. Since then:\n"
                + "\n".join(f"  - {x}" for x in d)
            )
    if not findings:
        allow()
    pre_tool_decision(
        "ask",
        "PREFLIGHT SEAL: this ships changes the preflight didn't clear.\n"
        + "\n".join(findings)
        + "\nRe-run /preflight for that environment, or approve if this change was reviewed.",
    )


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("record", "verify"):
        utf8_stdio()
        ap = argparse.ArgumentParser(prog="preflight_seal.py")
        sub = ap.add_subparsers(dest="mode", required=True)
        rec = sub.add_parser("record")
        rec.add_argument("--env", required=True)
        rec.add_argument("--verdict", required=True)
        rec.add_argument("--sha")
        rec.add_argument("--watch", action="append", default=[])
        rec.add_argument("--value", action="append", default=[])
        rec.add_argument("--trigger", action="append", default=[])
        rec.add_argument("--days", type=float, default=7)
        ver = sub.add_parser("verify")
        ver.add_argument("--env")
        ver.add_argument("--deployed")
        args = ap.parse_args()
        cli_event = Event({"cwd": os.getcwd()})
        (cmd_record if args.mode == "record" else cmd_verify)(cli_event, args)
        sys.exit(0)
    hook(read_event())
