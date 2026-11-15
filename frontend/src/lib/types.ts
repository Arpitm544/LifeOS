// Shapes returned by the LifeOS FastAPI backend (backend/app/schemas*.py and api/*.py).
export const categories = ["study", "work", "errand", "health", "social", "finance", "home", "other"] as const;
export type Category = (typeof categories)[number];
export type TaskStatus = "open" | "blocked" | "done" | "dropped";
export type PriorityBand = "P1" | "P2" | "P3";

export type PriorityBreakdown = {
  urgency: number; importance: number; blocking: number; staleness: number;
  weights?: Record<string, number>;
  free_hours_before_deadline?: number; effort_min?: number; estimate_min?: number;
  calibration_factor?: number; blocks_count?: number;
};

export type Task = {
  id: string;
  title: string;
  deadline_at: string | null;
  effort_est_min: number;
  importance: number;
  category: Category;
  status: TaskStatus;
  priority_score: number;
  priority_band: PriorityBand;
  pinned: boolean;
  notes?: string | null;
  effort_actual_min?: number | null;
  recurrence_rrule?: string | null;
  created_at?: string | null;
  completed_at?: string | null;
  why?: string | null;
  priority_breakdown?: PriorityBreakdown | null;
};
export type TaskInput = { title: string; deadline_at: string | null; effort_est_min: number; importance: number; category: Category; notes?: string | null };
export type EffortAnswer = "less" | "about_right" | "more" | "custom";

export type PreferenceKey = "work_hours" | "quiet_hours" | "focus_windows" | "timezone" | "reminder_lead" | "estimate_padding" | "work_hours_overrides";
export type PreferenceRow = { id: string; key: string; value: Record<string, unknown>; source: "stated" | "inferred" | "default"; confidence: number; status: "active" | "suggested" };
export type Routine = { id: string; title: string; rrule: string; start_time: string; duration_min: number; movable: boolean; anchor_date: string | null };

/** The planning settings the Profile form edits, flattened from preference rows. */
export type Preferences = {
  timezone: string;
  workStart: string; workEnd: string;
  quietStart: string; quietEnd: string;
  focusStart: string; focusEnd: string;
  reminderLead: number;
  estimatePadding: boolean;
};

export type TodayEvent = { id: string; title: string; start_at: string; end_at: string; location: string | null };
export type PlanBlock = { id: string; task_id: string; title: string | null; start_at: string; end_at: string; status: "planned" | "done" | "missed" | "moved" };
export type DueTask = { id: string; title: string; deadline_at: string | null; priority_score: number; priority_band: PriorityBand; status: TaskStatus; why: string | null; overdue: boolean };
export type Conflict = { id: string; deadline_at: string; needed_min: number; free_min: number; shortfall_min: number; task_ids: string[]; options: unknown[]; status?: string; tasks?: { id: string; title: string | null }[] };
export type Today = {
  date: string; timezone: string;
  events: TodayEvent[]; plan_blocks: PlanBlock[]; due_tasks: DueTask[]; conflicts: Conflict[];
  free_min_left: number;
  next: { type: "plan_block"; id: string; start_at: string; end_at: string; task_id: string; title: string | null } | null;
};

export type ConflictOptionType = "extend_hours" | "move_flexible" | "renegotiate";
export type ConflictOption = {
  type: ConflictOptionType; description: string; resolves: boolean; remaining_shortfall_min: number;
  change: Record<string, unknown>; draft_message?: string;
  preview: { task_id: string; title: string; start_at: string; end_at: string }[];
};
export type ConflictOptions = { conflict: Conflict; options: ConflictOption[] };
export type ConflictResolution = { conflict_id: string; status: string; applied: string; batch_id: string; draft_message: string | null; remaining_conflicts: number };

export type ChatTaskCard = Task & { deadline_label?: string | null };
export type ChatAction = {
  action_id: string | null;
  type: "task_created" | "task_updated" | "task_completed" | "task_deleted" | "event_created" | "preference_set" | "schedule" | "plan_generated" | "capacity_check";
  undo_until?: string;
  batch_id?: string;
  task_id?: string; title?: string; task?: ChatTaskCard;
  ask_actual_effort?: boolean;
  event?: { id: string; title: string; start_at: string; end_at: string; location: string | null; label: string };
  preference?: { key: string; value: Record<string, unknown>; source: string };
  filter?: string;
  result?: Record<string, unknown>;
  date?: string;
  plan_blocks?: { id?: string; task_id: string; title: string; start_at: string; end_at: string }[];
  unplaced_task_ids?: string[];
};
export type ChatConflict = { id: string; deadline_at: string; needed_min: number; free_min: number; shortfall_min: number; task_ids: string[]; options: string[] };
export type ChatResponse = {
  message_id: string | null; reply: string; spoken_reply?: string; actions: ChatAction[]; conflicts: ChatConflict[];
  clarification: { question: string; options: string[] } | null;
  confirmation: { prompt: string; options: string[] } | null;
  fallback: boolean;
  steps?: AgentStep[];
};

export type AgentStep = { kind: "context" | "understand" | "tool" | "check" | "fallback" | "confirm"; label: string; status: "done" | "asked" | "waiting" | "skipped" | "failed" | "warning"; detail: string; tool?: string; ms?: number };

export type Suggestion = { id: string; type: string; text: string; payload?: Record<string, unknown>; status: string };
export type Insights = {
  calibration_factors: Record<string, number>;
  focus_windows: [number, number][];
  plan_adherence: number;
  overdue_rates: Record<string, number>;
  snooze_rates: Record<string, number>;
  cold_start: boolean;
  completed_14d: number;
  completion_rate: number | null;
  planned_blocks_14d: number;
  completion_chart: { date: string; completed: number }[];
  samples: number;
  suggestions: Suggestion[];
};

export type Reminder = { id: string; item_type: string; item_id: string; kind: string; fire_at: string; status: string; action_taken: string | null; message: string | null; sent_at: string | null };
