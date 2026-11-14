import type { AgentStep } from "./types.ts";

const order: AgentStep["status"][] = ["done", "asked", "waiting", "warning", "failed", "skipped"];
const words: Record<AgentStep["status"], string> = { done: "done", asked: "asked you", waiting: "waiting for you", warning: "heads-up", failed: "failed", skipped: "skipped" };

/** "4 steps · 3 done, 1 asked you · 1.2 s" */
export function stepsSummary(steps: AgentStep[]): string {
  const counts = new Map<AgentStep["status"], number>();
  for (const step of steps) counts.set(step.status, (counts.get(step.status) ?? 0) + 1);
  const parts = order.filter(status => counts.get(status)).map(status => `${counts.get(status)} ${words[status]}`);
  const ms = steps.reduce((total, step) => total + (step.ms ?? 0), 0);
  return [`${steps.length} step${steps.length === 1 ? "" : "s"}`, parts.join(", "), ms ? formatMs(ms) : ""].filter(Boolean).join(" · ");
}

export function formatMs(ms: number): string {
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1)} s`;
}

export function statusLabel(status: AgentStep["status"]): string {
  return words[status];
}
