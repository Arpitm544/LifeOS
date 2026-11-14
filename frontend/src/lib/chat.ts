import { parseWorkspace, validateTask } from "./task-utils.ts";
import { categories, type Preferences, type Task, type TaskInput } from "./types.ts";

export type ChatReply = { reply: string; spoken_reply: string; tasks: TaskInput[] };
export type ChatMessage = { id: string; text: string; response?: ChatReply; taskIds?: Record<number, string> };
type ChatRequest = { text: string; history: { role: "user" | "assistant"; content: string }[]; tasks: Task[]; preferences: Preferences };

export function parseChatRequest(value: unknown): ChatRequest {
  const data = value as ChatRequest;
  if (!data || typeof data.text !== "string" || !data.text.trim() || data.text.length > 1000) throw new Error("Invalid message.");
  if (!Array.isArray(data.history) || data.history.length > 12 || data.history.length % 2 || data.history.some((m, i) => !m || m.role !== (i % 2 ? "assistant" : "user") || typeof m.content !== "string" || !m.content.trim() || m.content.length > 6000)) throw new Error("Invalid history.");
  if (!Array.isArray(data.tasks) || data.tasks.length > 30) throw new Error("Invalid task context.");
  const workspace = parseWorkspace(JSON.stringify({ version: 1, tasks: data.tasks, preferences: data.preferences }));
  return { text: data.text.trim(), history: data.history, tasks: workspace.tasks, preferences: workspace.preferences };
}

export function parseChatReply(value: unknown): ChatReply {
  const data = value as ChatReply;
  if (!data || typeof data.reply !== "string" || !data.reply.trim() || data.reply.length > 6000 || typeof data.spoken_reply !== "string" || !data.spoken_reply.trim() || data.spoken_reply.length > 500 || !Array.isArray(data.tasks) || data.tasks.length > 5) throw new Error("Invalid AI reply. Please retry.");
  const tasks = data.tasks.map(task => {
    if (!task || typeof task.title !== "string" || validateTask(task)) throw new Error("Invalid task suggestion. Please retry.");
    if (task.deadline !== null && !/(Z|[+-]\d{2}:\d{2})$/.test(task.deadline)) throw new Error("The suggested deadline needs a timezone. Please retry.");
    return { title: task.title.trim(), deadline: task.deadline, effort: task.effort, importance: task.importance, category: task.category };
  });
  return { reply: data.reply.trim(), spoken_reply: data.spoken_reply.trim(), tasks };
}

export const chatReplySchema = {
  type: "object", properties: {
    reply: { type: "string", maxLength: 6000 }, spoken_reply: { type: "string", maxLength: 500 },
    tasks: { type: "array", maxItems: 5, items: { type: "object", properties: {
      title: { type: "string", minLength: 1, maxLength: 120 }, deadline: { type: ["string", "null"], description: "ISO 8601 datetime with timezone offset, or null" },
      effort: { type: "integer", minimum: 5, maximum: 600 }, importance: { type: "integer", minimum: 1, maximum: 5 }, category: { type: "string", enum: categories },
    }, required: ["title", "deadline", "effort", "importance", "category"], additionalProperties: false } },
  }, required: ["reply", "spoken_reply", "tasks"], additionalProperties: false,
};
