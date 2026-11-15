import assert from "node:assert/strict";
import test from "node:test";
import { baseLanguage, replyLanguage, scriptLanguage, speechLocale } from "../src/lib/language.ts";

test("base language codes are normalised", () => {
  assert.equal(baseLanguage("hi-IN"), "hi");
  assert.equal(baseLanguage("PT_br"), "pt");
  assert.equal(baseLanguage("<x>"), null);
  assert.equal(baseLanguage(42), null);
});

test("Devanagari gives Hindi away; other scripts and Latin text stay unknown", () => {
  assert.equal(scriptLanguage("कल शाम तक रिपोर्ट"), "hi");
  assert.equal(scriptLanguage("明日までにレポート"), null);
  assert.equal(scriptLanguage("kal shaam tak report"), null);
});

test("reply language: setting, then what was heard, then script", () => {
  assert.equal(replyLanguage("en", "hi", "kal report"), "en");
  assert.equal(replyLanguage("auto", "hi", "kal report"), "hi");
  assert.equal(replyLanguage("auto", "es", "hola"), null); // only English and Hindi: other languages get English
  assert.equal(replyLanguage("auto", "xx", "कल"), "hi");
  assert.equal(replyLanguage("auto", null, "plan my day"), null);
});

test("speech locales default to English", () => {
  assert.equal(speechLocale("hi"), "hi-IN");
  assert.equal(speechLocale("pt"), "en-US");
  assert.equal(speechLocale(null), "en-US");
  assert.equal(speechLocale("sw"), "en-US");
});
