import { expect, test } from "@playwright/test";

import { ALERT, openJob, signIn } from "./helpers";

// Brief bars: an override without a real reason is refused by the form (the API tests
// cover the API side); a stale page cannot decide twice.

async function openFirstWithBand(page: import("@playwright/test").Page, band: string) {
  await page.locator("#f-band").selectOption(band);
  await page.locator("#f-state").selectOption("SCORED");
  await page.getByRole("button", { name: "Filter" }).click();
  await page.locator("[data-row-link]").first().click();
  await expect(page.getByRole("heading", { name: "Evidence" })).toBeVisible();
}

test("an override needs a reason of at least 10 characters", async ({ page }) => {
  await signIn(page);
  await openJob(page, "Data Analyst");
  await openFirstWithBand(page, "reject");
  await page.screenshot({ path: "test-results/candidate-page.png", fullPage: true });
  const url = page.url();
  await page.keyboard.press("s");
  await expect(page.getByRole("dialog")).toContainText("This goes against the recommendation");
  await page.keyboard.press("Enter");
  await expect(page.locator(ALERT)).toContainText("at least 10 characters");
  await page.getByLabel("Reason").fill("too short");
  await page.keyboard.press("Enter");
  await expect(page.locator(ALERT)).toContainText("at least 10 characters");
  expect(page.url()).toBe(url);
  await page.getByLabel("Reason").fill("Portfolio shows SQL work the CV does not mention");
  await page.keyboard.press("Enter");
  await page.waitForURL((u) => u.toString() !== url);
  await page.goto(url);
  await expect(page.getByText(/Strong portfolio|Portfolio shows SQL work/)).toBeVisible();
});

test("a stale page gets a conflict message, not a second decision", async ({ browser }) => {
  const ctx = await browser.newContext();
  const a = await ctx.newPage();
  await signIn(a);
  await openJob(a, "Data Analyst");
  await openFirstWithBand(a, "advance");
  const b = await ctx.newPage();
  await b.goto(a.url());
  await expect(b.getByRole("heading", { name: "Evidence" })).toBeVisible();

  await a.keyboard.press("s");
  await a.keyboard.press("Enter");
  await a.waitForURL((u) => !u.toString().endsWith(new URL(b.url()).pathname));

  await b.keyboard.press("r");
  await b.getByLabel("Reason").fill("Second tab tries to reject the same candidate");
  await b.keyboard.press("Enter");
  await expect(b.locator(ALERT)).toContainText("changed since you opened it");
  await ctx.close();
});
