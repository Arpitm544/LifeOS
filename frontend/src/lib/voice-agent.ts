import type { ChatAction, ChatResponse } from "./types.ts";

type Phrase = (name: string) => string;
const named = (name: string, before: string) => (name ? `${before}${name}` : "");

// Greetings and farewells in English and Hindi. Any other code falls back to English.
const greetings: Record<string, Phrase> = {
  en: n => `Hi${named(n, " ")}! What can I do for you?`,
  hi: n => `नमस्ते${named(n, " ")}! बताइए, मैं क्या मदद करूँ?`,
};
const farewells: Record<string, string> = { en: "Okay, talk soon.", hi: "ठीक है, फिर मिलते हैं।" };
const base = (language?: string | null) => (language ?? "en").toLowerCase().split(/[-_]/)[0];

/** What the agent says when a conversation opens, in `language` (a code such as "hi" or "es-ES"). */
export function greeting(firstName: string, language?: string | null) {
  return (greetings[base(language)] ?? greetings.en)(firstName.trim());
}

/** What the agent says before closing, in the language of the conversation. */
export function farewell(language?: string | null) {
  return farewells[base(language)] ?? farewells.en;
}

// Whole-utterance phrases that end the conversation. "No" alone is only a goodbye when nothing is waiting for an answer.
const endings = /^(?:ok(?:ay)?[,\s]+)?(?:bye(?:[\s-]bye)?|goodbye|good night|see (?:you|ya)|stop|end(?: the)? (?:call|chat|conversation)|that'?s (?:all|it|everything)|i'?m (?:done|good|all set)|nothing(?: else)?|thanks?(?: you)?(?: so much)?(?:[,\s]+(?:that'?s (?:all|it)|bye))?)$/;
const declines = /^(?:no|nope|no thanks?|no thank you)$/;

// Hindi goodbyes, in Devanagari and romanised (people often speak Hindi that way).
const otherEndings = new Set([
  "अलविदा", "बाय", "बाय बाय", "बस", "बस इतना", "बस इतना ही", "धन्यवाद", "शुक्रिया", "ठीक है बाय", "फिर मिलते हैं",
  "alvida", "bas", "bas itna", "bas itna hi", "dhanyavaad", "dhanyawad", "shukriya", "theek hai bye", "phir milte hain",
]);
const otherDeclines = new Set(["नहीं", "नहीं धन्यवाद", "nahi", "nahin", "nahi shukriya"]);

/** True when the user is wrapping up. `awaitingAnswer` keeps "no" for answering the agent's question. */
export function isGoodbye(text: string, awaitingAnswer = false) {
  const clean = text.toLowerCase().replace(/[‘’]/g, "'").replace(/[.!?,।…\s]+$/g, "").replace(/\s+/g, " ").trim();
  if (!clean) return false;
  if (endings.test(clean) || otherEndings.has(clean)) return true;
  return !awaitingAnswer && (declines.test(clean) || otherDeclines.has(clean));
}

/** The words to read aloud: the backend's spoken version if it wrote one, else the reply (the speech API takes 500 characters). */
export function spokenText(response: Pick<ChatResponse, "reply" | "spoken_reply">) {
  const text = (response.spoken_reply || response.reply || "").trim();
  return text.length > 500 ? `${text.slice(0, 497).replace(/\s+\S*$/, "")}…` : text;
}

/** Whether the agent just asked something, so the next "no" is an answer rather than a goodbye. */
export function asksQuestion(response: Pick<ChatResponse, "clarification" | "confirmation">) {
  return !!(response.clarification || response.confirmation);
}

const labels: Partial<Record<ChatAction["type"], string>> = {
  task_created: "Task added", task_updated: "Task updated", task_completed: "Task completed", task_deleted: "Task removed",
  event_created: "Event added", preference_set: "Preference saved", plan_generated: "Plan updated",
};

/** Short labels for what changed, shown under the agent's reply. Read-only checks are left out. */
export function actionLabels(actions: ChatAction[]) {
  return actions.map(action => labels[action.type]).filter((label): label is string => !!label);
}
