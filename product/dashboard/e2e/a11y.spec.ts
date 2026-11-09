import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { openJob, signIn } from "./helpers";

// Brief bar: no serious or critical accessibility issues on any page (axe).
async function check(page: Page, name: string) {
  const result = await new AxeBuilder({ page }).analyze();
  const bad = result.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(
    bad.map((v) => `${name}: ${v.id} (${v.impact}) ${v.nodes.map((n) => n.target.join(" ")).slice(0, 3)}`),
  ).toEqual([]);
}

test("sign in, jobs, job, candidate and review pages", async ({ page }) => {
  await page.goto("/login");
  await check(page, "sign in");
  await signIn(page);
  await check(page, "jobs");
  await openJob(page, "Registered Nurse, Surgical Ward");
  await check(page, "job");
  await page.locator("[data-row-link]").first().click();
  await expect(page.getByRole("heading", { name: "Evidence" })).toBeVisible();
  await check(page, "candidate");
  await page.keyboard.press("r");
  await check(page, "decision box");
  await page.keyboard.press("Escape");
  await page.goto("/review");
  await check(page, "review queue");
});
