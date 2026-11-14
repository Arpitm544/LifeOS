import { readRequestJson } from "./request-json.ts";

/** "es:aura-2-celeste-es,fr:aura-2-agathe-fr" -> { es: "aura-2-celeste-es", fr: "aura-2-agathe-fr" } */
export function parseVoices(value: string | undefined): Record<string, string> {
  const voices: Record<string, string> = Object.create(null);
  for (const entry of (value ?? "").split(",")) {
    const [code, voice] = entry.split(":").map(part => part?.trim());
    if (code && voice && /^[a-z]{2,3}$/.test(code) && /^[\w.-]+$/.test(voice)) voices[code] = voice;
  }
  return voices;
}

// `model` is the English voice; other languages need a voice in DEEPGRAM_TTS_VOICES, else the browser speaks.
export async function speechResponse(request: Request, apiKey: string | undefined, model: string, fetcher: typeof fetch = fetch, voiceConfig?: string) {
  const headers = { "Cache-Control": "no-store" };
  const error = (message: string, status: number) => Response.json({ error: message }, { status, headers });
  let text, language = "en";
  try {
    const data = await readRequestJson(request, 4000) as { text?: unknown; language?: unknown } | null;
    if (typeof data?.text !== "string" || !data.text.trim() || data.text.length > 500) return error("Spoken reply must contain 1–500 characters.", 400);
    text = data.text.trim();
    if (data.language !== undefined && data.language !== null) {
      if (typeof data.language !== "string" || !/^[a-z]{2,3}(-[A-Za-z0-9]{2,8})?$/i.test(data.language)) return error("Invalid reply language.", 400);
      language = data.language.toLowerCase().split("-")[0];
    }
  } catch (e) { return error(e instanceof RangeError ? "Spoken reply is too large." : "Invalid spoken reply.", e instanceof RangeError ? 413 : 400); }
  const voice = language === "en" ? model : parseVoices(voiceConfig)[language];
  if (!voice) return Response.json({ error: "No server voice for this language.", code: "unsupported_language" }, { status: 422, headers });
  if (!apiKey) return error("Spoken replies are not configured. Add DEEPGRAM_API_KEY to the server environment and restart the app.", 503);
  try {
    const query = new URLSearchParams({ model: voice, encoding: "mp3" });
    const response = await fetcher(`https://api.deepgram.com/v1/speak?${query}`, {
      method: "POST", headers: { Authorization: `Token ${apiKey}`, "Content-Type": "application/json" }, body: JSON.stringify({ text }),
      signal: AbortSignal.any([request.signal, AbortSignal.timeout(25_000)]),
    });
    if (!response.ok) {
      await response.body?.cancel();
      return error(response.status === 429 ? "Voice service is busy. Please retry shortly." : "Could not generate speech. Please retry.", response.status === 429 ? 429 : 502);
    }
    if (!response.body || !response.headers.get("content-type")?.startsWith("audio/")) {
      await response.body?.cancel();
      return error("Voice service returned invalid audio. Please retry.", 502);
    }
    return new Response(response.body, { headers: { ...headers, "Content-Type": "audio/mpeg" } });
  } catch { return error("Speech generation did not finish. Please retry.", 502); }
}
