import { expect, test } from "@playwright/test";

import { PERSONAL, openJob, signIn } from "./helpers";

// Brief bar: no name, email or phone in the page before shortlist (0).
test("blind review: no personal details before shortlist", async ({ page }) => {
  const bodies: string[] = [];
  page.on("response", async (res) => {
    try {
      bodies.push(await res.text());
    } catch {
      // no body
    }
  });
  await signIn(page);
  await openJob(page, "Data Analyst (review drill)");
  bodies.push(await page.content());
  const links = page.locator("[data-row-link]");
  for (let i = 0; i < 3; i++) {
    await links.nth(i).click();
    await expect(page.getByRole("heading", { name: "Evidence" })).toBeVisible();
    bodies.push(await page.content());
    await page.goBack();
  }
  for (const pattern of PERSONAL) {
    expect(bodies.filter((b) => pattern.test(b)), `found ${pattern}`).toHaveLength(0);
  }
  await expect(page.getByText("Contact (shown after shortlist")).toHaveCount(0);
});

test("contact details appear after shortlist, and the view is logged", async ({ page }) => {
  await signIn(page);
  await openJob(page, "Data Analyst");
  await page.getByRole("link", { name: "Review next undecided" }).click();
  await expect(page.getByRole("heading", { name: "Evidence" })).toBeVisible();
  const url = page.url();
  await expect(page.getByText("@example.test")).toHaveCount(0);
  await page.keyboard.press("s");
  const reason = page.getByLabel("Reason");
  if ((await reason.inputValue()) === "") await reason.fill("Shortlisted in the end to end test run");
  await page.getByRole("button", { name: "Confirm shortlist" }).click();
  await page.waitForURL((u) => u.toString() !== url);
  await page.goto(url);
  const contact = page.getByRole("region", { name: /Contact/ });
  await expect(contact).toContainText("@example.test");
  await expect(page.getByText("Contact details viewed")).toBeVisible();
});
