import assert from "node:assert/strict";
import test from "node:test";
import { formatMs, stepsSummary } from "../src/lib/agent-steps.ts";
import type { AgentStep } from "../src/lib/types.ts";

const step = (status: AgentStep["status"], ms?: number): AgentStep => ({ kind: "tool", label: "Create task", status, detail: "", ms });

test("summary counts steps by status in a fixed order and adds time", () => {
  assert.equal(stepsSummary([step("asked"), step("done", 420), step("done", 900), step("warning")]), "4 steps · 2 done, 1 asked you, 1 heads-up · 1.3 s");
  assert.equal(stepsSummary([step("waiting")]), "1 step · 1 waiting for you");
});

test("times read naturally", () => {
  assert.equal(formatMs(42.4), "42 ms");
  assert.equal(formatMs(1250), "1.3 s");
});
