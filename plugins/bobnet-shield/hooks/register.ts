/**
 * BOBNET SHIELD — redact PII/PHI from tool results before the model reads them.
 *
 * Hooks are good at refusing an action; they can't change what a tool returned.
 * A mod can. Every tool result passes through here on its way to the model:
 * string values are scanned with the same validated detector the Python hooks
 * use (pii.py), and hits are replaced with "[SSN redacted]" and the like. The
 * result keeps its exact shape, so core accepts it as the tool's own output.
 *
 * Fails closed: if redaction throws, the result is withheld rather than passed
 * through unscanned. (The opposite of the Moot Hall display, which fails open —
 * a display bug should never block work; a shield bug should never leak data.)
 *
 * Covers the main loop and every Bob's tool calls alike. Not covered: what a
 * subagent already read inside its own context before reporting (its *report*
 * passes through here as the Agent tool's result and is scanned).
 */
import type { Register } from "claude-code";

type Severity = "high" | "medium";
type Hit = { kind: string; severity: Severity; start: number; end: number };

// ── detector (TS port of hooks/scripts/pii.py — keep the two in step) ─────────

const LABEL: Record<string, string> = {
  ssn: "SSN",
  card: "card number",
  npi: "NPI",
  mbi: "Medicare ID",
  dea: "DEA number",
  mrn: "record/member ID",
  dob_name: "DOB",
  icd10: "diagnosis code",
  phone_name: "phone",
  email_bulk: "email",
};

const TEST_VALUES = new Set([
  "123456789",
  "078051120",
  "219099999",
  "4111111111111111",
  "4242424242424242",
  "5555555555554444",
  "5105105105105100",
  "378282246310005",
  "371449635398431",
  "6011111111111117",
  "4012888888881881",
  "1234567890",
  "1234567893",
]);

const PLACEHOLDER =
  /(x{3,}|#{3,}|\*{3,}|•{2,}|<[^>]*>|\{\{[^}]*\}\}|example|redacted|placeholder|dummy|fake|sample)/i;

const digitsOf = (s: string) => s.replace(/\D/g, "");

export function luhn(d: string): boolean {
  let sum = 0;
  let alt = false;
  for (let i = d.length - 1; i >= 0; i--) {
    let n = d.charCodeAt(i) - 48;
    if (alt) {
      n *= 2;
      if (n > 9) n -= 9;
    }
    sum += n;
    alt = !alt;
  }
  return sum % 10 === 0;
}

const ssnValid = (a: string, g: string, s: string) => {
  const area = Number(a);
  return !(
    area === 0 ||
    area === 666 ||
    area >= 900 ||
    g === "00" ||
    s === "0000"
  );
};
const CARD_PREFIX =
  /^(4|5[1-5]|2[2-7]|3[47]|6(011|5|4[4-9])|3(0[0-5]|[68])|35)/;
const cardValid = (d: string) =>
  d.length >= 13 &&
  d.length <= 19 &&
  CARD_PREFIX.test(d) &&
  luhn(d) &&
  new Set(d).size > 2;
const npiValid = (d: string) =>
  d.length === 10 && (d[0] === "1" || d[0] === "2") && luhn("80840" + d);
const deaValid = (s: string) => {
  const u = s.toUpperCase();
  if (!/^[ABCDEFGHJKLMPRSTUX][A-Z9]\d{7}$/.test(u)) return false;
  const d = [...u.slice(2)].map(Number);
  return (d[0]! + d[2]! + d[4]! + 2 * (d[1]! + d[3]! + d[5]!)) % 10 === d[6];
};

const DATE = String.raw`(?:\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2}-\d{1,2}-\d{4}|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.? \d{1,2},? \d{4})`;
const NAMEISH =
  /\b(name|patient|first[_ ]?name|last[_ ]?name|full[_ ]?name|member|beneficiary|insured)\b/i;
const DXWORD =
  /\b(diagnos[ie]s|dx|icd[- ]?10|condition|problem list|assessment)\b/i;

const near = (t: string, s: number, e: number, rx: RegExp, w: number) =>
  rx.test(t.slice(Math.max(0, s - w), Math.min(t.length, e + w)));
const isDigit = (c: string | undefined) =>
  c !== undefined && c >= "0" && c <= "9";

export function scan(text: string, medium = true): Hit[] {
  if (!text) return [];
  const hits: Hit[] = [];
  const seen = new Set<string>();
  const add = (kind: string, severity: Severity, s: number, e: number) => {
    if (severity === "medium" && !medium) return;
    const key = `${s}:${e}`;
    if (seen.has(key)) return;
    const v = text.slice(s, e);
    if (TEST_VALUES.has(v.replace(/\W/g, ""))) return;
    if (
      PLACEHOLDER.test(
        text.slice(Math.max(0, s - 12), Math.min(text.length, e + 12)),
      )
    )
      return;
    seen.add(key);
    hits.push({ kind, severity, start: s, end: e });
  };
  const each = (rx: RegExp, fn: (m: RegExpExecArray) => void) => {
    for (const m of text.matchAll(
      new RegExp(rx.source, rx.flags.includes("g") ? rx.flags : rx.flags + "g"),
    ))
      fn(m as RegExpExecArray);
  };
  /** emulate the Python lookbehinds: the char before/after must not be a digit (or dash, for SSNs) */
  const bounded = (s: number, e: number, dash = false) => {
    const b = text[s - 1],
      a = text[e];
    return !isDigit(b) && !isDigit(a) && !(dash && (b === "-" || a === "-"));
  };

  each(/(\d{3})[- ](\d{2})[- ](\d{4})/, (m) => {
    const s = m.index!,
      e = s + m[0].length;
    if (bounded(s, e, true) && ssnValid(m[1]!, m[2]!, m[3]!))
      add("ssn", "high", s, e);
  });
  each(
    /\b(ssn|social security(?: number| no\.?)?|ss#)\W{0,5}(\d{9})\b/i,
    (m) => {
      const d = m[2]!,
        s = m.index! + m[0].length - d.length;
      if (ssnValid(d.slice(0, 3), d.slice(3, 5), d.slice(5)))
        add("ssn", "high", s, s + 9);
    },
  );
  each(/(?:\d[ -]?){12,18}\d/, (m) => {
    const s = m.index!,
      e = s + m[0].length;
    if (bounded(s, e) && cardValid(digitsOf(m[0]))) add("card", "high", s, e);
  });
  each(/\bnpi\W{0,5}(\d{10})\b/i, (m) => {
    const s = m.index! + m[0].length - 10;
    if (npiValid(m[1]!)) add("npi", "high", s, s + 10);
  });
  each(
    /\b[1-9][AC-HJKMNP-RT-Y][AC-HJKMNP-RT-Y0-9]\d-?[AC-HJKMNP-RT-Y][AC-HJKMNP-RT-Y0-9]\d-?[AC-HJKMNP-RT-Y]{2}\d{2}\b/,
    (m) => add("mbi", "high", m.index!, m.index! + m[0].length),
  );
  each(/\bdea\W{0,8}([A-Z][A-Z9]\d{7})\b/i, (m) => {
    const s = m.index! + m[0].length - 9;
    if (deaValid(m[1]!)) add("dea", "high", s, s + 9);
  });
  each(
    /\b(mrn|medical record(?: number| no\.?)?|patient[ _-]?id|member[ _-]?id|subscriber[ _-]?id|policy[ _-]?(?:number|no)|chart[ _-]?(?:number|no))\W{0,5}([A-Z0-9][A-Z0-9-]{4,19})\b/i,
    (m) => {
      const v = m[2]!,
        s = m.index! + m[0].length - v.length;
      if (/\d/.test(v)) add("mrn", "high", s, s + v.length);
    },
  );
  each(
    new RegExp(
      String.raw`\b(dob|date of birth|birth ?date|born)\W{0,5}(${DATE})`,
      "i",
    ),
    (m) => {
      const v = m[2]!,
        s = m.index! + m[0].length - v.length;
      if (near(text, s, s + v.length, NAMEISH, 120))
        add("dob_name", "medium", s, s + v.length);
    },
  );
  each(/\b[A-TV-Z]\d{2}(?:\.[0-9A-TV-Z]{1,4})?\b/, (m) => {
    const s = m.index!,
      e = s + m[0].length;
    if (near(text, s, e, DXWORD, 60)) add("icd10", "medium", s, e);
  });
  each(/(?:\+?1[ .-]?)?\(?[2-9]\d{2}\)?[ .-]?[2-9]\d{2}[ .-]?\d{4}/, (m) => {
    const s = m.index!,
      e = s + m[0].length;
    if (bounded(s, e) && near(text, s, e, NAMEISH, 60))
      add("phone_name", "medium", s, e);
  });
  const emails = [
    ...text.matchAll(/\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b/g),
  ];
  if (emails.length >= 5)
    for (const m of emails)
      add("email_bulk", "medium", m.index!, m.index! + m[0].length);

  return hits.sort((a, b) => a.start - b.start);
}

export function redact(
  text: string,
  medium = true,
): { text: string; hits: Hit[] } {
  const hits = scan(text, medium);
  if (!hits.length) return { text, hits };
  let out = "";
  let pos = 0;
  for (const h of hits) {
    if (h.start < pos) continue;
    out += text.slice(pos, h.start) + `[${LABEL[h.kind] ?? h.kind} redacted]`;
    pos = h.end;
  }
  return { text: out + text.slice(pos), hits };
}

/** Redact every string inside a value, keeping its shape. Returns the new value and all hits. */
export function redactDeep(
  v: unknown,
  medium = true,
): { value: unknown; hits: Hit[] } {
  const all: Hit[] = [];
  const walk = (x: unknown): unknown => {
    if (typeof x === "string") {
      const r = redact(x, medium);
      all.push(...r.hits);
      return r.text;
    }
    if (Array.isArray(x)) return x.map(walk);
    if (x && typeof x === "object") {
      const o: Record<string, unknown> = {};
      for (const [k, val] of Object.entries(x)) o[k] = walk(val);
      return o;
    }
    return x;
  };
  return { value: walk(v), hits: all };
}

// ── the hook ──────────────────────────────────────────────────────────────────

/** Tools whose results are just a confirmation of what Claude itself sent; nothing new to scan. */
const SKIP = new Set([
  "Write",
  "Edit",
  "MultiEdit",
  "NotebookEdit",
  "TodoWrite",
  "TaskCreate",
  "TaskUpdate",
]);

function tally(hits: Hit[]): string {
  const n: Record<string, number> = {};
  for (const h of hits)
    n[LABEL[h.kind] ?? h.kind] = (n[LABEL[h.kind] ?? h.kind] ?? 0) + 1;
  return Object.entries(n)
    .map(([k, c]) => `${c} ${k}${c > 1 ? "s" : ""}`)
    .join(", ");
}

export const register: Register = (on, options) => {
  const mode = String(options?.mode ?? "redact").trim().toLowerCase(); // unknown values → redact (fail safe)
  const medium = options?.medium !== false;
  if (mode === "off") return;

  on("tool.call", async ($, e, next) => {
    const ran = await next(e);
    if (SKIP.has(e.tool) || ran.deny !== undefined || ran.isError) return ran;

    const scanned = redactDeep(ran.result, medium);
    const textHits = scan(ran.text ?? "", medium); // what the model would actually read
    const hits = scanned.hits.length ? scanned.hits : textHits;
    if (!hits.length) return ran;

    const what = tally(hits);
    if (mode === "withhold" || (!scanned.hits.length && textHits.length)) {
      // withhold mode, or the personal data is only in core's rendered text, not a string we can rewrite
      $.ui.status(`🛡 shield withheld a ${e.tool} result (${what})`);
      return {
        deny: `result withheld by bobnet-shield: it contained ${what}. Work from a de-identified source.`,
      };
    }
    $.ui.status(`🛡 shield redacted ${what} from ${e.tool}`);
    return {
      result: scanned.value as typeof ran.result,
      context: [
        `bobnet-shield redacted ${what} from this ${e.tool} result before you saw it. ` +
          "Placeholders like [SSN redacted] stand in for real values; do not try to recover or guess them.",
      ],
    };
  }).catch(($, e, next) =>
    // Fail CLOSED. If the hook threw after the tool ran, next(e) replays that result — which is
    // exactly the unscanned data we must not pass through. Withhold it instead.
    next.called
      ? {
          deny: "result withheld: bobnet-shield could not scan it, and does not pass unscanned output through.",
        }
      : next(e),
  );
};
