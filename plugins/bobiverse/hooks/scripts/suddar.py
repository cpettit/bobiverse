#!/usr/bin/env python3
"""
suddar.py — PreToolUse(Write|Edit|MultiEdit|NotebookEdit) + PreToolUse(Bash for git commit).
Deep scan for secrets before they touch disk or history.

Denies when:
  - the content being written matches a known credential pattern, or
  - the target path is a secret-bearing file (.env, *.pem, id_rsa, ...).
For `git commit`, runs gitleaks/trufflehog on staged changes if either is installed.

Config: .bobnet/suddar.json → {"allow_paths": [regex], "allow_patterns": [regex]}
Placeholders like "xxxx", "<your-key>", "example" are tolerated.
"""
import re
import shutil
import subprocess
from bobnet import read_event, pre_tool_decision, allow, load_config

ev = read_event()
cfg = load_config(ev, "suddar", {"allow_paths": [r"\.example$", r"\.sample$", r"\.template$", r"(^|/)tests?/fixtures/"],
                                 "allow_patterns": []})

SECRET_PATTERNS = [
    ("AWS access key",        r"\b(AKIA|ASIA|AGPA|AIDA|AROA|ANPA|ANVA)[A-Z0-9]{16}\b"),
    ("AWS secret key",        r"(?i)aws.{0,20}secret.{0,20}[=:]\s*['\"]?[A-Za-z0-9/+=]{40}\b"),
    ("GitHub token",          r"\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b|\bgithub_pat_[A-Za-z0-9_]{60,}\b"),
    ("GitLab token",          r"\bglpat-[A-Za-z0-9\-_]{20,}\b"),
    ("Slack token",           r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    ("Slack webhook",         r"https://hooks\.slack\.com/services/T[A-Z0-9]+/B[A-Z0-9]+/[A-Za-z0-9]+"),
    ("Stripe key",            r"\b(sk|rk)_(live|test)_[A-Za-z0-9]{20,}\b"),
    ("OpenAI/Anthropic key",  r"\bsk-(ant-)?[A-Za-z0-9\-_]{20,}\b"),
    ("Google API key",        r"\bAIza[0-9A-Za-z\-_]{35}\b"),
    ("Azure/GUID-secret",     r"(?i)client_?secret\s*[=:]\s*['\"]?[A-Za-z0-9~._\-]{30,}"),
    ("Private key block",     r"-----BEGIN (RSA |EC |DSA |OPENSSH |PGP |ENCRYPTED )?PRIVATE KEY( BLOCK)?-----"),
    ("JWT",                   r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    ("Twilio",                r"\bSK[0-9a-fA-F]{32}\b"),
    ("SendGrid",              r"\bSG\.[A-Za-z0-9_-]{22}\.[A-Za-z0-9_-]{43}\b"),
    ("npm token",             r"\bnpm_[A-Za-z0-9]{36}\b"),
    ("PyPI token",            r"\bpypi-AgEIcHlwaS5vcmc[A-Za-z0-9\-_]{50,}\b"),
    ("Hashicorp Vault token", r"\b(hvs|hvb|s)\.[A-Za-z0-9]{24,}\b"),
    ("DB connection string",  r"(?i)\b(postgres(ql)?|mysql|mongodb(\+srv)?|redis|amqp)://[^:\s/]+:[^@\s]{6,}@"),
    ("Generic password",      r"(?i)\b(password|passwd|pwd)\s*[=:]\s*['\"][^'\"\s]{8,}['\"]"),
    ("Generic API key",       r"(?i)\b(api[_-]?key|api[_-]?secret|access[_-]?token|auth[_-]?token|secret[_-]?key)\s*[=:]\s*['\"][A-Za-z0-9\-_./+=]{16,}['\"]"),
]

SECRET_PATHS = [
    r"(^|/)\.env(\.[\w-]+)?$",
    r"\.(pem|key|p12|pfx|jks|keystore)$",
    r"(^|/)id_(rsa|dsa|ecdsa|ed25519)(\.pub)?$",
    r"(^|/)\.(aws|ssh|gnupg)/",
    r"(^|/)(credentials|secrets?)\.(json|ya?ml|toml|ini)$",
    r"(^|/)\.npmrc$", r"(^|/)\.pypirc$", r"(^|/)\.netrc$",
    r"(^|/)kubeconfig$", r"(^|/)\.kube/config$",
    r"(^|/)terraform\.tfstate(\.backup)?$",
    r"(^|/)\.terraform/",
]

PLACEHOLDER = re.compile(r"(?i)(xxxx|\*\*\*\*|<[^>]*>|your[-_ ]?(key|token|secret|password)|example|placeholder|changeme|redacted|dummy|fake|0{8,}|1234567890)")


def placeholderish(s: str) -> bool:
    return bool(PLACEHOLDER.search(s))


def redact(s: str) -> str:
    s = s.strip()
    if len(s) <= 8:
        return "****"
    return f"{s[:4]}…{s[-4:]}"


def path_allowed(p: str) -> bool:
    return any(re.search(a, p) for a in cfg["allow_paths"])


def scan_text(text: str):
    hits = []
    for name, pat in SECRET_PATTERNS:
        if any(re.search(a, pat) for a in cfg["allow_patterns"]):
            continue
        for m in re.finditer(pat, text):
            frag = m.group(0)
            if placeholderish(frag):
                continue
            # find line number
            line = text.count("\n", 0, m.start()) + 1
            hits.append((name, line, redact(frag)))
            if len(hits) >= 5:
                return hits
    return hits


# ---- Write / Edit family ----
if ev.tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
    path = ev.file_path
    if path and not path_allowed(path):
        for pat in SECRET_PATHS:
            if re.search(pat, path):
                pre_tool_decision("deny",
                    f"SUDDAR: refusing to write secret-bearing file `{path}` (matched /{pat}/). "
                    "Secrets belong in a secret manager or an untracked local file the human creates. "
                    "If this is a template, name it *.example and use placeholders.")
    hits = scan_text(ev.written_text)
    if hits:
        lines = "\n".join(f"  - {n} at line {ln}: {r}" for n, ln, r in hits)
        pre_tool_decision("deny",
            f"SUDDAR: credential-shaped content detected in write to `{path or '(unknown)'}`:\n{lines}\n"
            "Not writing it. Replace with an env-var reference or a placeholder like <YOUR_KEY>. "
            "If this is a false positive, add a pattern to .bobnet/suddar.json allow_patterns.")
    allow()

# ---- git commit: run an external scanner on staged changes if available ----
if ev.tool == "Bash" and re.search(r"\bgit\s+commit\b", ev.command):
    tool = None
    if shutil.which("gitleaks"):
        tool = ["gitleaks", "protect", "--staged", "--no-banner", "--redact", "--exit-code", "9"]
    elif shutil.which("trufflehog"):
        tool = ["trufflehog", "git", "file://.", "--since-commit", "HEAD", "--only-verified", "--fail", "--no-update"]
    if tool:
        try:
            r = subprocess.run(tool, cwd=ev.cwd, capture_output=True, text=True, timeout=60)
            if r.returncode not in (0,):
                out = (r.stdout + r.stderr).strip()[-1500:]
                pre_tool_decision("deny",
                    f"SUDDAR: {tool[0]} found secrets in staged changes. Commit blocked.\n{out}\n"
                    "Unstage/redact the secret, then commit again.")
        except Exception:
            pass  # scanner trouble is not a reason to block commits
    allow()

allow()
