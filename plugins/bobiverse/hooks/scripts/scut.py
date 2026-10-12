#!/usr/bin/env python3
"""
scut.py — Notification, and called from the Stop hook. Subspace comms.

Pushes a short message to the human's phone/desk when Claude needs them
(permission prompt, idle waiting for input) or when a long session finishes.
Silent no-op unless configured.

Config (env vars or .bobnet/scut.json):
  SCUT_NTFY_URL      e.g. https://ntfy.sh/your-private-topic   (recommended; self-hostable)
  SCUT_WEBHOOK_URL   any JSON webhook (Slack/Discord/Mattermost incoming webhook)
  SCUT_MIN_SECONDS   only ping on Stop if the session ran longer than this (default 300)
  SCUT_NOTIFY        "1" to ping on Notification events too (default 1)

Uses only stdlib; no dependencies.
"""

import json
import os
import sys
import time
import urllib.request
from pathlib import Path
from bobnet import read_event, allow, load_config, bobnet_dir

mode = sys.argv[1] if len(sys.argv) > 1 else "notification"
ev = read_event()
cfg = load_config(ev, "scut", {})
ntfy = os.environ.get("SCUT_NTFY_URL") or cfg.get("ntfy_url")
webhook = os.environ.get("SCUT_WEBHOOK_URL") or cfg.get("webhook_url")
if not (ntfy or webhook):
    allow()

project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or ev.cwd).name
started = bobnet_dir(ev) / f"start-{ev.session}.marker"

if mode == "stop":
    min_s = float(os.environ.get("SCUT_MIN_SECONDS") or cfg.get("min_seconds", 300))
    try:
        elapsed = time.time() - started.stat().st_mtime
    except Exception:
        elapsed = 0
    if elapsed < min_s:
        allow()
    title, body = (
        f"Bob · {project}",
        f"Session finished after {int(elapsed // 60)} min. Awaiting orders.",
    )
else:
    if (os.environ.get("SCUT_NOTIFY") or str(cfg.get("notify", "1"))) != "1":
        allow()
    kind = ev.notification_type or "attention"
    msg = (ev.message or "").strip()[:200] or "Claude needs your input."
    title, body = f"Bob · {project} · {kind}", msg

# Notifications leave for a third party (ntfy, Slack, Discord). Nothing personal
# goes with them: redact, and if anything was found, say so instead of sending it.
try:
    from pii import redact

    pii_cfg = load_config(ev, "pii", {})
    title, t_hits = redact(title, pii_cfg)
    body, b_hits = redact(body, pii_cfg)
    if t_hits or b_hits:
        body = f"{body}\n(personal data redacted from this notification)"
except Exception:
    body = (
        "Claude needs your attention."  # if the scrubber fails, send nothing specific
    )


def post(url, data, headers):
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=5) as r:
        r.read()


try:
    if ntfy:
        post(
            ntfy,
            body.encode(),
            {"Title": title, "Tags": "satellite", "Priority": "default"},
        )
    if webhook:
        post(
            webhook,
            json.dumps(
                {"text": f"*{title}*\n{body}", "content": f"**{title}**\n{body}"}
            ).encode(),
            {"Content-Type": "application/json"},
        )
except Exception:
    pass
allow()
