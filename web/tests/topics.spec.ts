import {test, expect} from "@playwright/test";

test("topic map links full-corpus filters, both searches, and original records", async ({page}) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto("/#topics");
  await expect(page.getByRole("heading", {name:"A landscape of Danish."})).toBeVisible();
  await expect(page.locator(".topics-view")).toHaveAttribute("aria-busy","false");
  await expect(page.locator(".topic-map")).toHaveAttribute("aria-label", /21396 sampled records/);
  await expect(page.locator(".topic-row")).toHaveCount(29); // 28 topics + no vector
  await page.getByRole("button",{name:"Zoom in map",exact:true}).click();
  await expect(page.getByRole("button",{name:"Reset map zoom"})).toHaveClass(/changed/);
  await page.getByRole("button",{name:"Reset map zoom"}).click();
  await expect(page.getByRole("button",{name:"Reset map zoom"})).not.toHaveClass(/changed/);
  await page.getByLabel("Map colour by").selectOption("pii");
  await expect(page.locator(".map-legend")).toContainText("PII flagged");
  await expect(page.locator(".map-legend")).toContainText("Not annotated");
  await page.getByLabel("Map colour by").selectOption("topic");
  await page.getByLabel("Find a topic").fill("miljøvurdering");
  await expect(page.locator(".topic-row")).toHaveCount(1);
  await page.locator(".topic-row").click();
  await expect(page.locator(".topics-view")).toHaveAttribute("aria-busy","false");
  await expect(page.locator(".topic-details")).toContainText("44,716 records");
  await expect(page.locator(".topic-keywords")).toContainText("miljørapport");
  await expect(page.locator(".filter-chips")).toContainText("miljøvurdering");
  await expect(page.locator(".metric").first().locator("strong")).toHaveText("44.72K");
  await page.getByLabel("Search mode").selectOption("text");
  await page.getByLabel("Search the complete corpus").fill("vindmøller");
  await page.getByRole("button",{name:"Search",exact:true}).click();
  await expect(page.locator(".records-panel .count-badge")).toContainText("1.43K matches");
  await expect(page.locator(".record-table tbody tr")).toHaveCount(30);
  await page.getByRole("button",{name:"Load more records",exact:true}).click();
  await expect(page.locator(".record-table tbody tr")).toHaveCount(60);
  await page.getByLabel("Search mode").selectOption("semantic");
  await page.getByLabel("Search the complete corpus").fill("vedvarende energi");
  await page.getByRole("button",{name:"Search",exact:true}).click();
  await expect(page.locator(".records-panel .count-badge")).toContainText("300 ranked");
  await expect(page.locator(".records-panel")).toContainText("44,716 records compared");
  await page.locator(".mapped-records summary").click();
  await page.locator(".mapped-record-list>button").first().click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.locator(".reader-text")).not.toBeEmpty();
  await page.keyboard.press("Escape");
  await page.getByRole("button",{name:"Clear all",exact:true}).click();
  await expect(page.locator(".topics-view")).toHaveAttribute("aria-busy","false");
  await expect(page.locator(".metric").first().locator("strong")).toHaveText("7.4M");
  await expect(page.getByRole("alert")).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("canvas point interaction, mobile map, and unassigned coverage", async ({page}) => {
  await page.goto("/#topics");
  await expect(page.locator(".topics-view")).toHaveAttribute("aria-busy","false");
  await page.getByLabel("Map colour by").selectOption("domain");
  // Resolve a real rendered point to pixels, then click the canvas (not an
  // ECharts synthetic event). This verifies the full hit-testing/reader path.
  const point = await page.evaluate(async () => {
    const url = performance.getEntriesByType("resource").map(r => r.name).find(u => u.includes("/echarts_core.js"))!;
    const echarts = await import(url);
    const element = document.querySelector(".topic-map")!;
    const instance = echarts.getInstanceByDom(element);
    const series = instance.getOption().series;
    // Pick the leftmost dot to avoid overlap in the dense centre of the map.
    let candidate: any = null;
    series.forEach((s: any, i: number) => s.data?.forEach((d: any) => {
      if (d.recordNo !== undefined && (!candidate || d.value[0] < candidate.data.value[0])) candidate = {data:d,index:i};
    }));
    const position = instance.convertToPixel({seriesIndex:candidate.index},candidate.data.value);
    return {x:position[0],y:position[1],id:candidate.data.recordNo};
  });
  await page.locator(".topic-map").scrollIntoViewIfNeeded();
  const request = page.waitForResponse(r => new URL(r.url()).pathname === `/api/record/${point.id}` && r.status() === 200);
  const bounds = await page.locator(".topic-map").boundingBox();
  await page.mouse.click(bounds!.x+point.x, bounds!.y+point.y);
  await request;
  await expect(page.locator(".reader-text")).not.toBeEmpty();
  await page.keyboard.press("Escape");
  await page.getByLabel("Map colour by").selectOption("topic");
  await page.screenshot({path:"../.cache/topics-desktop.png",fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await page.evaluate(() => window.scrollTo(0,0));
  await expect(page.getByRole("button",{name:"Topics",exact:true})).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.getByLabel("Find a topic").fill("No topic vector");
  await page.locator(".topic-row").click();
  await expect(page.locator(".topics-view")).toHaveAttribute("aria-busy","false");
  await expect(page.locator(".map-empty")).toContainText("No mapped records");
  await expect(page.locator(".metric").first().locator("strong")).toHaveText("962");
  await expect(page.locator(".record-title").first()).toBeVisible();
  await page.getByRole("button",{name:"Clear topic",exact:true}).click();
  await page.getByRole("button",{name:"Clear topic search",exact:true}).click();
  await expect(page.locator(".topics-view")).toHaveAttribute("aria-busy","false");
  await page.locator(".topic-map-panel").scrollIntoViewIfNeeded();
  await page.screenshot({path:"../.cache/topics-mobile.png",fullPage:true});
});
