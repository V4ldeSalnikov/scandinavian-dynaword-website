import { test, expect } from "@playwright/test";

test("complete corpus, linked filters, annotations, and reader", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("./");
  await expect(
    page.getByText("Complete Danish corpus", { exact: true }),
  ).toBeVisible();
  await expect(page.locator(".metric").first().locator("strong")).toHaveText(
    "7.4M",
  );
  await expect(page.locator(".record-title").first()).toBeVisible();
  await page.screenshot({
    path: "../.cache/desktop-overview.png",
    fullPage: true,
  });
  await page.locator("#domain").selectOption("News");
  await expect(page.locator(".filter-chips")).toContainText("News");
  await expect(page.locator(".metrics")).toHaveAttribute("aria-busy", "false");
  const filtered = await page
    .locator(".metric")
    .first()
    .locator("strong")
    .textContent();
  expect(filtered).not.toEqual("7.4M");
  await page.locator("#pii").selectOption("contains_pii");
  await expect(page.locator(".metrics")).toHaveAttribute("aria-busy", "false");
  await expect(page.locator(".record-table tbody tr").first()).toContainText(
    "Flagged",
  );
  await page.getByLabel("Minimum tokens", { exact: true }).fill("100");
  await page.getByLabel("Maximum tokens", { exact: true }).fill("1000");
  await expect(page.locator(".metrics")).toHaveAttribute("aria-busy", "false");
  await expect(page.locator(".record-title").first()).toBeVisible();
  await page.locator(".record-title").first().click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.locator(".reader-text")).not.toBeEmpty();
  await page.getByRole("button", { name: "Metadata & annotations" }).click();
  await expect(page.locator(".metadata-list")).toContainText("contains_pii");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await page.getByRole("button", { name: "Clear all", exact: true }).click();
  await expect(page.locator(".metric").first().locator("strong")).toHaveText(
    "7.4M",
  );
  await page
    .getByRole("button", { name: "Load more records", exact: true })
    .click();
  await expect(page.locator(".record-table tbody tr")).toHaveCount(60);
  await page.locator(".record-title").first().click();
  await expect(page.locator(".reader-text")).not.toBeEmpty();
  const before = (await page.locator(".reader-text").textContent())!.length;
  await page
    .getByRole("button", { name: "Load more text", exact: true })
    .click();
  await expect
    .poll(
      async () => (await page.locator(".reader-text").textContent())!.length,
    )
    .toBeGreaterThan(before);
  await page.keyboard.press("Escape");
  await page.getByLabel("Annotation to visualise").selectOption("content_type");
  await expect(page.locator(".annotations .panel-foot")).toContainText(
    "Multiple labels",
  );
  await expect(page.getByRole("alert")).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("full-text search, pagination, and source documents", async ({ page }) => {
  await page.goto("./");
  await expect(
    page.getByText("Complete Danish corpus", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("Search mode").selectOption("text");
  await page.getByLabel("Search the complete corpus").fill("vindmøller");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.locator(".records-panel .count-badge")).toContainText(
    "matches",
  );
  await expect(page.locator(".record-title").first()).toBeVisible();
  await expect(page.locator(".records-panel")).toContainText("vindmøller");
  await expect(page.locator(".metric").first().locator("strong")).toHaveText(
    "7.4M",
  );
  await page.getByRole("button", { name: "Sources", exact: true }).click();
  await expect(page.locator(".source-card")).toHaveCount(50);
  await page.locator(".source-card").first().click();
  await expect(page.getByRole("dialog")).toContainText("Source licence");
  await page.getByRole("button", { name: "Explore this source" }).click();
  await expect(page.locator(".filter-chips button")).toHaveCount(2);
});

test("mobile layout and filter access", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("./");
  await expect(
    page.getByText("Complete Danish corpus", { exact: true }),
  ).toBeVisible();
  await expect(page.locator(".metrics")).toHaveAttribute("aria-busy", "false");
  await page.getByRole("button", { name: "Open filters", exact: true }).click();
  await expect(page.locator(".sidebar")).toBeVisible();
  await page.locator("#quality").selectOption("good");
  await page
    .getByRole("button", { name: "Close filters", exact: true })
    .click();
  await expect(page.locator(".sidebar")).not.toBeVisible();
  await expect(page.locator(".filter-chips")).toContainText("Good");
  const dimensions = await page.evaluate(() => ({
    width: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
  }));
  expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.width + 1);
  await expect(page.locator(".metrics")).toHaveAttribute("aria-busy", "false");
  await expect(page.locator(".metric").first().locator("strong")).toHaveText(
    "2.78M",
  );
  await page.screenshot({
    path: "../.cache/mobile-overview.png",
    fullPage: true,
  });
});

test("chart clicks, brush ranges, and keyboard-readable values", async ({
  page,
}) => {
  await page.goto("./");
  await expect(page.locator(".metrics")).toHaveAttribute("aria-busy", "false");
  const composition = page.locator('.composition [role="img"]');
  const box = await composition.boundingBox();
  await page.mouse.click(box!.x + 150, box!.y + 16);
  await expect(page.locator("#domain")).toHaveValue("Other");
  await expect(page.locator(".metrics")).toHaveAttribute("aria-busy", "false");
  await page.getByRole("button", { name: "Clear all", exact: true }).click();
  await expect(page.locator(".metrics")).toHaveAttribute("aria-busy", "false");
  const histogram = page.locator('.lengths [role="img"]');
  await histogram.scrollIntoViewIfNeeded();
  const h = await histogram.boundingBox();
  const plot = h!.width - 65;
  await page.mouse.move(h!.x + 47 + (plot * 3.2) / 22, h!.y + 40);
  await page.mouse.down();
  await page.mouse.move(h!.x + 47 + (plot * 5.7) / 22, h!.y + 80, {
    steps: 12,
  });
  await page.mouse.up();
  await expect(page.getByLabel("Minimum tokens", { exact: true })).toHaveValue(
    "64",
  );
  await expect(page.getByLabel("Maximum tokens", { exact: true })).toHaveValue(
    "511",
  );
  await page.locator(".lengths summary").click();
  await expect(page.locator(".lengths .chart-data table")).toBeVisible();
  await expect(page.locator(".lengths .chart-data")).toContainText(
    "64–127 tokens",
  );
});

test("semantic search ranks the corpus slice and retains original-text access", async ({
  page,
}) => {
  await page.goto("./");
  await expect(page.getByLabel("Search mode")).toHaveValue("semantic");
  await page
    .getByLabel("Search the complete corpus")
    .fill("vedvarende energi vindmøller");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.locator(".records-panel .count-badge")).toContainText(
    "300 ranked",
  );
  await expect(page.locator(".record-title").first()).toBeVisible();
  await expect(page.locator(".records-panel")).toContainText(
    "Danish word vectors",
  );
  await expect(page.locator(".metric").first().locator("strong")).toHaveText(
    "7.4M",
  );
  await page.locator("#domain").selectOption("Encyclopedic");
  await expect(page.locator(".record-title").first()).toBeVisible();
  await page.locator(".record-title").first().click();
  await expect(page.locator(".reader-text")).not.toBeEmpty();
  await page.getByRole("button", { name: "Metadata & annotations" }).click();
  await expect(page.locator(".metadata-list")).toContainText("Encyclopedic");
  await page.screenshot({ path: "../.cache/record-reader.png" });
});
