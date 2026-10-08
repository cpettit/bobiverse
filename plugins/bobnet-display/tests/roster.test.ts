import { expect, mock, test } from "claude-code/testing";
import type { Engine } from "claude-code/testing";

/** Draw the pane on the terminal surface and flatten it to its shown text. */
async function paneText($: Engine) {
  const tree = await $.ui.render({
    component: "Pane",
    requestId: "bobnet",
    surface: "terminal",
  } as never);
  const out: string[] = [];
  const walk = (n: unknown): void => {
    if (typeof n === "string" || typeof n === "number") out.push(String(n));
    else if (Array.isArray(n)) n.forEach(walk);
    else if (n && typeof n === "object") {
      const o = n as { children?: unknown; props?: { children?: unknown } };
      walk(o.children ?? o.props?.children);
    }
  };
  walk(tree);
  return out.join("");
}

test("roster tracks two Bobs from spawn to report, and adjourns the moot", async ($, on) => {
  mock.clock(on);
  let n = 0;
  on("agent.spawn", () => ({ model: "inherit", agentId: `bob-${++n}` }));
  on(
    "turn.complete",
    (_$, e) => ({ text: (e as { text?: string }).text ?? "" }) as never,
  );
  on("ui.open", () => ({ value: { isPlaced: true } }) as never);

  await $.agent.spawn({
    prompt: "design it",
    description: "ADR for queue",
    subagentType: "bobiverse:bill",
  } as never);
  await $.agent.spawn({
    prompt: "break it",
    description: "fuzz the parser",
    subagentType: "bobiverse:homer",
  } as never);

  const during = await paneText($);
  expect(during).toContain("MOOT IN SESSION");
  expect(during).toContain("bill");
  expect(during).toContain("homer");
  expect(during).toContain("replicated homer");

  for (const agentId of ["bob-1", "bob-2"]) {
    await $.turn.complete({
      agentId,
      turnId: agentId,
      reason: "answer",
      text: "done",
      answer: "Report.\n\nDRIFT CHECK\n1. ...",
      durationMs: 1200,
      isAborted: false,
    } as never);
  }

  const after = await paneText($);
  expect(after).toContain("moot adjourned");
  expect(after).toContain("drift✓");
  expect(after).not.toContain("MOOT IN SESSION");
});
