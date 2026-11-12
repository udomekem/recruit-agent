import { expect, type Page } from "@playwright/test";

// Test settings come from the environment (passed in by the e2e script from .env; never
// printed). The token is only used to check it never reaches the browser.
export const PASSWORD = process.env.DASHBOARD_PASSWORD ?? "";
export const TOKEN = process.env.RECRUITER_TOKEN ?? "";

if (!PASSWORD || !TOKEN) throw new Error("DASHBOARD_PASSWORD and RECRUITER_TOKEN are needed");

export async function signIn(page: Page): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Your next great hire." })).toBeVisible();
}

/** The newest job whose title contains `title` (the seed adds new jobs on each run). */
export async function openJob(page: Page, title: string): Promise<void> {
  await page.goto("/jobs");
  await page.getByRole("link", { name: title, exact: true }).first().click();
  await expect(page.getByRole("heading", { level: 1 })).toContainText(title.replace(/ \(.*/, ""));
}

/** Every seeded person's name, name parts, email and phone (synthetic, from the eval set
 * the seed uses): none of these may appear before shortlist. */
function seededPeople(): string[] {
  // e2e runs with the product folder mounted; the dataset sits beside the dashboard
  const { readFileSync } = require("node:fs") as typeof import("node:fs");
  const rows = readFileSync(`${__dirname}/../../evals/datasets/score-v1.jsonl`, "utf8")
    .trim()
    .split("\n")
    .map((l) => JSON.parse(l) as { input: { intake: { name: string; email: string } } });
  const out = new Set<string>();
  for (const r of rows) {
    const { name, email } = r.input.intake;
    out.add(name);
    name.split(" ").forEach((p) => out.add(p));
    out.add(email);
    out.add(email.split("@")[0]);
  }
  return [...out];
}

export const PERSONAL: RegExp[] = [
  ...seededPeople().map((s) => new RegExp(`\\b${s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`)),
  /0491 570 [3-8]\d\d/,
];

/** Click a link to a candidate and wait until that candidate is open. List pages show
 * the first candidate's review already, so a heading alone does not prove the click landed. */
export async function openCandidate(page: Page, link: import("@playwright/test").Locator): Promise<void> {
  const href = (await link.getAttribute("href")) ?? "";
  const path = href.split("?")[0];
  await link.click();
  await page.waitForURL((u) => u.pathname === path);
  await expect(page.getByRole("heading", { name: "Evidence" })).toBeVisible();
}

/** Show only undecided candidates with this recommendation in the open job. */
export async function filterTodo(page: Page, band: string): Promise<void> {
  await page.locator("#f-band").selectOption(band);
  await page.getByRole("button", { name: "Filter" }).click();
  await page.waitForURL(/band=/);
  await page.getByRole("navigation", { name: "Status" }).getByRole("link", { name: /^To decide/ }).click();
  await page.waitForURL(/status=todo/);
}

/** Our own alerts (Next.js adds an empty route announcer with role alert too). */
export const ALERT = '[role="alert"]:not(#__next-route-announcer__)';
