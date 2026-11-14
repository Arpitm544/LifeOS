import { readRequestJson } from "./request-json.ts";

export async function speechResponse(request: Request, apiKey: string | undefined, model: string, fetcher: typeof fetch = fetch) {
  const headers = { "Cache-Control": "no-store" };
  const error = (message: string, status: number) => Response.json({ error: message }, { status, headers });
  let text;
  try {
    const data = await readRequestJson(request, 4000) as { text?: unknown } | null;
    if (typeof data?.text !== "string" || !data.text.trim() || data.text.length > 500) return error("Spoken reply must contain 1–500 characters.", 400);
    text = data.text.trim();
  } catch (e) { return error(e instanceof RangeError ? "Spoken reply is too large." : "Invalid spoken reply.", e instanceof RangeError ? 413 : 400); }
  if (!apiKey) return error("Spoken replies are not configured. Add DEEPGRAM_API_KEY to the server environment and restart the app.", 503);
  try {
    const query = new URLSearchParams({ model, encoding: "mp3" });
    const response = await fetcher(`https://api.deepgram.com/v1/speak?${query}`, {
      method: "POST", headers: { Authorization: `Token ${apiKey}`, "Content-Type": "application/json" }, body: JSON.stringify({ text }),
      signal: AbortSignal.any([request.signal, AbortSignal.timeout(25_000)]),
    });
    if (!response.ok) return error(response.status === 429 ? "Voice service is busy. Please retry shortly." : "Could not generate speech. Please retry.", response.status === 429 ? 429 : 502);
    if (!response.body || !response.headers.get("content-type")?.startsWith("audio/")) return error("Voice service returned invalid audio. Please retry.", 502);
    return new Response(response.body, { headers: { ...headers, "Content-Type": "audio/mpeg" } });
  } catch { return error("Speech generation did not finish. Please retry.", 502); }
}
