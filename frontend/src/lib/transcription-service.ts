const maxAudioBytes = 4_000_000;
const formats: Record<string, string> = { "audio/webm": "webm", "audio/mp4": "m4a", "audio/ogg": "ogg", "audio/wav": "wav" };
// A language pinned in Chat settings (English or Hindi) is sent to Deepgram as-is. "Auto" uses "multi", which
// is built for English and Hindi mixed together (Hinglish), so it suits people who switch between the two.
const pinnable = new Set(["en", "hi"]);

export async function transcriptionResponse(request: Request, apiKey: string | undefined, model: string, fetcher: typeof fetch = fetch) {
  const headers = { "Cache-Control": "no-store" };
  const error = (message: string, status: number) => Response.json({ error: message }, { status, headers });
  if (!apiKey) { console.error("DEEPGRAM_API_KEY is not set; voice transcription is disabled."); return error("Voice input is unavailable right now. Please type your message.", 503); }
  const type = request.headers.get("content-type")?.split(";")[0].trim().toLowerCase() || "";
  if (!Object.hasOwn(formats, type)) return error("Unsupported recording format. Try another browser or type your message.", 415);
  if (Number(request.headers.get("content-length")) > maxAudioBytes) return error("Recording is too large. Please record a shorter message.", 413);
  const reader = request.body?.getReader();
  if (!reader) return error("No audio received. Please record again.", 400);
  try {
    const chunks: Uint8Array<ArrayBuffer>[] = [];
    let size = 0;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > maxAudioBytes) { await reader.cancel(); return error("Recording is too large. Please record a shorter message.", 413); }
      chunks.push(new Uint8Array(value));
    }
    if (!size) return error("No audio received. Please record again.", 400);
    const hint = request.headers.get("x-transcribe-language")?.trim().toLowerCase() ?? "";
    const query = new URLSearchParams({ model, language: pinnable.has(hint) ? hint : "multi", smart_format: "true" });
    const response = await fetcher(`https://api.deepgram.com/v1/listen?${query}`, {
      method: "POST", headers: { Authorization: `Token ${apiKey}`, "Content-Type": type }, body: new Blob(chunks, { type }),
      signal: AbortSignal.any([request.signal, AbortSignal.timeout(25_000)]),
    });
    if (!response.ok) {
      console.error(`Deepgram listen request failed with status ${response.status}`);
      await response.body?.cancel();
      return error(response.status === 429 ? "Voice service is busy. Please retry shortly." : "Could not transcribe the recording. Please retry.", response.status === 429 ? 429 : 502);
    }
    const result = await response.json();
    const channel = result.results?.channels?.[0];
    const transcript = channel?.alternatives?.[0]?.transcript;
    if (typeof transcript !== "string") return error("The voice service returned an invalid transcript. Please retry.", 502);
    const text = transcript.trim();
    if (!text) return error("No speech detected. Please try again.", 422);
    if (text.length > 1000) return error("That transcript exceeds 1,000 characters. Please record a shorter message.", 422);
    // Multilingual models list the languages heard, most used first; detect_language sets detected_language.
    const heard = channel?.alternatives?.[0]?.languages?.[0] ?? channel?.detected_language;
    const language = typeof heard === "string" && /^[a-z]{2,3}(-[A-Za-z0-9]{2,8})?$/i.test(heard) ? heard.toLowerCase() : null;
    return Response.json({ text, language }, { headers });
  } catch {
    return error("Transcription did not finish. Please retry or type your message.", 502);
  } finally { reader.releaseLock(); }
}
