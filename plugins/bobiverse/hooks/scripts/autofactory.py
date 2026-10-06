#!/usr/bin/env python3
"""
autofactory.py — PostToolUse(Write|Edit|MultiEdit).
The printers run themselves: format + lint the file that was just touched, and
feed any failures straight back to Claude (exit 2 → stderr becomes feedback).

Only runs tools that are already installed in the project/environment. Never
installs anything. Formatters write in place; linters report.
Config: .bobnet/autofactory.json → {"enabled": true, "format": true, "lint": true, "skip": [regex]}
"""
import os
import re
import shutil
import subprocess
from pathlib import Path
from bobnet import read_event, allow, feedback, load_config, marker, touch

ev = read_event()
cfg = load_config(ev, "autofactory", {"enabled": True, "format": True, "lint": True, "skip": [r"(^|/)node_modules/", r"(^|/)vendor/", r"(^|/)dist/", r"(^|/)build/", r"\.min\.(js|css)$", r"(^|/)\.bobnet/"]})
if not cfg.get("enabled", True):
    allow()

path = ev.file_path
if not path or not os.path.isfile(path):
    allow()
if any(re.search(s, path) for s in cfg["skip"]):
    allow()

# Mark the session as "did real work" for the Bobnet log hook.
touch(marker(ev, "dirty"))

ext = Path(path).suffix.lower()
cwd = ev.cwd
root = os.environ.get("CLAUDE_PROJECT_DIR") or cwd


def have(*names):
    return next((n for n in names if shutil.which(n)), None)


def has_file(*names):
    return any(Path(root, n).exists() for n in names)


def run(cmd, timeout=45):
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return 124, f"timeout running {' '.join(cmd)}"
    except Exception as e:
        return 1, str(e)


formatters, linters = [], []

if ext == ".py":
    if have("ruff"):
        formatters.append(["ruff", "format", path])
        linters.append(["ruff", "check", path])
    else:
        if have("black"): formatters.append(["black", "-q", path])
        if have("flake8"): linters.append(["flake8", path])
    if have("mypy") and has_file("mypy.ini", "pyproject.toml", "setup.cfg"):
        linters.append(["mypy", "--no-error-summary", path])

elif ext in (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".json", ".css", ".scss", ".md", ".yaml", ".yml"):
    if has_file("node_modules/.bin/prettier") or have("prettier"):
        formatters.append(["npx", "--no-install", "prettier", "--write", "--log-level", "warn", path])
    if ext in (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs") and (has_file("node_modules/.bin/eslint") or have("eslint")):
        linters.append(["npx", "--no-install", "eslint", "--no-warn-ignored", path])
    if ext in (".ts", ".tsx") and has_file("tsconfig.json") and has_file("node_modules/.bin/tsc"):
        linters.append(["npx", "--no-install", "tsc", "--noEmit", "-p", "tsconfig.json"])

elif ext == ".go":
    if have("gofmt"): formatters.append(["gofmt", "-w", path])
    if have("go"): linters.append(["go", "vet", "./..."])

elif ext == ".rs":
    if have("rustfmt"): formatters.append(["rustfmt", path])
    if have("cargo"): linters.append(["cargo", "check", "-q"])

elif ext in (".sh", ".bash"):
    if have("shfmt"): formatters.append(["shfmt", "-w", path])
    if have("shellcheck"): linters.append(["shellcheck", path])

elif ext == ".tf":
    if have("terraform"):
        formatters.append(["terraform", "fmt", path])
        linters.append(["terraform", "validate", "-no-color"])
    if have("tflint"): linters.append(["tflint", "--filter", path])

elif ext in (".yaml", ".yml"):
    if have("yamllint"): linters.append(["yamllint", "-f", "parsable", path])

elif ext == "" and Path(path).name == "Dockerfile" or ext == ".dockerfile":
    if have("hadolint"): linters.append(["hadolint", path])

problems = []
if cfg.get("format", True):
    for f in formatters:
        code, out = run(f)
        if code not in (0,) and out:
            problems.append(f"[format] {' '.join(f[:2])}:\n{out[-800:]}")
if cfg.get("lint", True):
    for l in linters:
        code, out = run(l)
        if code != 0 and out:
            problems.append(f"[lint] {' '.join(l[:2])}:\n{out[-1200:]}")

if problems:
    feedback("AUTOFACTORY: the printers flagged your last edit to "
             f"`{path}`. Fix before moving on:\n\n" + "\n\n".join(problems))
allow()
