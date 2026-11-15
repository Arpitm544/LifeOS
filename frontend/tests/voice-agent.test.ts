import test from "node:test";
import assert from "node:assert/strict";
import { actionLabels, asksQuestion, farewell, greeting, isGoodbye, spokenText } from "../src/lib/voice-agent.ts";
import type { ChatAction } from "../src/lib/types.ts";

test("the agent greets by first name", () => {
  assert.equal(greeting("Arpit"), "Hi Arpit! What can I do for you?");
  assert.equal(greeting("  "), "Hi! What can I do for you?");
});

test("goodbyes end the conversation, but requests that mention them do not", () => {
  for (const phrase of ["Bye.", "bye bye", "Goodbye!", "That's all", "That’s it.", "Thanks", "thank you, that's all", "I'm done", "Okay, bye", "nothing else", "stop", "end the call"]) assert.equal(isGoodbye(phrase), true, phrase);
  for (const phrase of ["Stop my gym routine on Friday", "Add a meeting to say goodbye to Sam", "Thanks, now add a call at 3", "Thanks for adding that, also remind me tomorrow", "", "   "]) assert.equal(isGoodbye(phrase), false, phrase);
});

test("'no' answers the agent's question instead of ending the conversation", () => {
  assert.equal(isGoodbye("No.", true), false);
  assert.equal(isGoodbye("no thanks", true), false);
  assert.equal(isGoodbye("No thanks"), true);
  assert.equal(isGoodbye("bye", true), true);
});

test("the spoken reply prefers the backend's voice version and stays under the speech limit", () => {
  assert.equal(spokenText({ reply: "Added **Essay**.", spoken_reply: "Added Essay." }), "Added Essay.");
  assert.equal(spokenText({ reply: "Added Essay." }), "Added Essay.");
  const long = spokenText({ reply: "word ".repeat(200) });
  assert.ok(long.length <= 500);
  assert.ok(long.endsWith("…"));
});

test("questions and actions are recognised from the chat response", () => {
  assert.equal(asksQuestion({ clarification: null, confirmation: { prompt: "Add it?", options: ["Yes", "No"] } }), true);
  assert.equal(asksQuestion({ clarification: null, confirmation: null }), false);
  const actions = [{ type: "event_created" }, { type: "schedule" }, { type: "task_created" }] as ChatAction[];
  assert.deepEqual(actionLabels(actions), ["Event added", "Task added"]);
});

test("the agent greets and says goodbye in the conversation's language", () => {
  assert.equal(greeting("Arpit", "hi"), "नमस्ते Arpit! बताइए, मैं क्या मदद करूँ?");
  assert.equal(greeting("", "hi-IN"), "नमस्ते! बताइए, मैं क्या मदद करूँ?");
  assert.equal(greeting("Ana", "es"), "Hi Ana! What can I do for you?"); // only English and Hindi
  assert.equal(farewell("hi"), "ठीक है, फिर मिलते हैं।");
  assert.equal(farewell(null), "Okay, talk soon.");
});

test("Hindi goodbyes are understood, in Devanagari or romanised, punctuation and all", () => {
  for (const phrase of ["अलविदा", "बस इतना ही।", "धन्यवाद!", "shukriya", "Bas itna hi.", "फिर मिलते हैं"]) assert.equal(isGoodbye(phrase), true, phrase);
  for (const phrase of ["कल शाम तक रिपोर्ट जोड़ दो", "धन्यवाद, अब एक मीटिंग जोड़ दो", "shukriya, kal ki meeting hata do"]) assert.equal(isGoodbye(phrase), false, phrase);
  assert.equal(isGoodbye("नहीं", true), false);
  assert.equal(isGoodbye("नहीं"), true);
});
