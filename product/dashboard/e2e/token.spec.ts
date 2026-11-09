import { expect, test } from "@playwright/test";

import { TOKEN, openJob, signIn } from "./helpers";

// Brief bar: the API token appears in no page, script or response (0).
test("the API token never reaches the browser", async ({ page }) => {
  const seen: string[] = [];
  page.on("response", async (res) => {
    try {
      const type = res.headers()["content-type"] ?? "";
      if (/text|json|javascript|x-component/.test(type)) seen.push(await res.text());
      seen.push(JSON.stringify(res.headers()));
    } catch {
      // redirects and aborted requests have no body
    }
  });
  page.on("request", (req) => seen.push(req.url(), JSON.stringify(req.headers())));

  await signIn(page);
  await openJob(page, "Data Analyst");
  await page.getByRole("link", { name: "Review next undecided" }).click();
  await expect(page.getByRole("heading", { name: "Evidence" })).toBeVisible();
  seen.push(await page.content());
  await page.goto("/review");
  seen.push(await page.content());
  seen.push(JSON.stringify(await page.context().cookies()));
  await page.waitForLoadState("networkidle");

  expect(seen.length).toBeGreaterThan(10);
  const leaks = seen.filter((s) => s.includes(TOKEN));
  expect(leaks, "token found in browser traffic").toHaveLength(0);
});
