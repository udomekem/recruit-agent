import { expect, test } from "@playwright/test";

import { openJob, signIn } from "./helpers";

// Brief bar: a recruiter reviews 50 seeded candidates in at most 2 actions each.
// An action is a key press or a click (design Q2). Each decision agrees with the AI:
// s for advance or maybe, r for reject, then Enter.
test("50 candidates decided with the keyboard, 2 actions each", async ({ page }) => {
  test.setTimeout(600_000);
  await signIn(page);
  await openJob(page, "Data Analyst (review drill)");
  await page.getByRole("link", { name: "Review next undecided" }).click();

  let actions = 0;
  let decided = 0;
  const started = Date.now();
  for (let i = 0; i < 50; i++) {
    const badge = page.getByText(/AI recommendation: (Advance|Maybe|Reject)/);
    await expect(badge).toBeVisible();
    const band = (await badge.textContent()) ?? "";
    const url = page.url();
    await page.keyboard.press(band.includes("Reject") ? "r" : "s");
    actions++;
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.keyboard.press("Enter");
    actions++;
    if (i < 49) await page.waitForURL((u) => u.toString() !== url);
    decided++;
  }
  await expect(page.getByText("Every scored candidate in this job has a decision.")).toBeVisible();
  const seconds = Math.round((Date.now() - started) / 1000);
  console.log(`decided ${decided} candidates with ${actions} actions in ${seconds} s`);
  expect(decided).toBe(50);
  expect(actions / decided).toBeLessThanOrEqual(2);
  await expect(page.locator("p", { hasText: "Agreement with the AI:" })).toContainText("100%");
  await page.screenshot({ path: "test-results/job-after-review.png", fullPage: true });
});
