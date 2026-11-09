import { expect, test } from "@playwright/test";

import { ALERT, signIn } from "./helpers";

test("pages need a session; a wrong password is refused", async ({ page }) => {
  for (const path of ["/", "/review", "/jobs/00000000-0000-0000-0000-000000000000"]) {
    await page.goto(path);
    await expect(page).toHaveURL(/\/login$/);
  }
  await page.getByLabel("Password").fill("not-the-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.locator(ALERT)).toHaveText("That password is not right.");
});

test("sign in, then sign out", async ({ page }) => {
  await signIn(page);
  const cookies = await page.context().cookies();
  const session = cookies.find((c) => c.name === "ra_session");
  expect(session?.httpOnly).toBe(true);
  expect(session?.sameSite).toBe("Lax");
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.goto("/");
  await expect(page).toHaveURL(/\/login$/);
});
