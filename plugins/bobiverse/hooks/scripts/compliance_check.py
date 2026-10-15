#!/usr/bin/env python3
"""
compliance_check.py — what guards are active, is the audit chain intact, and
an exportable evidence pack.

    python3 compliance_check.py [--project DIR] [--export]

Prints a markdown posture report. With --export, also writes
.bobnet/compliance/<YYYY-MM-DD>/ containing:
  posture.md          this report
  audit-verify.txt    chain verification result + head hash
  audit/              a copy of the audit log files
  config/             every .bobnet/*.json in effect
  hooks.json          the hook wiring that was active
  ANCHOR.txt          the chain head hash and how to anchor it off-box

Exit 0 always; the report says what's wrong. This tool reports, it doesn't decide.
"""
from __future__ import annotations


import argparse
import re
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from audit import verify  # noqa: E402

PLUGIN_ROOT = HERE.parent.parent  # plugins/bobiverse

GUARDS = [
    # (script, what it does, controls it supports)
    (
        "busters.py",
        "Destructive / prod / privilege-grant commands need confirmation; catastrophic ones denied",
        "SOC 2 CC6.2, CC6.3, CC8.1 · HIPAA §164.308(a)(4)",
    ),
    (
        "suddar.py",
        "Credentials and secret files blocked from being written or committed",
        "SOC 2 CC6.1 · HIPAA §164.312(a)(2)(iv), §164.312(d)",
    ),
    (
        "prime_directive.py",
        "CI, prod infra, IAM, migrations, lockfiles, audit log protected",
        "SOC 2 CC8.1 · change management, separation of duties",
    ),
    (
        "phi_guard.py",
        "PII/PHI blocked from being written to files; flagged in commands",
        "HIPAA §164.502(b) minimum necessary, §164.312(c)(1) · SOC 2 C1.1",
    ),
    (
        "data_zones.py",
        "Reads of classified locations, tables and storage need approval or are denied",
        "HIPAA §164.308(a)(3)(ii)(A), §164.312(a)(1) · SOC 2 CC6.1, C1.1",
    ),
    (
        "egress.py",
        "Personal data blocked from web requests; outbound domains audited / allowlisted",
        "HIPAA §164.312(e)(1) · SOC 2 CC6.6, CC6.7",
    ),
    (
        "audit.py",
        "Hash-chained, append-only record of every tool call and gate decision",
        "HIPAA §164.312(b) · SOC 2 CC7.2, CC7.3",
    ),
    (
        "oracle_gate.py",
        "Expensive agent launches need a human decision",
        "cost control",
    ),
]


def load(p: Path):
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def wired_scripts() -> set[str]:
    h = load(PLUGIN_ROOT / "hooks" / "hooks.json") or {}
    out = set()
    for groups in (h.get("hooks") or {}).values():
        for g in groups:
            for x in g.get("hooks", []):
                cmd = x.get("command", "")
                for s, *_ in GUARDS:
                    # standalone ("busters.py") or via the gate dispatcher ("gate.py pre busters …")
                    if re.search(rf"(?<![\w-]){re.escape(s[:-3])}(\.py|\b)", cmd):
                        out.add(s)
    return out


def shield_installed() -> str:
    mp = PLUGIN_ROOT.parent / "bobnet-shield" / ".claude-plugin" / "plugin.json"
    return (
        "present in this marketplace (install: /plugin install bobnet-shield@bobiverse)"
        if mp.exists()
        else "not found beside this plugin"
    )


def report(project: Path) -> tuple[str, dict]:
    bn = Path(os.environ.get("BOBNET_DIR") or project / ".bobnet")
    wired = wired_scripts()
    cfg = {p.stem: load(p) for p in sorted(bn.glob("*.json"))} if bn.exists() else {}
    ok, n, msg = verify(bn / "audit")
    head = ""
    files = (
        sorted((bn / "audit").glob("audit-*.jsonl")) if (bn / "audit").exists() else []
    )
    if ok and files:
        last = files[-1].read_text().strip().splitlines()
        head = json.loads(last[-1])["hash"] if last else ""

    lines = [
        f"# Compliance posture — {project.name}",
        f"Generated {time.strftime('%Y-%m-%d %H:%M %Z')} by bobiverse compliance_check.py",
        "",
        "> A technical inventory of guards, not an attestation. Control references show which",
        "> requirement each guard *supports*; whether it satisfies that requirement is your",
        "> auditor's call, and HIPAA coverage of data sent to a model provider depends on your agreements.",
        "",
        "## Guards",
        "",
        "| Guard | Status | What it does | Supports |",
        "|---|---|---|---|",
    ]
    for s, what, ctl in GUARDS:
        status = "✅ wired" if s in wired else "❌ not wired"
        lines.append(f"| `{s}` | {status} | {what} | {ctl} |")

    lines += ["", "## Configuration in effect", ""]
    zones = cfg.get("data-zones") or {}
    nz = len(zones.get("zones", []))
    lines.append(
        f"- **Data zones:** {nz} configured · built-in defaults {'on' if zones.get('defaults', True) else 'off'}"
        + (
            ""
            if nz
            else "  ⚠ no project-specific zones — only generic phi/, pii/, HL7, DICOM, X12 paths are covered"
        )
    )
    eg = cfg.get("egress") or {}
    lines.append(
        f"- **Egress:** mode `{eg.get('mode', 'audit')}` · search `{eg.get('search', 'allow')}` · {len(eg.get('allow_domains', []))} extra allowed domains"
        + (
            "  ⚠ audit mode allows any domain (logged)"
            if eg.get("mode", "audit") == "audit"
            else ""
        )
    )
    pg = cfg.get("phi-guard") or {}
    lines.append(
        f"- **PHI guard:** medium-severity → `{pg.get('medium', 'ask')}` · {len(pg.get('allow_paths', []))} allowlisted paths"
    )
    au = cfg.get("audit") or {}
    lines.append(
        f"- **Audit log:** {'enabled' if au.get('enabled', True) else '❌ DISABLED'}"
    )
    mi = cfg.get("mission") or {}
    lines.append(
        f"- **Mission file:** {'enabled (redacted before save)' if mi.get('enabled', True) else 'disabled'}"
    )
    lines.append(
        f"- **SCUT notifications:** {'configured' if (cfg.get('scut') or os.environ.get('SCUT_NTFY_URL') or os.environ.get('SCUT_WEBHOOK_URL')) else 'not configured'} (always redacted)"
    )
    lines.append(f"- **Output redaction (bobnet-shield mod):** {shield_installed()}")

    lines += ["", "## Audit chain", "", f"- {'✅' if ok else '❌'} {msg}"]
    if head:
        lines.append(f"- Head hash: `{head}`")
    if not ok:
        lines.append(
            "- ⚠ The log was modified after it was written. Preserve the current files as-is and investigate before anything else touches them."
        )

    gaps = []
    if not nz:
        gaps.append(
            "Define project data zones (.bobnet/data-zones.json) for where regulated data actually lives — paths, tables, buckets."
        )
    if eg.get("mode", "audit") == "audit":
        gaps.append(
            "Egress is in audit mode. For regulated work, set mode `ask` or `deny` with an allowlist."
        )
    if not au.get("enabled", True):
        gaps.append("The audit log is disabled.")
    missing = [s for s, *_ in GUARDS if s not in wired]
    if missing:
        gaps.append(f"Guards not wired: {', '.join(missing)}.")
    gaps.append(
        "Ship the audit log off-box (WORM storage or your SIEM) and anchor the head hash; a local chain only proves the log wasn't edited by something that didn't recompute it."
    )
    gaps.append(
        "Confirm in writing that data sent to your model provider is covered for this use (e.g. a BAA) before any zone is set to `ask` rather than `deny`."
    )
    lines += ["", "## Gaps and next steps", ""] + [
        f"{i}. {g}" for i, g in enumerate(gaps, 1)
    ]

    return "\n".join(lines) + "\n", {
        "ok": ok,
        "entries": n,
        "msg": msg,
        "head": head,
        "bn": bn,
        "cfg": cfg,
    }


def export(project: Path, text: str, meta: dict) -> Path:
    bn: Path = meta["bn"]
    out = bn / "compliance" / time.strftime("%Y-%m-%d")
    if out.exists():
        out = out.with_name(out.name + time.strftime("-%H%M%S"))
    (out / "config").mkdir(parents=True, exist_ok=True)
    (out / "posture.md").write_text(text)
    (out / "audit-verify.txt").write_text(
        f"{'OK' if meta['ok'] else 'BROKEN'}\n{meta['msg']}\nhead: {meta['head']}\n"
    )
    if (bn / "audit").exists():
        shutil.copytree(
            bn / "audit", out / "audit", ignore=shutil.ignore_patterns(".lock")
        )
    for p in bn.glob("*.json"):
        shutil.copy2(p, out / "config" / p.name)
    hj = PLUGIN_ROOT / "hooks" / "hooks.json"
    if hj.exists():
        shutil.copy2(hj, out / "hooks.json")
    digest = hashlib.sha256()
    for f in sorted(out.rglob("*")):
        if f.is_file():
            digest.update(f.relative_to(out).as_posix().encode())
            digest.update(f.read_bytes())
    (out / "ANCHOR.txt").write_text(
        f"Audit chain head: {meta['head'] or '(empty)'}\n"
        f"Evidence pack sha256 (all files above, path-ordered): {digest.hexdigest()}\n\n"
        "To make this tamper-evident beyond this machine, record both values somewhere you\n"
        "control and Claude can't write: a signed git tag, a ticket, a WORM bucket object,\n"
        "your SIEM. Later, re-run the export and compare.\n"
    )
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default=os.environ.get("CLAUDE_PROJECT_DIR") or ".")
    ap.add_argument("--export", action="store_true")
    a = ap.parse_args()
    project = Path(a.project).resolve()
    text, meta = report(project)
    print(text)
    if a.export:
        print(f"Evidence pack written to: {export(project, text, meta)}")
