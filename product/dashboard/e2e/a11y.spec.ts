import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { openCandidate, openJob, signIn } from "./helpers";

// Brief bar: no serious or critical accessibility issues on any page (axe).
async function check(page: Page, name: string) {
  const result = await new AxeBuilder({ page }).analyze();
  const bad = result.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(
    bad.map((v) => `${name}: ${v.id} (${v.impact}) ${v.nodes.map((n) => n.target.join(" ")).slice(0, 3)}`),
  ).toEqual([]);
}

test("sign in, candidates, job, candidate, to do, jobs and inbox pages", async ({ page }) => {
  await page.goto("/login");
  await check(page, "sign in");
  await signIn(page);
  await check(page, "jobs");
  await openJob(page, "Registered Nurse, Surgical Ward");
  await check(page, "job");
  await openCandidate(page, page.locator("[data-row-link]").first());
  await check(page, "candidate");
  await page.keyboard.press("r");
  await check(page, "decision box");
  await page.keyboard.press("Escape");
  await page.getByRole("tab", { name: "CV" }).click();
  await check(page, "cv tab");
  await page.goto("/review");
  await check(page, "to do");
  await page.goto("/jobs");
  await check(page, "job board");
  await page.goto("/inbox");
  await check(page, "inbox");
});
