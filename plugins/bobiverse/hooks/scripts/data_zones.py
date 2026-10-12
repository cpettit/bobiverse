#!/usr/bin/env python3
"""
data_zones.py — PreToolUse(Read|Grep|Glob|NotebookRead|Edit|Write|MultiEdit|NotebookEdit|Bash|mcp__.*).
Data classification zones: stop regulated data before it reaches the model.

Once a Bob reads a file, its contents are in the model's context and have left
your environment. The only place to stop that is before the read. A zone names
where regulated data lives — paths, database tables, storage URIs — and what
happens when a tool reaches for it: "ask" (a human decides) or "deny".

  .bobnet/data-zones.json
  {
    "zones": [
      {"name": "patient extracts", "classification": "PHI", "mode": "deny",
       "paths": ["data/phi/**", "**/*.hl7"],
       "tables": ["patients", "encounters", "claims"],
       "uris": ["s3://acme-phi-*", "az://phistore/*"]}
    ],
    "defaults": true
  }

Built-in defaults (mode "ask", turn off with "defaults": false): directories
named phi/ or pii/, HL7v2 (*.hl7), DICOM (*.dcm), C-CDA (*.ccda, *.cda) and
X12 claims (*.835, *.837) files.

Paths are globs (`**` crosses directories) matched against the path as given
and relative to the project root. Tables match SQL in Bash commands and in any
MCP tool's input (FROM / JOIN / INTO / UPDATE / TABLE <name>, schema-qualified
or quoted). URIs are globs matched against tokens in commands and MCP input.
"""

import fnmatch
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bobnet import allow, load_config, pre_tool_decision, read_event  # noqa: E402

DEFAULT_ZONE = {
    "name": "common regulated-data locations",
    "classification": "PHI/PII",
    "mode": "ask",
    "paths": [
        "**/phi/**",
        "**/pii/**",
        "phi/**",
        "pii/**",
        "**/*.hl7",
        "**/*.dcm",
        "**/*.ccda",
        "**/*.cda",
        "**/*.835",
        "**/*.837",
    ],
    "tables": [],
    "uris": [],
}

ev = read_event()
cfg = load_config(ev, "data-zones", {"zones": [], "defaults": True})
zones = list(cfg.get("zones", []))
if cfg.get("defaults", True):
    zones.append(DEFAULT_ZONE)
if not zones:
    allow()

root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or ev.cwd or ".").resolve()


def glob_rx(g: str) -> re.Pattern:
    """Glob → regex: ** spans directories, * stays within one."""
    out, i = "", 0
    while i < len(g):
        if g[i : i + 3] == "**/":
            out += "(?:.*/)?"
            i += 3
        elif g[i : i + 2] == "**":
            out += ".*"
            i += 2
        elif g[i] == "*":
            out += "[^/]*"
            i += 1
        elif g[i] == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(g[i])
            i += 1
    return re.compile(rf"^{out}$", re.IGNORECASE)


def path_forms(p: str) -> list[str]:
    p = p.strip().strip("'\"")
    if not p:
        return []
    forms = {p, p.lstrip("./")}
    try:
        ap = Path(p) if os.path.isabs(p) else (root / p)
        ap = ap.resolve()
        forms.add(str(ap))
        try:
            forms.add(str(ap.relative_to(root)))
        except ValueError:
            pass
    except Exception:
        pass
    return [f.replace("\\", "/") for f in forms if f]


def path_hits(p: str, zone: dict) -> str | None:
    for g in zone.get("paths", []):
        rx = glob_rx(g)
        for f in path_forms(p):
            if rx.match(f):
                return g
    return None


def table_hits(text: str, zone: dict) -> str | None:
    for t in zone.get("tables", []):
        name = re.escape(t)
        rx = rf"(?i)\b(from|join|into|update|table|truncate|describe|desc)\s+(?:[`\"\[]?\w+[`\"\]]?\.)*[`\"\[]?{name}[`\"\]]?\b"
        if re.search(rx, text):
            return t
    return None


def uri_hits(text: str, zone: dict) -> str | None:
    tokens = re.findall(r"[\w+.-]+://[^\s'\"`)]+", text)
    for g in zone.get("uris", []):
        for tok in tokens:
            if fnmatch.fnmatchcase(tok.lower(), g.lower()):
                return g
    return None


def strings(v) -> list[str]:
    """Every string value in an MCP tool's input, unescaped (JSON-encoding would hide quoted names)."""
    if isinstance(v, str):
        return [v]
    if isinstance(v, dict):
        return [s for x in v.values() for s in strings(x)]
    if isinstance(v, (list, tuple)):
        return [s for x in v for s in strings(x)]
    return []


def decide(zone: dict, what: str):
    mode = zone.get("mode", "ask")
    label = zone.get("classification", "regulated")
    name = zone.get("name", "unnamed zone")
    msg = (
        f"DATA ZONE ({label}): {what} is inside '{name}'. "
        "Reading it puts its contents in the model's context, outside your environment. "
    )
    if mode == "deny":
        pre_tool_decision(
            "deny",
            msg
            + "This zone is deny-only; work with a de-identified extract or synthetic data instead.",
        )
    pre_tool_decision(
        "ask",
        msg
        + "Approve only if this data is covered for this use (e.g. a BAA) or is de-identified.",
    )


i = ev.input if isinstance(ev.input, dict) else {}

# --- file tools ---
if ev.tool in (
    "Read",
    "NotebookRead",
    "Edit",
    "Write",
    "MultiEdit",
    "NotebookEdit",
    "Grep",
    "Glob",
):
    candidates = [ev.file_path, i.get("path", "")]
    if ev.tool == "Glob" and i.get("pattern"):
        base = i.get("path") or ""
        candidates.append(os.path.join(base, i["pattern"]) if base else i["pattern"])
    for c in filter(None, candidates):
        for z in zones:
            g = path_hits(str(c), z)
            if g:
                decide(z, f"`{c}` (matches {g})")
    allow()

# --- shell and MCP tools: paths, tables, URIs in the command / input ---
if ev.tool == "Bash" or ev.tool.startswith("mcp__"):
    text = ev.command if ev.tool == "Bash" else "\n".join(strings(i))
    tokens = re.findall(r"[\w./~@:+-]+", text)
    for z in zones:
        for tok in tokens:
            if "/" in tok or "." in tok:
                g = path_hits(tok, z)
                if g:
                    decide(z, f"`{tok}` (matches {g})")
        t = table_hits(text, z)
        if t:
            decide(z, f"table `{t}`")
        u = uri_hits(text, z)
        if u:
            decide(z, f"location matching `{u}`")
    allow()

allow()
