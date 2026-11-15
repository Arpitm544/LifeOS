import { expect, test } from "@playwright/test";

// UI smoke tests that need no sign-in. Signed-in flows are covered by workflows.spec.ts through the API.
test("landing page loads and links to sign in", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveTitle(/LifeOS/i);
  await expect(page.getByRole("link", { name: /sign in|get started|log in/i }).first()).toBeVisible();
});

test("workspace routes require sign-in, including notification deep links", async ({ page }) => {
  for (const path of ["/today", "/today?replan=1", "/task/00000000-0000-4000-8000-000000000000", "/onboarding"]) {
    await page.goto(path);
    await expect(page).toHaveURL(/sign-in|accounts\.dev|clerk/i);
  }
});

test("service worker is served", async ({ request }) => {
  const response = await request.get("/sw.js");
  expect(response.ok()).toBeTruthy();
  expect(await response.text()).toContain("notificationclick");
});
