import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { stripTypeScriptTypes } from "node:module";
import { runInNewContext } from "node:vm";
import { isSameOrigin } from "../src/lib/same-origin.ts";

for (const [route, service] of [["transcribe", "transcriptionResponse"], ["speak", "speechResponse"]]) {
  test(`${route} requires authentication and same-origin before calling the provider`, async () => {
    let userId: string | null = null, calls = 0, quotaCalls = 0;
    let quotaResult: Response | null = null;
    const source = readFileSync(new URL(`../src/app/api/${route}/route.ts`, import.meta.url), "utf8").replace(/^import .*;\r?\n/gm, "").replace("export async function POST", "async function POST");
    const handler = runInNewContext(stripTypeScriptTypes(source) + "; POST;", {
      auth: async () => ({ userId, getToken: async () => "session-token" }),
      voiceQuota: async (token: string, kind: string) => {
        assert.equal(token, "session-token"); assert.equal(kind, route);
        quotaCalls++; return quotaResult;
      }, Response, URL, isSameOrigin, process: { env: {} },
      [service]: async () => { calls++; return Response.json({ ok: true }); },
    });
    const request = (origin?: string) => new Request(`http://localhost/api/${route}`, { method: "POST", headers: origin ? { Origin: origin } : {} });
    assert.equal((await handler(request("http://localhost"))).status, 401);
    userId = "signed-in";
    assert.equal((await handler(request("https://elsewhere.example"))).status, 403);
    assert.equal((await handler(request())).status, 403);
    assert.equal(calls, 0);
    assert.equal(quotaCalls, 0);
    assert.equal((await handler(request("http://localhost"))).status, 200);
    assert.equal(calls, 1);
    // Behind a reverse proxy request.url is the internal address; the forwarded host/proto describe the browser's view.
    const proxied = (origin: string, host: string) => new Request(`http://0.0.0.0:3000/api/${route}`, { method: "POST", headers: { Origin: origin, "X-Forwarded-Host": host, "X-Forwarded-Proto": "https" } });
    assert.equal((await handler(proxied("https://app.example.com", "app.example.com"))).status, 200);
    assert.equal((await handler(proxied("https://evil.example", "app.example.com"))).status, 403);
    assert.equal((await handler(proxied("http://app.example.com", "app.example.com"))).status, 403);
    assert.equal(calls, 2);
    calls = 1;
    quotaResult = Response.json({ error: "Limit reached" }, { status: 429 });
    assert.equal((await handler(request("http://localhost"))).status, 429);
    assert.equal(calls, 1, "quota rejection never reaches the paid provider");
    quotaResult = Response.json({ error: "Unavailable" }, { status: 503 });
    assert.equal((await handler(request("http://localhost"))).status, 503);
    assert.equal(calls, 1);
  });
}
