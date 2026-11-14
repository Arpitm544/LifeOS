import { auth } from "@clerk/nextjs/server";
import { speechResponse } from "@/lib/speech-service";

export async function POST(request: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Sign in to hear replies." }, { status: 401 });
  if (request.headers.get("origin") !== new URL(request.url).origin) return Response.json({ error: "Invalid request origin." }, { status: 403 });
  return speechResponse(request, process.env.DEEPGRAM_API_KEY, process.env.DEEPGRAM_TTS_MODEL || "aura-2-thalia-en");
}
