import { auth } from "@clerk/nextjs/server";
import { transcriptionResponse } from "@/lib/transcription-service";

import { isSameOrigin } from "@/lib/same-origin";
import { voiceQuota } from "@/lib/voice-quota";

export async function POST(request: Request) {
  const { userId, getToken } = await auth();
  if (!userId) return Response.json({ error: "Sign in to use voice input." }, { status: 401 });
  if (!isSameOrigin(request)) return Response.json({ error: "Invalid request origin." }, { status: 403 });
  const limited = await voiceQuota(await getToken(), "transcribe", request.signal);
  if (limited) return limited;
  return transcriptionResponse(request, process.env.DEEPGRAM_API_KEY, process.env.DEEPGRAM_TRANSCRIPTION_MODEL || "nova-3");
}
