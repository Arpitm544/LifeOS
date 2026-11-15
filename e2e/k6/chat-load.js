// k6 load test (PRD 9 Scalability / Appendix B): 100 virtual users for 5 minutes on POST /api/chat.
// Run against a server with ENVIRONMENT=development, ALLOW_DEMO_AUTH=true and NO LLM key, so the
// quick-add path measures LifeOS logic only (target: p95 <= 300 ms, no errors). Raise CHAT_RATE_LIMIT
// on that server: each virtual user is its own demo user, but keep it well above 30/min if you share users.
//   k6 run -e API_URL=http://127.0.0.1:8000 k6/chat-load.js
import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  scenarios: { chat: { executor: "constant-vus", vus: Number(__ENV.VUS || 100), duration: __ENV.DURATION || "5m" } },
  thresholds: { http_req_failed: ["rate<0.01"], "http_req_duration{name:chat}": ["p(95)<300"], "http_req_duration{name:today}": ["p(95)<1500"] },
};

const API = (__ENV.API_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");
const texts = ["Buy groceries by tomorrow", "Finish the report on Friday", "Call the bank at 5 pm", "Pay rent by the 5th", "Read chapter 3 by Sunday"];

export default function () {
  const headers = { "Content-Type": "application/json", "X-Demo-User-Id": `user_k6_${__VU}` };
  const chat = http.post(`${API}/api/chat`, JSON.stringify({ text: texts[__ITER % texts.length], client_tz: "UTC" }),
    { headers: { ...headers, "Idempotency-Key": `k6-${__VU}-${__ITER}-${Date.now()}` }, tags: { name: "chat" } });
  check(chat, { "chat 200": r => r.status === 200, "has reply": r => !!r.json("reply") });
  const today = http.get(`${API}/api/today`, { headers, tags: { name: "today" } });
  check(today, { "today 200": r => r.status === 200 });
  sleep(2 + Math.random() * 2); // ~15 messages per user per 10 minutes, well under the 30/min limit
}
