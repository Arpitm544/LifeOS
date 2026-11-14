export async function readRequestJson(request: Request, limit: number): Promise<unknown> {
  if (Number(request.headers.get("content-length")) > limit) throw new RangeError("Request too large");
  const reader = request.body?.getReader();
  if (!reader) throw new Error("Missing body");
  const chunks: Uint8Array<ArrayBuffer>[] = [];
  let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > limit) { await reader.cancel(); throw new RangeError("Request too large"); }
      chunks.push(new Uint8Array(value));
    }
    return JSON.parse(await new Blob(chunks).text());
  } finally { reader.releaseLock(); }
}
