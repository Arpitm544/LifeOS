import assert from "node:assert/strict";
import test from "node:test";
import { baseLanguage, replyLanguage, scriptLanguage, speechLocale } from "../src/lib/language.ts";

test("base language codes are normalised", () => {
  assert.equal(baseLanguage("hi-IN"), "hi");
  assert.equal(baseLanguage("PT_br"), "pt");
  assert.equal(baseLanguage("<x>"), null);
  assert.equal(baseLanguage(42), null);
});

test("script gives away some languages but not Latin-script text", () => {
  assert.equal(scriptLanguage("कल शाम तक रिपोर्ट"), "hi");
  assert.equal(scriptLanguage("明日までにレポート"), "ja");
  assert.equal(scriptLanguage("Отчёт к пятнице"), "ru");
  assert.equal(scriptLanguage("kal shaam tak report"), null);
});

test("reply language: setting, then what was heard, then script", () => {
  assert.equal(replyLanguage("es", "hi", "hola"), "es");
  assert.equal(replyLanguage("auto", "hi", "kal report"), "hi");
  assert.equal(replyLanguage("auto", "xx", "कल"), "hi");
  assert.equal(replyLanguage("auto", null, "plan my day"), null);
});

test("speech locales default to English", () => {
  assert.equal(speechLocale("hi"), "hi-IN");
  assert.equal(speechLocale("pt"), "pt-BR");
  assert.equal(speechLocale(null), "en-US");
  assert.equal(speechLocale("sw"), "en-US");
});
