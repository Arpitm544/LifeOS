"use client";

import { AlertTriangle, Check, Clock, HelpCircle, Minus, X } from "lucide-react";
import { formatMs, statusLabel, stepsSummary } from "@/lib/agent-steps";
import type { AgentStep } from "@/lib/types";

const icons = { done: Check, asked: HelpCircle, waiting: Clock, warning: AlertTriangle, failed: X, skipped: Minus } as const;

/** "How LifeOS handled this": what the agent read, decided and did for one message. */
export function AgentSteps({ steps, open }: { steps: AgentStep[]; open?: boolean }) {
  if (!steps.length) return null;
  return <details className="agent-steps" open={open}>
    <summary><span className="eyebrow muted">How LifeOS handled this</span><span className="agent-steps-summary">{stepsSummary(steps)}</span></summary>
    <ol>{steps.map((step, index) => {
      const Icon = icons[step.status] ?? Check;
      return <li key={index} className={`agent-step ${step.status}`}>
        <span className="agent-step-icon" aria-hidden="true"><Icon size={14} /></span>
        <div><p className="agent-step-label">{step.label}<span className="sr-only"> — {statusLabel(step.status)}</span></p>{step.detail ? <p className="agent-step-detail">{step.detail}</p> : null}</div>
        {step.ms ? <span className="agent-step-time">{formatMs(step.ms)}</span> : null}
      </li>;
    })}</ol>
  </details>;
}
