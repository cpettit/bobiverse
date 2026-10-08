# BOBNET · Moot Hall

A live relay display for the Bobiverse crew. It stays out of the way until the
crew is actually working — two or more Bobs running at once — then opens
itself as a pane, tracks every Bob from replication to report, and records
what happens on the SCUT relay. When the last Bob reports, it shows the tally
and folds away.

## The concept

In the books the Bobs are scattered across dozens of star systems and keep in
touch over SCUT, a faster-than-light relay. A moot is when they all get on the
relay at once. The display is the view from the relay hub: who's on, what each
one is doing right now, the traffic going past, and whether any of the gates
held anything up.

Three ideas carry the design:

1. **It comes when it's needed.** No pane until there's a crew to watch. A
   single Bob doing a single task doesn't warrant a dashboard; three Bobs
   working a moot in parallel do. `/bobnet` opens it by hand.
2. **Every Bob is a row, and the row tells you if he's stuck.** Status, an
   activity bar, tool count, the last thing he touched, and elapsed time. A Bob
   with a full bar is working; a Bob whose last tool hasn't changed in three
   minutes is worth a look.
3. **Thoth is different, and looks it.** The oracle gets his own sealed vault
   card in a double magenta border — *sealed / consulting / answered* — so it is
   always obvious when the expensive one is running.

## Layout (terminal, ~70 cols)

```
BOBNET ⟡ SCUT relay                    MOOT IN SESSION · 3 on relay · 04:12
╭─────────────────────────────────────────────────────────────────────────╮
│ ◉ ⚗ bill        ▰▰▰▱▱  12 ops  WebFetch https://docs.example.com/…  03:58│
│ ◉ ⚙ garfield    ▰▰▰▰▱  17 ops  Edit src/queue/consumer.ts           03:40│
│ ◉ ☻ homer       ▰▱▱▱▱   3 ops  Bash pytest -q tests/test_queue.py   01:02│
│ ○ ➶ milo        reported  22 ops  map the queue module    drift✓    00:48│
╰─────────────────────────────────────────────────────────────────────────╯
╔═════════════════════════════════════════════════════════════════════════╗
║ ⚿ THOTH — consulting                                                    ║
║ at-least-once vs exactly-once for the billing consumer                  ║
║ read-only · no reach · 9 lookups · 02:31                                ║
╚═════════════════════════════════════════════════════════════════════════╝
── SCUT traffic ─────────────────────────────
15:04:11 garfield   Edit src/queue/consumer.ts
15:04:09 homer      blocked: BUSTERS armed: this command is destructive…
15:04:02 BOB        replicated homer → fuzz the consumer
15:03:51 BOBNET     moot convened — 3 Bobs on the relay
gates  BUSTERS ?1  SUDDAR ✓  PRIME ✓  ORACLE ?1
```

Glyphs are call signs, one per Bob (⚗ Bill's lab, ⚙ Garfield's builds, ☻
Homer, ➶ Milo the scout, ⚿ Thoth's lock, ◍ Charles's planet…). `◉` running,
`○` reported. `drift✓` means the subagent's report included the DRIFT CHECK
the drift hook asks for; `drift?` means it didn't, so the integrator should
read that report more carefully.

## Lifecycle

| Event | What the display does |
|---|---|
| `agent.spawn` | Adds a row. At ≥ 2 concurrent Bobs: marks the moot convened, logs it, opens the pane. A spawn the Oracle Gate or a human declined shows as *held at gate* in the traffic. |
| `tool.call` (subagent) | Bumps that Bob's op count, updates his last tool, logs the line. A denied call logs in red. |
| `turn.complete` (subagent) | Marks the Bob reported or recalled, stamps elapsed, checks for DRIFT CHECK. When nobody's left running, logs *moot adjourned*. |
| `/bobnet` | Opens the pane on demand, idle or not. |

Both gating hooks (`agent.spawn`, `tool.call`) carry a fail-open `.catch` that
replays the real result: a bug in the display can never block a Bob or run his
tool twice. The test suite exercised this path by accident before the clock was
mocked — the hook errored and the spawn went through untouched.

## What's stubbed vs. what's real

Real and tested:
- roster from spawn → report, op counts, last tool, elapsed
- SCUT traffic log (spawns, tool calls, denials, reports, convene/adjourn)
- auto-open at the moot threshold; `/bobnet` command
- Thoth's vault card
- drift-check indicator

Stubbed, with `TODO` markers in `hooks/register.tsx`:
- **Gate counters.** Denials are visible on `tool.call` results and can be
  attributed by the message prefix (`BUSTERS:`, `SUDDAR:`, `PRIME DIRECTIVE:`,
  `ORACLE GATE:`). *Asks* the human approved look like ordinary successes at
  that layer, so counting them will need an observer on `classic.PreToolUse`.
- **Auto-close.** After *moot adjourned*, wait ~8s on `$.clock`, re-check that
  no new moot has started, then `$.ui.close`.
- **Ticking clock.** Elapsed times redraw only on events today; a 1s
  `$.clock` timer that touches an atom while a moot is in session fixes that.
- **Starmap row.** `HOME` maps each Bob to a star system. Next step is a
  one-line strip — `Sol ●●  ε Eri ●  ο² Eri ○` — showing where the crew is.
- **Per-surface polish.** Desktop can draw colored progress bars; mobile should
  collapse to the roster alone.

## Files

```
bobnet-display/
  .claude-plugin/plugin.json
  hooks/hooks.json         { "modules": ["./register.tsx"] }
  hooks/register.tsx       the mod
  types/index.d.ts         state contract: bobs, traffic, gates, mootStartedAt
  tests/roster.test.ts     two Bobs spawn → moot convened → both report → adjourned
  DESIGN.md                this file
```

To ship it with the rest of the crew, copy the folder to
`plugins/bobnet-display/` in the marketplace repo and add an entry to
`.claude-plugin/marketplace.json`; it's independent of the main plugin and can
be installed on its own.
