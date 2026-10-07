#!/usr/bin/env python3
"""
busters.py — PreToolUse(Bash). The kill switch.

Three tiers:
  KILL  : commands that are catastrophic in any context → deny, always.
  ASK   : destructive / irreversible / production-flavored → force a permission
          prompt even in auto-accept mode (Riker's confirmation gate, enforced).
  allow : everything else.

Disarm the ASK tier for a window with `/disarm` (writes .bobnet/busters.disarmed
with an expiry). KILL tier cannot be disarmed.
Config overrides: .bobnet/busters.json → {"ask_extra": [...regex], "allow": [...regex]}
"""

import re
import time
from bobnet import read_event, pre_tool_decision, allow, bobnet_dir, load_config

ev = read_event()
if ev.tool != "Bash":
    allow()
cmd = ev.command
if not cmd:
    allow()

KILL = [
    r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f|-[a-zA-Z]*f[a-zA-Z]*r)[a-zA-Z]*\s+(/|~|\$HOME|\*|\.\.?)(\s|$|/\*)",  # rm -rf / ~ * .
    r"\bmkfs(\.\w+)?\b",
    r"\bdd\s+.*\bof=/dev/(sd|nvme|disk|hd)",
    r">\s*/dev/(sd|nvme|hd)[a-z0-9]*\b",
    r"\bchmod\s+(-R\s+)?[0-7]*777\s+/(\s|$)",
    r":\(\)\s*\{\s*:\|:&\s*\};:",  # fork bomb
    r"\bgit\s+push\s+.*--force.*\s(main|master|production|prod)\b",
    r"\bgit\s+push\s+.*\s(main|master|production|prod)\s+.*--force",
]

ASK = [
    # filesystem
    r"\brm\s+-[a-zA-Z]*r",  # any recursive rm
    r"\brm\s+-[a-zA-Z]*f",  # any forced rm
    r"\bfind\b.*-delete\b",
    r"\bshred\b",
    r"\btruncate\b",
    # git history / remote
    r"\bgit\s+push\b.*(--force|-f\b|\+\w)",
    r"\bgit\s+(reset\s+--hard|clean\s+-[a-zA-Z]*f|branch\s+-D|checkout\s+--\s+\.)",
    r"\bgit\s+push\s+.*--delete",
    r"\bgit\s+filter-(branch|repo)\b",
    # databases
    r"\b(DROP|TRUNCATE)\s+(TABLE|DATABASE|SCHEMA|INDEX)\b",
    r"\bDELETE\s+FROM\b(?![^;]*\bWHERE\b)",  # DELETE without WHERE
    r"\bUPDATE\s+\w+\s+SET\b(?![^;]*\bWHERE\b)",
    r"\b(psql|mysql|sqlite3|mongo(sh)?)\b.*\b(drop|truncate)\b",
    # infra / IaC — apply is always a human decision; state surgery doubly so (Charles's rules)
    r"\b(terraform|tofu)\s+(destroy|apply)\b",
    r"\b(terraform|tofu)\s+state\s+(rm|mv|push|replace-provider)\b",
    r"\b(terraform|tofu)\s+(import|force-unlock|taint|untaint)\b",
    r"\b(terraform|tofu)\s+workspace\s+delete\b",
    r"\bpulumi\s+(destroy|up|refresh\s+.*--yes|state\s+(delete|unprotect))",
    r"\bcdk\s+(deploy|destroy)\b",
    r"\baws\s+cloudformation\s+(deploy|delete-stack|update-stack|create-stack)\b",
    r"\baz\s+(deployment|stack)\s+\S+\s+(create|delete|what-if\s+.*--confirm)",
    r"\baz\s+group\s+delete\b",
    # privilege grants weigh the same as deletes
    r"\baz\s+(role\s+assignment\s+create|ad\s+(app|sp)\s+credential\s+reset|keyvault\s+set-policy)\b",
    r"\baws\s+iam\s+(attach|put)-(role|user|group)-policy\b",
    r"\baws\s+iam\s+(create-access-key|create-policy-version|update-assume-role-policy|add-user-to-group)\b",
    r"\baws\s+(kms\s+put-key-policy|s3api\s+put-bucket-policy|s3api\s+put-public-access-block|sts\s+assume-role)\b",
    r"\bgcloud\s+(projects|iam)\s+.*add-iam-policy-binding\b",
    r"\bkubectl\s+(create|apply)\b.*\b(clusterrolebinding|rolebinding)\b",
    r"\bkubectl\s+(delete|drain|cordon|replace\s+--force)",
    r"\bhelm\s+(uninstall|delete|rollback)\b",
    r"\bdocker\s+(system\s+prune|volume\s+(rm|prune)|rmi|container\s+prune)",
    r"\bdocker\s+compose\s+down\s+.*(-v|--volumes)",
    r"\baws\s+\S+\s+(delete|terminate|remove|purge)[-\w]*",
    r"\baws\s+s3\s+(rm|rb)\b",
    r"\bgcloud\s+.*\bdelete\b",
    r"\baz\s+.*\bdelete\b",
    r"\b(systemctl|service)\s+(stop|disable|mask)\b",
    # secrets / identity
    r"\b(aws|gcloud|az|vault|op)\b.*\b(rotate|revoke)\b",
    r"\bgh\s+(repo\s+delete|secret\s+(set|delete|remove))",
    # package publish
    r"\bnpm\s+(publish|unpublish|deprecate)\b",
    r"\b(twine\s+upload|cargo\s+publish|gem\s+push|poetry\s+publish)\b",
    # anything that smells like prod
    r"\b(prod|production)\b.*\b(deploy|apply|migrate|release|rollout)\b",
    r"\b(deploy|apply|migrate|release|rollout)\b.*\b(prod|production)\b",
    # privilege
    r"\bsudo\s+(rm|dd|mkfs|chmod|chown|systemctl|shutdown|reboot)\b",
    r"\b(shutdown|reboot|halt|poweroff)\b",
    r"\bcrontab\s+-r\b",
    r"\bchown\s+-R\b",
    r"\bchmod\s+-R\b",
]

cfg = load_config(ev, "busters", {"ask_extra": [], "allow": []})
ASK += cfg.get("ask_extra", [])
ALLOWLIST = cfg.get("allow", [])

# Split heredoc bodies out of the command. Text fed to a heredoc is usually DATA
# (a file being written, a script's string literals), so a KILL pattern found only
# there is downgraded to ASK — the human still sees it, but a README that mentions
# `mkfs` doesn't get hard-denied. Everything outside heredocs is matched as-is.
HEREDOC = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?[^\n]*\n(.*?)\n\s*\1\s*(?:\n|$)", re.S)
heredoc_bodies = [m.group(2) for m in HEREDOC.finditer(cmd)]
command_only = HEREDOC.sub(" <<HEREDOC_BODY_REMOVED ", cmd)

flat = " ".join(command_only.split())
flat_data = " ".join(" ".join(heredoc_bodies).split())

for pat in ALLOWLIST:
    if re.search(pat, flat, re.I):
        allow()

for pat in KILL:
    if re.search(pat, flat, re.I):
        pre_tool_decision(
            "deny",
            "BUSTERS: catastrophic command pattern — denied unconditionally. "
            f"Matched /{pat}/. This tier cannot be disarmed. If you really mean this, "
            "the human runs it by hand outside Claude.",
        )
for pat in KILL:
    if flat_data and re.search(pat, flat_data, re.I):
        pre_tool_decision(
            "ask",
            f"BUSTERS: a catastrophic pattern (/{pat}/) appears inside heredoc CONTENT, not the command itself. "
            "That's usually data (a file being written, a script's strings) — but if this heredoc is piped to a shell "
            "or interpreter, it will execute. Read the heredoc before approving.",
        )

# Disarm window check
disarm = bobnet_dir(ev) / "busters.disarmed"
try:
    if disarm.exists():
        exp = float(disarm.read_text().strip() or "0")
        if time.time() < exp:
            allow()
        disarm.unlink()
except Exception:
    pass

for pat in ASK:
    if re.search(pat, flat, re.I):
        pre_tool_decision(
            "ask",
            "BUSTERS armed: this command is destructive, irreversible, or production-flavored "
            f"(matched /{pat}/). Riker's rule: explicit confirmation required. "
            "Review the exact command before approving. To skip these prompts for 15 min, run /disarm.",
        )

allow()
