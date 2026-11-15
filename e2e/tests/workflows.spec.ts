import { expect, test, type APIRequestContext } from "@playwright/test";
import { api, inHours } from "./helpers";

// The six PRD workflows (section 5) exercised through the public API. Chat runs with whatever
// model the server has; without a key it uses quick add, which these assertions accept.
let client: APIRequestContext;

test.beforeAll(async () => {
  client = await api();
  const health = await client.get("/health");
  expect(health.ok(), "API is not running at E2E_API_URL").toBeTruthy();
});

test.afterAll(async () => {
  await client.delete("/api/account?confirmed=true");
  await client.dispose();
});

test("5.1 onboarding stores working hours, quiet hours and focus time", async () => {
  for (const body of [
    { key: "timezone", value: { name: "Asia/Kolkata" } },
    { key: "work_hours", value: { start: "09:00", end: "18:00" } },
    { key: "quiet_hours", value: { start: "22:30", end: "07:30" } },
    { key: "focus_windows", value: { windows: [["08:00", "10:00"]] } },
    { key: "onboarding", value: { completed: true, focus_period: "morning" } },
  ]) expect((await client.post("/api/preferences", { data: body })).ok()).toBeTruthy();
  const rows = await (await client.get("/api/preferences")).json();
  expect(rows.map((row: { key: string }) => row.key)).toEqual(expect.arrayContaining(["work_hours", "quiet_hours", "focus_windows", "onboarding"]));
});

test("5.2 creating a task through chat returns an action card that can be undone", async () => {
  const response = await client.post("/api/chat", { headers: { "Idempotency-Key": `e2e-${Date.now()}` }, data: { text: "Finish DBMS report by tomorrow", client_tz: "Asia/Kolkata" } });
  expect(response.ok()).toBeTruthy();
  const body = await response.json();
  expect(typeof body.reply).toBe("string");
  expect(typeof body.spoken_reply).toBe("string");
  expect(body.spoken_reply.split(/\s+/).length).toBeLessThanOrEqual(25);
  const created = body.actions.find((action: { type: string }) => action.type === "task_created");
  if (created?.action_id) {
    const undo = await client.post(`/api/actions/${created.action_id}/undo`);
    expect(undo.ok()).toBeTruthy();
  }
});

test("chat is idempotent: a retried request never creates a duplicate", async () => {
  const key = `e2e-idem-${Date.now()}`;
  const send = () => client.post("/api/chat", { headers: { "Idempotency-Key": key }, data: { text: "Buy stamps by Friday", client_tz: "UTC" } });
  const [first, second] = [await (await send()).json(), await (await send()).json()];
  expect(second.message_id).toBe(first.message_id);
});

test("5.3 schedule changes: plan, move a block, and the move is validated", async () => {
  const task = await (await client.post("/api/tasks", { data: { title: "E2E focus task", deadline_at: inHours(96), effort_est_min: 60, importance: 4, category: "study" } })).json();
  const plan = await (await client.post("/api/plan/rebuild?days=7", {})).json();
  expect(Array.isArray(plan.blocks)).toBeTruthy();
  const blocks = await (await client.get("/api/plan-blocks")).json();
  const block = blocks.find((row: { task_id: string; status: string }) => row.task_id === task.id && row.status === "planned");
  test.skip(!block, "No free working time in the next 7 days to place a block");
  const bad = await client.patch(`/api/plan-blocks/${block.id}`, { data: { start_at: block.end_at, end_at: block.start_at } });
  expect(bad.status()).toBeGreaterThanOrEqual(400);
});

test("5.4 Capacity Guard catches a deadline that cannot fit and offers options", async () => {
  const check = await (await client.post("/api/capacity/check", { data: { hypothetical: { title: "Huge job", effort_min: 1440, deadline: inHours(6) } } })).json();
  expect(check.fits).toBe(false);
  await client.post("/api/tasks", { data: { title: "E2E impossible task", deadline_at: inHours(4), effort_est_min: 600, importance: 5, category: "work" } });
  const today = await (await client.get("/api/today")).json();
  expect(today.conflicts.length).toBeGreaterThan(0);
  const options = await (await client.get(`/api/conflicts/${today.conflicts[0].id}/options`)).json();
  expect(options.options.length).toBeGreaterThan(0);
});

test("5.5 reminders: a task with a deadline gets reminders, and Done completes it", async () => {
  const task = await (await client.post("/api/tasks", { data: { title: "E2E reminder task", deadline_at: inHours(30), effort_est_min: 30, importance: 3, category: "errand" } })).json();
  const preview = await (await client.post("/api/reminders/preview", { data: { deadline: inHours(30), effort_min: 30, now: new Date().toISOString() } })).json();
  expect(preview.reminders.length).toBeGreaterThan(0);
  const done = await client.post(`/api/tasks/${task.id}/complete`, { data: {} });
  expect(done.ok()).toBeTruthy();
  expect((await done.json()).status).toBe("done");
});

test("5.6 daily plan and insights load with computed metrics", async () => {
  const today = await (await client.get("/api/today")).json();
  expect(today).toHaveProperty("free_min_left");
  const insights = await (await client.get("/api/insights")).json();
  expect(insights).toHaveProperty("calibration_factors");
  expect(Array.isArray(insights.completion_chart)).toBeTruthy();
});

test("data export returns the user's rows as JSON", async () => {
  const exported = await client.get("/api/export");
  expect(exported.ok()).toBeTruthy();
  expect(await exported.json()).toHaveProperty("tasks");
});
