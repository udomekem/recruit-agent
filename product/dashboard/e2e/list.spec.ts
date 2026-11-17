import { expect, test } from "@playwright/test";

import { signIn } from "./helpers";

// The all-jobs list draws one page of rows (100) and "Show more" adds the next page
// (phase 5B evals: drawing every row took 9 s at ~1,800 candidates).
test("the candidate list draws 100 rows at a time", async ({ page }) => {
  await signIn(page);
  const rows = page.locator("[data-row-link]");
  const first = await rows.count();
  expect(first).toBeGreaterThan(0);
  expect(first).toBeLessThanOrEqual(100);
  const more = page.getByRole("link", { name: /^Show \d+ more/ });
  if (first < 100) {
    await expect(more).toHaveCount(0);
    return;
  }
  await more.click();
  await page.waitForURL(/show=200/);
  await expect.poll(() => rows.count()).toBeGreaterThan(100);
  expect(await rows.count()).toBeLessThanOrEqual(200);
});
