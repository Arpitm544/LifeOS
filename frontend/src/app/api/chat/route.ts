import { auth } from "@clerk/nextjs/server";
import { chatResponse } from "@/lib/chat-service";

export async function POST(request: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Sign in to use chat." }, { status: 401 });
  if (request.headers.get("origin") !== new URL(request.url).origin) return Response.json({ error: "Invalid request origin." }, { status: 403 });
  return chatResponse(request, process.env.GEMINI_API_KEY, process.env.GEMINI_MODEL || "gemini-3.5-flash");
}
