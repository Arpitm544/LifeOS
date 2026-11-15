// Behind a reverse proxy (Caddy, Vercel, nginx) the server sees an internal URL such as
// http://0.0.0.0:3000, so request.url alone never matches the browser's https:// origin.
// Use the forwarded host/proto the proxy sets, falling back to request.url when there is none.
export function isSameOrigin(request: Request): boolean {
  const origin = request.headers.get("origin");
  if (!origin) return false;
  const url = new URL(request.url);
  const host = request.headers.get("x-forwarded-host")?.split(",")[0].trim() || request.headers.get("host") || url.host;
  const proto = request.headers.get("x-forwarded-proto")?.split(",")[0].trim() || url.protocol.replace(/:$/, "");
  return origin === `${proto}://${host}`;
}
