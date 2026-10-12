import { expect, test } from "claude-code/testing";

import { luhn, redact, scan } from "../hooks/register";

const card = (() => {
  for (let c = 0; c < 10; c++) {
    const s = "4532" + "0".repeat(11) + c;
    if (luhn(s)) return s;
  }
  return "";
})();
const SSN = "512-44-" + "7832";

test("detector parity with pii.py: positives and near-misses", () => {
  const kinds = (t: string) => scan(t).map((h) => h.kind);
  expect(kinds(`patient ssn ${SSN}`)).toEqual(["ssn"]);
  expect(kinds("id 666-12-3456 and 901-23-4567")).toEqual([]);
  expect(kinds("use 123-45-6789 in docs")).toEqual([]);
  expect(kinds(`card ${card}`)).toEqual(["card"]);
  expect(kinds("4111 1111 1111 1111")).toEqual([]);
  expect(kinds("MBI 1EG4-TE5-MK73")).toEqual(["mbi"]);
  expect(kinds("MRN: A1234567")).toEqual(["mrn"]);
  expect(kinds("member id: pending")).toEqual([]);
  expect(kinds("patient name: J. Doe, DOB 03/14/1961")).toEqual(["dob_name"]);
  expect(kinds("build date 03/14/2024")).toEqual([]);
  expect(kinds("diagnosis: E11.9 type 2")).toEqual(["icd10"]);
  expect(kinds("2026-10-12 09:13:44 job 4532118 took 1234567 ms")).toEqual([]);
  expect(kinds(`ssn <${SSN}>`)).toEqual([]);
});

test("redact replaces values with labels", () => {
  expect(redact(`ssn ${SSN}, card ${card}`).text).toBe(
    "ssn [SSN redacted], card [card number redacted]",
  );
});

test("a Read result with an SSN reaches the model redacted, shape intact", async ($, on) => {
  on(
    "tool.call",
    () =>
      ({
        result: {
          type: "text",
          file: {
            filePath: "/x/p.csv",
            content: `name,ssn\nAnn,${SSN}\n`,
            numLines: 2,
          },
        },
        text: `name,ssn\nAnn,${SSN}\n`,
      }) as never,
  );
  const r = (await $.tool.call({
    tool: "Read",
    file_path: "/x/p.csv",
  } as never)) as {
    result?: { file: { content: string; numLines: number } };
    context?: string[];
  };
  expect(r.result?.file.content).toBe("name,ssn\nAnn,[SSN redacted]\n");
  expect(r.result?.file.numLines).toBe(2);
  expect(r.context?.[0]).toContain("redacted 1 SSN");
});

test("a clean result passes through untouched", async ($, on) => {
  const original = {
    result: { stdout: "build ok in 1234567 ms", stderr: "" },
    text: "build ok in 1234567 ms",
  };
  on("tool.call", () => original as never);
  const r = (await $.tool.call({
    tool: "Bash",
    command: "make",
  } as never)) as typeof original;
  expect(r.result.stdout).toBe("build ok in 1234567 ms");
});

test(
  "withhold mode drops a result that contains personal data",
  { options: { mode: "withhold" } },
  async ($, on) => {
    on(
      "tool.call",
      () =>
        ({
          result: { stdout: `card ${card}`, stderr: "" },
          text: `card ${card}`,
        }) as never,
    );
    const r = (await $.tool.call({
      tool: "Bash",
      command: "cat billing.log",
    } as never)) as { deny?: string; isError?: boolean; text?: string };
    const said = r.deny ?? r.text ?? "";
    expect(said).toContain("withheld");
    expect(said).not.toContain(card);
  },
);

test("writes and edits are not scanned (nothing new comes back)", async ($, on) => {
  on(
    "tool.call",
    () =>
      ({ result: { filePath: "/x/a.txt", content: SSN }, text: "ok" }) as never,
  );
  const r = (await $.tool.call({
    tool: "Write",
    file_path: "/x/a.txt",
    content: SSN,
  } as never)) as { result?: { content: string } };
  expect(r.result?.content).toBe(SSN);
});
