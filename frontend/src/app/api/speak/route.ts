import { auth } from "@clerk/nextjs/server";
import { parseVoices, speechResponse } from "@/lib/speech-service";

import { voiceQuota } from "@/lib/voice-quota";

export async function POST(request: Request) {
  const { userId, getToken } = await auth();
  if (!userId) return Response.json({ error: "Sign in to hear replies." }, { status: 401 });
  if (request.headers.get("origin") !== new URL(request.url).origin) return Response.json({ error: "Invalid request origin." }, { status: 403 });
  // A language with no server voice (Hindi) is read by the device, so answer that before spending voice quota.
  const asked = await request.clone().json().catch(() => null) as { language?: unknown } | null;
  const language = typeof asked?.language === "string" ? asked.language.toLowerCase().split("-")[0] : "en";
  if (language !== "en" && !parseVoices(process.env.DEEPGRAM_TTS_VOICES)[language]) {
    return Response.json({ error: "No server voice for this language.", code: "unsupported_language" }, { status: 422, headers: { "Cache-Control": "no-store" } });
  }
  const limited = await voiceQuota(await getToken(), "speak", request.signal);
  if (limited) return limited;
  // English uses Deepgram's Aura voice. Deepgram has no Hindi voice (checked against /v1/models), so Hindi replies
  // are read by the device's Hindi voice in the browser.
  return speechResponse(request, process.env.DEEPGRAM_API_KEY, process.env.DEEPGRAM_TTS_MODEL || "aura-2-thalia-en", undefined, process.env.DEEPGRAM_TTS_VOICES);
}
