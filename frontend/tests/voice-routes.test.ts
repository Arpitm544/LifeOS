import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { stripTypeScriptTypes } from "node:module";
import { runInNewContext } from "node:vm";

for (const [route, service] of [["transcribe", "transcriptionResponse"], ["speak", "speechResponse"]]) {
  test(`${route} requires authentication and same-origin before calling the provider`, async () => {
    let userId: string | null = null, calls = 0, quotaCalls = 0;
    let quotaResult: Response | null = null;
    const source = readFileSync(new URL(`../src/app/api/${route}/route.ts`, import.meta.url), "utf8").replace(/^import .*;\n/gm, "").replace("export async function POST", "async function POST");
    const handler = runInNewContext(stripTypeScriptTypes(source) + "; POST;", {
      auth: async () => ({ userId, getToken: async () => "session-token" }),
      voiceQuota: async (token: string, kind: string) => {
        assert.equal(token, "session-token"); assert.equal(kind, route);
        quotaCalls++; return quotaResult;
      }, Response, URL, process: { env: {} },
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
    quotaResult = Response.json({ error: "Limit reached" }, { status: 429 });
    assert.equal((await handler(request("http://localhost"))).status, 429);
    assert.equal(calls, 1, "quota rejection never reaches the paid provider");
    quotaResult = Response.json({ error: "Unavailable" }, { status: 503 });
    assert.equal((await handler(request("http://localhost"))).status, 503);
    assert.equal(calls, 1);
  });
}
