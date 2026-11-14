// Chat languages: the ones Deepgram's multilingual model transcribes (nova-3, language=multi).
export const languages = [
  { code: "en", label: "English", locale: "en-US" },
  { code: "hi", label: "हिन्दी · Hindi", locale: "hi-IN" },
  { code: "es", label: "Español · Spanish", locale: "es-ES" },
  { code: "fr", label: "Français · French", locale: "fr-FR" },
  { code: "de", label: "Deutsch · German", locale: "de-DE" },
  { code: "pt", label: "Português · Portuguese", locale: "pt-BR" },
  { code: "it", label: "Italiano · Italian", locale: "it-IT" },
  { code: "nl", label: "Nederlands · Dutch", locale: "nl-NL" },
  { code: "ru", label: "Русский · Russian", locale: "ru-RU" },
  { code: "ja", label: "日本語 · Japanese", locale: "ja-JP" },
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

/** Languages whose script gives them away; Latin-script text stays unknown. */
export function scriptLanguage(text: string): string | null {
  if (/[ऀ-ॿ]/.test(text)) return "hi";
  if (/[぀-ヿ]/.test(text)) return "ja";
  if (/[Ѐ-ӿ]/.test(text)) return "ru";
  return null;
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

export function saveLanguageSetting(value: LanguageSetting) {
  try { window.localStorage.setItem(storageKey, value); } catch { /* per-device convenience only */ }
}
