// Supported languages: English and Hindi (Hinglish too: Deepgram's nova-3 "multi" handles mixing the two).
// Anything else that is detected is answered in English.
export const languages = [
  { code: "en", label: "English", locale: "en-US" },
  { code: "hi", label: "हिन्दी · Hindi", locale: "hi-IN" },
] as const;

export type LanguageSetting = "auto" | (typeof languages)[number]["code"];
const codes = new Set<string>(languages.map(l => l.code));
const storageKey = "lifeos.chat-language";

/** "hi-IN" -> "hi"; unknown or malformed codes -> null. */
export function baseLanguage(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const base = value.trim().toLowerCase().split(/[-_]/)[0];
  return /^[a-z]{2,3}$/.test(base) ? base : null;
}

/** Devanagari script gives Hindi away; Latin-script text (English or romanised Hindi) stays unknown. */
export function scriptLanguage(text: string): string | null {
  return /[ऀ-ॿ]/.test(text) ? "hi" : null;
}

/** The setting wins; otherwise what Deepgram heard; otherwise the script of what was typed. */
export function replyLanguage(setting: LanguageSetting, spoken: string | null | undefined, text: string): string | null {
  if (setting !== "auto") return setting;
  const heard = baseLanguage(spoken);
  if (heard && codes.has(heard)) return heard;
  return scriptLanguage(text);
}

export function speechLocale(language: string | null | undefined): string {
  const base = baseLanguage(language);
  return languages.find(l => l.code === base)?.locale ?? "en-US";
}

export function readLanguageSetting(): LanguageSetting {
  try {
    const value = window.localStorage.getItem(storageKey);
    return value && (value === "auto" || codes.has(value)) ? value as LanguageSetting : "auto";
  } catch { return "auto"; }
}

/** The language the user pinned in Chat settings, or null for "auto". */
export function pinnedLanguage(): string | null {
  const setting = readLanguageSetting();
  return setting === "auto" ? null : setting;
}

export function saveLanguageSetting(value: LanguageSetting) {
  try { window.localStorage.setItem(storageKey, value); } catch { /* per-device convenience only */ }
}
