#!/usr/bin/env python3
"""
pii.py — shared PII/PHI detector for the Bobiverse compliance hooks.

Stdlib only. Every detector pairs a pattern with a validator so it doesn't
fire on every 9-digit number:

  HIGH    (identifiers that are personal on their own — deny by default)
    ssn          US Social Security number; SSA-invalid ranges rejected
    card         payment card number; Luhn-checked, 13–19 digits, known IIN prefixes
    npi          National Provider Identifier; Luhn with the 80840 prefix
    mbi          Medicare Beneficiary Identifier (CMS 11-char format)
    dea          DEA registration number; checksum-validated
    mrn          medical record / member / patient ID — only next to a keyword
                 ("MRN", "member id", "patient id", …) or matching a configured regex

  MEDIUM  (personal in combination — ask by default)
    dob_name     a date of birth next to a name-ish field
    icd10        an ICD-10-CM code next to a diagnosis keyword
    phone_name   a phone number next to a name-ish field
    email_bulk   five or more email addresses in one blob (a contact export)

Known test values (123-45-6789, 4111 1111 1111 1111, …) are ignored, as are
values inside obvious placeholders. Config: .bobnet/pii.json
  {
    "extra_id_patterns": [{"name": "member_id", "regex": "\\bMBR\\d{9}\\b", "severity": "high"}],
    "allow_values": ["555-12-3456"],
    "disable": ["email_bulk"]
  }
"""

import re
from dataclasses import dataclass

# ---------------------------------------------------------------- types


@dataclass(frozen=True)
class Hit:
    kind: str
    severity: str  # "high" | "medium"
    start: int
    end: int
    value: str

    def masked(self) -> str:
        return mask(self.value)

    def line(self, text: str) -> int:
        return text.count("\n", 0, self.start) + 1


def mask(v: str) -> str:
    digits = re.sub(r"\D", "", v)
    if len(digits) >= 4:
        return f"•••{digits[-4:]}" if len(digits) > 6 else "••••"
    return "••••"


# ---------------------------------------------------------------- validators


def luhn(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = ord(ch) - 48
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


def ssn_valid(area: str, group: str, serial: str) -> bool:
    a = int(area)
    if a == 0 or a == 666 or a >= 900:
        return False
    if group == "00" or serial == "0000":
        return False
    return True


CARD_PREFIX = re.compile(r"^(4|5[1-5]|2[2-7]|3[47]|6(011|5|4[4-9])|3(0[0-5]|[68])|35)")


def card_valid(digits: str) -> bool:
    return (
        13 <= len(digits) <= 19
        and bool(CARD_PREFIX.match(digits))
        and luhn(digits)
        and len(set(digits)) > 2
    )


def npi_valid(digits: str) -> bool:
    return len(digits) == 10 and digits[0] in "12" and luhn("80840" + digits)


def dea_valid(s: str) -> bool:
    s = s.upper()
    if not re.fullmatch(r"[ABCDEFGHJKLMPRSTUX][A-Z9]\d{7}", s):
        return False
    d = [int(c) for c in s[2:]]
    check = (d[0] + d[2] + d[4] + 2 * (d[1] + d[3] + d[5])) % 10
    return check == d[6]


# ---------------------------------------------------------------- patterns

SSN = re.compile(r"(?<![\d-])(\d{3})[- ](\d{2})[- ](\d{4})(?![\d-])")
SSN_LABELED = re.compile(
    r"(?i)\b(ssn|social security(?: number| no\.?)?|ss#)\W{0,5}(\d{9})\b"
)
CARD = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
NPI = re.compile(r"(?i)\bnpi\W{0,5}(\d{10})\b")
MBI = re.compile(
    r"\b[1-9][AC-HJKMNP-RT-Y][AC-HJKMNP-RT-Y0-9]\d-?[AC-HJKMNP-RT-Y][AC-HJKMNP-RT-Y0-9]\d-?[AC-HJKMNP-RT-Y]{2}\d{2}\b"
)
DEA = re.compile(r"(?i)\bdea\W{0,8}([A-Z][A-Z9]\d{7})\b")
MRN = re.compile(
    r"(?i)\b(mrn|medical record(?: number| no\.?)?|patient[ _-]?id|member[ _-]?id|subscriber[ _-]?id|policy[ _-]?(?:number|no)|chart[ _-]?(?:number|no))\W{0,5}([A-Z0-9][A-Z0-9-]{4,19})\b"
)

DATE = r"(?:\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2}-\d{1,2}-\d{4}|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.? \d{1,2},? \d{4})"
DOB = re.compile(rf"(?i)\b(dob|date of birth|birth ?date|born)\W{{0,5}}({DATE})")
NAMEISH = re.compile(
    r"(?i)\b(name|patient|first[_ ]?name|last[_ ]?name|full[_ ]?name|member|beneficiary|insured)\b"
)
ICD10 = re.compile(r"\b[A-TV-Z]\d{2}(?:\.[0-9A-TV-Z]{1,4})?\b")
DXWORD = re.compile(
    r"(?i)\b(diagnos[ie]s|dx|icd[- ]?10|condition|problem list|assessment)\b"
)
PHONE = re.compile(
    r"(?<!\d)(?:\+?1[ .-]?)?\(?[2-9]\d{2}\)?[ .-]?[2-9]\d{2}[ .-]?\d{4}(?!\d)"
)
EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

# Known test / documentation values — never personal.
TEST_VALUES = {
    "123456789",
    "078051120",
    "219099999",  # famous dummy SSNs
    "4111111111111111",
    "4242424242424242",
    "5555555555554444",
    "5105105105105100",
    "378282246310005",
    "371449635398431",
    "6011111111111117",
    "4012888888881881",
    "1234567890",
    "1234567893",  # dummy NPI
}
PLACEHOLDER = re.compile(
    r"(?i)(x{3,}|#{3,}|\*{3,}|•{2,}|<[^>]*>|\{\{[^}]*\}\}|example|redacted|placeholder|dummy|fake|sample)"
)


def _near(text: str, start: int, end: int, rx: re.Pattern, window: int = 80) -> bool:
    lo, hi = max(0, start - window), min(len(text), end + window)
    return bool(rx.search(text[lo:hi]))


def _placeholderish(text: str, start: int, end: int) -> bool:
    lo, hi = max(0, start - 12), min(len(text), end + 12)
    return bool(PLACEHOLDER.search(text[lo:hi]))


# ---------------------------------------------------------------- scan


def scan(text: str, cfg: dict | None = None, limit: int = 50) -> list[Hit]:
    """Find PII/PHI in `text`. Returns hits sorted by position, high severity first on ties."""
    if not text:
        return []
    cfg = cfg or {}
    disabled = set(cfg.get("disable", []))
    allow = {re.sub(r"\W", "", v) for v in cfg.get("allow_values", [])} | TEST_VALUES
    hits: list[Hit] = []
    seen: set[tuple[int, int]] = set()

    def add(kind, sev, s, e, v):
        if kind in disabled or (s, e) in seen:
            return
        if re.sub(r"\W", "", v) in allow or _placeholderish(text, s, e):
            return
        seen.add((s, e))
        hits.append(Hit(kind, sev, s, e, v))

    for m in SSN.finditer(text):
        if ssn_valid(m.group(1), m.group(2), m.group(3)):
            add("ssn", "high", m.start(), m.end(), m.group(0))
    for m in SSN_LABELED.finditer(text):
        d = m.group(2)
        if ssn_valid(d[:3], d[3:5], d[5:]):
            add("ssn", "high", m.start(2), m.end(2), d)
    for m in CARD.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        if card_valid(digits):
            add("card", "high", m.start(), m.end(), m.group(0))
    for m in NPI.finditer(text):
        if npi_valid(m.group(1)):
            add("npi", "high", m.start(1), m.end(1), m.group(1))
    for m in MBI.finditer(text):
        add("mbi", "high", m.start(), m.end(), m.group(0))
    for m in DEA.finditer(text):
        if dea_valid(m.group(1)):
            add("dea", "high", m.start(1), m.end(1), m.group(1))
    for m in MRN.finditer(text):
        v = m.group(2)
        if re.search(r"\d", v):  # an ID, not a word
            add("mrn", "high", m.start(2), m.end(2), v)
    for p in cfg.get("extra_id_patterns", []):
        try:
            rx = re.compile(p["regex"])
        except (re.error, KeyError):
            continue
        for m in rx.finditer(text):
            add(
                p.get("name", "custom_id"),
                p.get("severity", "high"),
                m.start(),
                m.end(),
                m.group(0),
            )

    for m in DOB.finditer(text):
        if _near(text, m.start(), m.end(), NAMEISH, 120):
            add("dob_name", "medium", m.start(2), m.end(2), m.group(2))
    for m in ICD10.finditer(text):
        if _near(text, m.start(), m.end(), DXWORD, 60):
            add("icd10", "medium", m.start(), m.end(), m.group(0))
    for m in PHONE.finditer(text):
        if _near(text, m.start(), m.end(), NAMEISH, 60):
            add("phone_name", "medium", m.start(), m.end(), m.group(0))
    emails = list(EMAIL.finditer(text))
    if len(emails) >= 5 and "email_bulk" not in disabled:
        for m in emails:
            add("email_bulk", "medium", m.start(), m.end(), m.group(0))

    hits.sort(key=lambda h: (h.start, h.severity != "high"))
    return hits[:limit]


LABEL = {
    "ssn": "SSN",
    "card": "card number",
    "npi": "NPI",
    "mbi": "Medicare ID",
    "dea": "DEA number",
    "mrn": "record/member ID",
    "dob_name": "DOB",
    "icd10": "diagnosis code",
    "phone_name": "phone",
    "email_bulk": "email",
}


def redact(text: str, cfg: dict | None = None) -> tuple[str, list[Hit]]:
    """Replace every hit with [<LABEL> redacted]. Returns (new_text, hits)."""
    hits = scan(text, cfg, limit=10_000)
    if not hits:
        return text, []
    out, pos = [], 0
    for h in sorted(hits, key=lambda h: h.start):
        if h.start < pos:
            continue
        out.append(text[pos : h.start])
        out.append(f"[{LABEL.get(h.kind, h.kind)} redacted]")
        pos = h.end
    out.append(text[pos:])
    return "".join(out), hits


def summarize(hits: list[Hit], text: str = "", n: int = 5) -> str:
    lines = []
    for h in hits[:n]:
        where = f" line {h.line(text)}" if text else ""
        lines.append(
            f"  - {LABEL.get(h.kind, h.kind)} ({h.severity}){where}: {h.masked()}"
        )
    if len(hits) > n:
        lines.append(f"  - … and {len(hits) - n} more")
    return "\n".join(lines)
