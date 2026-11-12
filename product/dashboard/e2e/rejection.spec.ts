import { expect, test, type Page } from "@playwright/test";

import { ALERT, openJob, PERSONAL, signIn } from "./helpers";

// Phase 5 brief: reject, read the draft, an edit with protected wording is refused, send
// in one action, and exactly one email arrives in the local Mailpit inbox with the first
// name filled in. The draft page never shows the name or address (blind review).
// Without a model key (CI) the draft is the plain template; with one, the writer's.

const MAILPIT = process.env.MAILPIT_URL ?? "http://localhost:8025";

type MailpitList = {
  messages: { ID: string; MessageID: string; Subject: string; To: { Address: string }[] }[];
};

async function draftReady(page: Page, url: string): Promise<void> {
  for (let i = 0; i < 30; i++) {
    await page.goto(url);
    if (await page.getByRole("heading", { name: "Rejection email draft" }).isVisible()) return;
    await page.waitForTimeout(1000);
  }
  throw new Error("the draft did not appear within 30 seconds");
}

test("reject, edit, send: one email arrives, the name only in the inbox", async ({ page, request }) => {
  test.setTimeout(120_000);
  await signIn(page);
  await openJob(page, "Data Analyst");
  await page.locator("#f-band").selectOption("reject");
  await page.locator("#f-state").selectOption("SCORED");
  await page.getByRole("button", { name: "Filter" }).click();
  await page.locator("[data-row-link]").first().click();
  await expect(page.getByRole("heading", { name: "Evidence" })).toBeVisible();
  const url = page.url();
  const candidateId = url.split("/").pop()!;

  await page.keyboard.press("r");
  await page.keyboard.press("Enter");
  await page.waitForURL((u) => u.toString() !== url);
  await draftReady(page, url);

  const panel = page.getByRole("region", { name: "Rejection email draft" });
  const preview = panel.getByLabel("Email as it will read");
  await expect(preview).toContainText("Hi [first name],");
  await expect(preview).toContainText("delete your application and data");
  const html = await page.content();
  for (const rx of PERSONAL) expect(html).not.toMatch(rx); // blind review holds on the draft

  // An edit that adds family wording is refused and not saved.
  await page.keyboard.press("e");
  const box = page.getByLabel(/Email text/);
  const original = await box.inputValue();
  await box.fill(`${original} The early starts may not suit your young children.`);
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.locator(ALERT)).toContainText("Not saved");
  await expect(page.locator(ALERT)).toContainText("young children");
  await box.fill(`${original} Thank you again for your time.`);
  await page.getByRole("button", { name: "Save" }).click();
  await expect(panel.getByText(/version 2 by you/)).toBeVisible();
  await page.screenshot({ path: "test-results/rejection-draft.png", fullPage: true });

  // Send: the Send button has focus, so Enter is the one action.
  await expect(page.locator("[data-send]")).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Rejection email sent" })).toBeVisible();

  // Exactly one message for this candidate, with the first name filled in.
  const messageId = `rejection.${candidateId}@`;
  let found: MailpitList["messages"] = [];
  for (let i = 0; i < 20 && found.length === 0; i++) {
    const list = (await (await request.get(`${MAILPIT}/api/v1/messages?limit=200`)).json()) as MailpitList;
    found = list.messages.filter((m) => m.MessageID.includes(messageId));
    if (!found.length) await page.waitForTimeout(500);
  }
  expect(found).toHaveLength(1);
  expect(found[0].Subject).toContain("Your application for Data Analyst");
  const msg = (await (await request.get(`${MAILPIT}/api/v1/message/${found[0].ID}`)).json()) as { Text: string };
  expect(msg.Text).toMatch(/^Hi [A-Z][a-z]+,/);
  expect(msg.Text).not.toContain("[first name]");
  expect(msg.Text).toContain("Thank you again for your time.");

  await page.reload();
  await expect(page.getByText(/^Delivered/)).toBeVisible();
  await page.screenshot({ path: "test-results/rejection-sent.png", fullPage: true });

  // A second send of the same rejection is impossible (the page no longer offers it, and
  // the inbox still has one message).
  await expect(page.locator("[data-send]")).toHaveCount(0);
});
