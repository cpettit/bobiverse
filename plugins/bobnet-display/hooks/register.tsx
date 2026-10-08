/**
 * BOBNET — Moot Hall
 *
 * A live relay display for the Bobiverse crew. When two or more Bobs are
 * running at once (a /moot, /replicate, /suddar fan-out), the pane opens on its
 * own; when the last one reports back it holds for a moment, shows the tally,
 * and folds away. `/bobnet` opens it by hand any time.
 *
 * STUB STATUS — what works vs. what's sketched:
 *   [x] roster: every subagent from spawn → report, with tool count and last tool
 *   [x] SCUT traffic log: spawns, tool calls, reports
 *   [x] auto-open at MOOT_THRESHOLD concurrent Bobs; /bobnet command
 *   [x] Thoth gets his own sealed vault card
 *   [x] drift-check indicator (did the report carry a DRIFT CHECK section)
 *   [ ] TODO gate counters: attribute Busters/SUDDAR/Prime/Oracle asks/denies
 *   [ ] TODO auto-close after the hold timer (needs $.clock + a guard on re-open)
 *   [ ] TODO elapsed-time ticking while idle (currently redraws on events only)
 *   [ ] TODO starmap row: plot each Bob at his home system (see HOME below)
 *   [ ] TODO surface-specific polish: desktop gets color bars, mobile collapses to roster only
 */
import { atom, read, update } from "claude-code";
import type { EngineInterface, Register } from "claude-code";

import type { Bob, BobStatus, GateCounts, Traffic } from "../types";

const PANE = "bobnet";
const TITLE = "BOBNET · Moot Hall";
const MOOT_THRESHOLD = 2; // concurrent Bobs that count as "the crew is running"
const TRAFFIC_KEEP = 60;

const bobs = atom(
  { plugin: "bobnet-display", key: "bobs" } as const,
  [] as Bob[],
);
const traffic = atom(
  { plugin: "bobnet-display", key: "traffic" } as const,
  [] as Traffic[],
);
const zero: GateCounts = { asks: 0, denies: 0 };
const gates = atom({ plugin: "bobnet-display", key: "gates" } as const, {
  busters: zero,
  suddar: zero,
  prime: zero,
  oracle: zero,
});
const mootStartedAt = atom(
  { plugin: "bobnet-display", key: "mootStartedAt" } as const,
  null as number | null,
);

// ── flavor ────────────────────────────────────────────────────────────────
/** Each Bob's call sign glyph. Unknown agents get a generic probe. */
const GLYPH: Record<string, string> = {
  bob: "◆",
  bill: "⚗",
  riker: "✦",
  will: "⚓",
  mario: "◎",
  medeiros: "✠",
  garfield: "⚙",
  neil: "◐",
  herschel: "◑",
  "sandbox-bob": "▣",
  roamer: "·",
  homer: "☻",
  marvin: "☁",
  milo: "➶",
  bender: "⌁",
  hugh: "∑",
  howard: "✎",
  archimedes: "△",
  manny: "⊕",
  guppy: "▤",
  charles: "◍",
  thoth: "⚿",
};
/** TODO starmap: home systems for the starmap row. Tune to taste/lore. */
export const HOME: Record<string, string> = {
  bob: "Epsilon Eridani",
  bill: "Epsilon Eridani",
  riker: "Sol",
  will: "Sol",
  homer: "Sol",
  charles: "Sol",
  milo: "Omicron² Eridani",
  howard: "Omicron² Eridani",
  mario: "deep survey",
  bender: "unknown — last ping stale",
};

const STATUS_LABEL: Record<BobStatus, string> = {
  spooling: "spooling",
  running: "running",
  reporting: "reporting",
  done: "reported",
  aborted: "recalled",
  denied: "held at gate",
};

const short = (agentType: string) => agentType.split(":").pop() ?? agentType;

const clip = (s: string, n: number) =>
  s.length > n ? s.slice(0, n - 1) + "…" : s;

const mmss = (ms: number) => {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
};

/** A tiny activity bar from tool count — 5 cells. */
const bar = (n: number) => {
  const filled = Math.min(5, Math.ceil(n / 4));
  return "▰".repeat(filled) + "▱".repeat(5 - filled);
};

/** A one-line label for a tool call: "Edit src/api.py", "Bash pytest -q". */
function describeTool(e: { tool: string; input?: unknown }): string {
  const i = (e.input ?? {}) as Record<string, unknown>;
  const arg = (i.file_path ??
    i.path ??
    i.command ??
    i.pattern ??
    i.url ??
    i.query ??
    "") as string;
  return clip(`${e.tool} ${String(arg).split("\n")[0]}`.trim(), 48);
}

/** Whether this moot has already toasted. Module variable: resets on reload, which is harmless. */
let toasted = false;

/**
 * The always-visible fallback: a status line under the prompt while any Bob is
 * running, cleared when the relay goes quiet. Shows even when the pane can't be placed.
 */
async function relayStatus($: EngineInterface) {
  const live = (await read($, bobs)).filter(
    (b) => b.status === "running" || b.status === "spooling",
  );
  if (live.length === 0) {
    $.ui.status(undefined);
    return;
  }
  const names = live.map((b) => `${GLYPH[b.name] ?? "◇"} ${b.name}`).join("  ");
  $.ui.status(`⟡ BOBNET · ${live.length} on relay · ${names} · /bobnet`);
}

/** Append one line to the SCUT traffic log. */
async function log($: EngineInterface, t: Omit<Traffic, "at">) {
  const at = await $.clock.now();
  await update($, traffic, (list) =>
    [...list, { at, ...t }].slice(-TRAFFIC_KEEP),
  );
}

export const register: Register = (on) => {
  on("session.start", async ($, e, next) => {
    await $.command.register({
      name: "bobnet",
      description: "Open the Bobnet Moot Hall display",
    });
    return next(e);
  });

  on("command.run", { command: "bobnet" }, async ($) => {
    const opened = await $.ui.open({ id: PANE, title: TITLE });
    return {
      text: opened.isPlaced
        ? "Bobnet relay open."
        : `Bobnet relay is open but this surface isn't drawing it: ${opened.reason}`,
    };
  });

  // ── a Bob launches ──────────────────────────────────────────────────────
  on("agent.spawn", async ($, e, next) => {
    const name = short(e.subagentType);
    const now = await $.clock.now();
    const ran = await next(e);

    if (ran.deny !== undefined) {
      await log($, {
        from: name.toUpperCase(),
        text: `held: ${clip(ran.deny, 60)}`,
        tone: "warn",
      });
      return ran;
    }
    const agentId = ran.agentId ?? e.tool_use_id;
    await update($, bobs, (list) => [
      ...list,
      {
        agentId,
        name,
        task: clip(e.description, 40),
        status: "running" as const,
        startedAt: now,
        toolCount: 0,
      },
    ]);
    await log($, {
      from: "BOB",
      text: `replicated ${name} → ${clip(e.description, 40)}`,
      tone: "normal",
    });

    const active = (await read($, bobs)).filter(
      (b) => b.status === "running" || b.status === "spooling",
    );
    if (active.length >= MOOT_THRESHOLD) {
      if ((await read($, mootStartedAt)) === null) {
        await update($, mootStartedAt, () => now);
        await log($, {
          from: "BOBNET",
          text: `moot convened — ${active.length} Bobs on the relay`,
          tone: "normal",
        });
      }
      // An unasked open is only drawn on a wide terminal (≥144 cols, 110 once
      // the person has opened it) or a surface that places panes. Otherwise it
      // waits undrawn — so always keep a status line, and toast once per moot.
      const opened = await $.ui.open({ id: PANE, title: TITLE });
      if (!opened.isPlaced && !toasted) {
        toasted = true;
        $.ui.toast(
          `⟡ Moot convened — ${active.length} Bobs on the relay. /bobnet to watch.`,
        );
        await log($, {
          from: "BOBNET",
          text: `pane waiting: ${clip(opened.reason, 60)}`,
          tone: "dim",
        });
      }
    }
    await relayStatus($);
    return ran;
  }).catch(($, e, next) => next(e)); // observer: a display bug must never refuse a spawn

  // ── a Bob uses a tool ───────────────────────────────────────────────────
  on("tool.call", async ($, e, next) => {
    const agentId = (e as { agentId?: string }).agentId;
    const ran = await next(e);
    if (!agentId) return ran; // main loop; not on the roster

    const label = describeTool(e as { tool: string; input?: unknown });
    let who = "BOB";
    await update($, bobs, (list) =>
      list.map((b) => {
        if (b.agentId !== agentId) return b;
        who = b.name;
        return { ...b, toolCount: b.toolCount + 1, lastTool: label };
      }),
    );
    const denied = (ran as { deny?: string }).deny;
    if (denied) {
      // TODO gate counters: parse the hook name out of `denied` ("BUSTERS:", "SUDDAR:", "PRIME DIRECTIVE:",
      // "ORACLE GATE:") and bump `gates[...]`. Asks are harder: a prompt the human approved looks like a
      // normal success here — likely needs a classic.PreToolUse observer instead.
      await log($, {
        from: who,
        text: `blocked: ${clip(denied, 56)}`,
        tone: "alert",
      });
    } else {
      await log($, { from: who, text: label, tone: "dim" });
    }
    return ran;
  }).catch(($, e, next) => next(e)); // observer: never block or re-run a Bob's tool call

  // ── a Bob reports back ──────────────────────────────────────────────────
  on("turn.complete", async ($, e, next) => {
    const ran = await next(e);
    if (!e.agentId) return ran;
    const now = await $.clock.now();
    let who = "";
    await update($, bobs, (list) =>
      list.map((b) => {
        if (b.agentId !== e.agentId) return b;
        who = b.name;
        return {
          ...b,
          status: e.isAborted ? "aborted" : "done",
          endedAt: now,
          driftChecked: /DRIFT CHECK/i.test(e.answer ?? ""),
        };
      }),
    );
    if (who)
      await log($, {
        from: who,
        text: e.isAborted ? "recalled" : `reported (${mmss(e.durationMs)})`,
        tone: "normal",
      });

    await relayStatus($);
    const stillRunning = (await read($, bobs)).some(
      (b) => b.status === "running" || b.status === "spooling",
    );
    if (!stillRunning && (await read($, mootStartedAt)) !== null) {
      await log($, {
        from: "BOBNET",
        text: "moot adjourned — all Bobs reported",
        tone: "normal",
      });
      await update($, mootStartedAt, () => null);
      toasted = false;
      // TODO auto-close: hold ~8s so the tally is visible, then $.ui.close({ id: PANE }) — unless a new
      // moot has started in the meantime (check mootStartedAt again after the wait).
    }
    return ran;
  });

  // ── drawing ─────────────────────────────────────────────────────────────
  on("ui.render", { component: "Pane", requestId: PANE }, async ($, e) => {
    const { Box, Text } = $.ui.resolve(e);
    const now = await $.clock.now();
    const roster = await read($, bobs);
    const log = await read($, traffic);
    const g = await read($, gates);
    const since = await read($, mootStartedAt);
    const rows = e.viewport?.rows ?? 30;

    const active = roster.filter(
      (b) => b.status === "running" || b.status === "spooling",
    );
    const recent = roster
      .filter((b) => b.status !== "running" && b.status !== "spooling")
      .slice(-4);
    const thoth = roster.filter((b) => b.name === "thoth").slice(-1)[0];
    const crew = [...active, ...recent].filter((b) => b.name !== "thoth");
    const logRoom = Math.max(3, rows - crew.length - (thoth ? 10 : 6) - 8);

    const header =
      since !== null
        ? `MOOT IN SESSION · ${active.length} on relay · ${mmss(now - since)}`
        : active.length
          ? `${active.length} on relay`
          : "relay quiet";

    return (
      <Box flexDirection="column" gap={1}>
        {/* ── header ── */}
        <Box justifyContent="space-between">
          <Text bold color="cyan">
            BOBNET ⟡ SCUT relay
          </Text>
          <Text
            color={since !== null ? "green" : undefined}
            dimColor={since === null}
          >
            {header}
          </Text>
        </Box>

        {/* ── roster ── */}
        <Box
          flexDirection="column"
          borderStyle="round"
          borderDimColor
          paddingX={1}
        >
          {crew.length === 0 && (
            <Text dimColor>
              No Bobs replicated this session. /moot to convene one.
            </Text>
          )}
          {crew.map((b) => {
            const live = b.status === "running" || b.status === "spooling";
            const t = (b.endedAt ?? now) - b.startedAt;
            return (
              <Box key={b.agentId} justifyContent="space-between">
                <Text dimColor={!live}>
                  <Text color={live ? "green" : undefined}>
                    {live ? "◉" : "○"}
                  </Text>{" "}
                  {GLYPH[b.name] ?? "◇"}{" "}
                  <Text bold={live}>{b.name.padEnd(11)}</Text>{" "}
                  {live ? bar(b.toolCount) : STATUS_LABEL[b.status].padEnd(5)}{" "}
                  {String(b.toolCount).padStart(3)} ops{"  "}
                  {live ? clip(b.lastTool ?? b.task, 34) : clip(b.task, 34)}
                </Text>
                <Text dimColor>
                  {!live && b.driftChecked !== undefined
                    ? b.driftChecked
                      ? "drift✓ "
                      : "drift? "
                    : ""}
                  {mmss(t)}
                </Text>
              </Box>
            );
          })}
        </Box>

        {/* ── Thoth's vault: sealed / consulting / answered ── */}
        {thoth && (
          <Box
            flexDirection="column"
            borderStyle="double"
            borderColor="magenta"
            paddingX={1}
          >
            <Text color="magenta" bold>
              ⚿ THOTH —{" "}
              {thoth.status === "running"
                ? "consulting"
                : thoth.status === "done"
                  ? "answered"
                  : STATUS_LABEL[thoth.status]}
            </Text>
            <Text dimColor>{clip(thoth.task, 60)}</Text>
            <Text dimColor>
              read-only · no reach · {thoth.toolCount} lookups ·{" "}
              {mmss((thoth.endedAt ?? now) - thoth.startedAt)}
            </Text>
          </Box>
        )}

        {/* ── SCUT traffic ── */}
        <Box flexDirection="column">
          <Text dimColor>── SCUT traffic ─────────────────────────────</Text>
          {log.slice(-logRoom).map((t) => (
            <Text
              key={`${t.at}-${t.from}-${t.text}`}
              dimColor={t.tone === "dim"}
              color={
                t.tone === "alert"
                  ? "red"
                  : t.tone === "warn"
                    ? "yellow"
                    : undefined
              }
              wrap="truncate-end"
            >
              {new Date(t.at).toISOString().slice(11, 19)} {t.from.padEnd(10)}{" "}
              {t.text}
            </Text>
          ))}
        </Box>

        {/* ── gates ── */}
        <Box gap={2}>
          <Text dimColor>gates</Text>
          {(["busters", "suddar", "prime", "oracle"] as const).map((k) => (
            <Text
              key={k}
              color={g[k].denies ? "red" : g[k].asks ? "yellow" : "green"}
            >
              {k.toUpperCase()}{" "}
              {g[k].denies
                ? `✕${g[k].denies}`
                : g[k].asks
                  ? `?${g[k].asks}`
                  : "✓"}
            </Text>
          ))}
        </Box>
      </Box>
    );
  });
};
