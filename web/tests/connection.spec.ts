import { test, expect } from "@playwright/test";

test("recovers automatically when the backend wakes", async ({ page }) => {
  let requests = 0;
  let awake = false;
  await page.route("**/api/manifest", async (route) => {
    requests++;
    if (!awake) {
      await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "Starting" }) });
    } else {
      await route.continue();
    }
  });
  await page.goto("./");
  await expect(page.getByRole("heading", { name: "Waiting for the data service" })).toBeVisible();
  awake = true;
  await expect(page.getByText("Complete Danish corpus", { exact: true })).toBeVisible({ timeout: 30000 });
  expect(requests).toBeGreaterThanOrEqual(2);
});
