#!/usr/bin/env python3
"""
egress.py — PreToolUse(WebFetch|WebSearch|Bash).
Controls what leaves for the web, and never lets personal data ride along.

Two checks, in order:
 1. PII in the request — a URL, a search query, a curl body. HIGH hit → deny,
    MEDIUM → ask. Always on; data in a query string ends up in someone's logs.
 2. Domain policy — where WebFetch and curl/wget/http may go:
      "audit" (default): allow everything, record it in the audit log
      "ask":   domains not on the allowlist need a human's OK
      "deny":  only allowlisted domains are reachable
    WebSearch has its own switch: "search": "allow" | "ask" | "deny".

  .bobnet/egress.json
  {"mode": "ask", "allow_domains": ["internal.acme.com"], "search": "allow"}

allow_domains extends the built-in list of documentation and package hosts
(set "defaults": false to start from empty). A domain matches itself and its
subdomains.
"""
from __future__ import annotations


import re
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bobnet import allow, load_config, pre_tool_decision, read_event  # noqa: E402
from pii import scan, summarize  # noqa: E402

DEFAULT_DOMAINS = [
    "github.com",
    "githubusercontent.com",
    "gitlab.com",
    "pypi.org",
    "pythonhosted.org",
    "npmjs.com",
    "npmjs.org",
    "crates.io",
    "rubygems.org",
    "pkg.go.dev",
    "registry.terraform.io",
    "developer.hashicorp.com",
    "opentofu.org",
    "learn.microsoft.com",
    "docs.aws.amazon.com",
    "cloud.google.com",
    "docs.python.org",
    "developer.mozilla.org",
    "stackoverflow.com",
    "wikipedia.org",
    "docs.claude.com",
    "code.claude.com",
    "anthropic.com",
    "hhs.gov",
    "cms.gov",
    "nist.gov",
    "cisecurity.org",
    "aicpa-cima.com",
]

ev = read_event()
cfg = load_config(
    ev,
    "egress",
    {"mode": "audit", "allow_domains": [], "search": "allow", "defaults": True},
)
pii_cfg = load_config(ev, "pii", {})
domains = [d.lower().lstrip(".") for d in cfg.get("allow_domains", [])]
if cfg.get("defaults", True):
    domains += DEFAULT_DOMAINS


def allowed(host: str) -> bool:
    host = host.lower().split(":")[0]
    return any(host == d or host.endswith("." + d) for d in domains)


def pii_check(text: str, what: str):
    hits = scan(text, pii_cfg)
    if not hits:
        return
    high = [h for h in hits if h.severity == "high"]
    pre_tool_decision(
        "deny" if high else "ask",
        f"EGRESS: the {what} contains personal data:\n{summarize(high or hits, text)}\n"
        "Requests are logged by whoever receives them. Remove the identifiers before sending.",
    )


def domain_check(url: str):
    host = urlparse(url if "://" in url else "https://" + url).hostname or ""
    if not host or allowed(host):
        return
    mode = cfg.get("mode", "audit")
    if mode == "deny":
        pre_tool_decision(
            "deny",
            f"EGRESS: `{host}` is not on the allowed-domains list (.bobnet/egress.json, mode deny).",
        )
    if mode == "ask":
        pre_tool_decision(
            "ask",
            f"EGRESS: `{host}` is not on the allowed-domains list. Approve this one request, or add the domain to .bobnet/egress.json.",
        )
    # audit mode: allowed through; the PostToolUse audit hook records the call


i = ev.input if isinstance(ev.input, dict) else {}

if ev.tool == "WebFetch":
    url = str(i.get("url", ""))
    pii_check(url + "\n" + str(i.get("prompt", "")), "request")
    domain_check(url)
    allow()

if ev.tool == "WebSearch":
    q = str(i.get("query", ""))
    pii_check(q, "search query")
    s = cfg.get("search", "allow")
    if s == "deny":
        pre_tool_decision(
            "deny",
            "EGRESS: web search is disabled for this project (.bobnet/egress.json).",
        )
    if s == "ask":
        pre_tool_decision("ask", f"EGRESS: web search for “{q[:80]}”. Approve?")
    allow()

if ev.tool == "Bash":
    cmd = ev.command
    if re.search(
        r"\b(curl|wget|http|https|httpie|xh|nc|ncat|Invoke-WebRequest|iwr)\b", cmd
    ):
        pii_check(cmd, "outbound command")
        for url in re.findall(r"https?://[^\s'\"`)]+", cmd):
            domain_check(url)
    allow()

allow()
