import { expect, test, type Page } from "@playwright/test";

import { signIn } from "./helpers";

// Phase 5B brief: connect the test inbox (Mailpit), email a CV with a job code in the
// subject, and see it read, matched to that job and added as a candidate. The sender's
// name never appears on the Inbox page (blind review holds here too).

const MAILPIT = process.env.MAILPIT_URL ?? "http://localhost:8025";

/** A small text PDF (enough for the extractor). Offsets in the xref are computed. */
function pdf(lines: string[]): string {
  const esc = (s: string) => s.replace(/[\\()]/g, (c) => `\\${c}`);
  const stream = `BT /F1 11 Tf 50 780 Td 14 TL ${lines.map((l) => `(${esc(l)}) '`).join(" ")} ET`;
  const objs = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
    `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`,
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
  ];
  let out = "%PDF-1.4\n";
  const offsets: number[] = [];
  objs.forEach((o, i) => {
    offsets.push(out.length);
    out += `${i + 1} 0 obj\n${o}\nendobj\n`;
  });
  const xref = out.length;
  out += `xref\n0 ${objs.length + 1}\n0000000000 65535 f \n`;
  out += offsets.map((o) => `${String(o).padStart(10, "0")} 00000 n \n`).join("");
  out += `trailer\n<< /Size ${objs.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return Buffer.from(out, "latin1").toString("base64");
}

async function jobCode(page: Page, title: string): Promise<string> {
  await page.goto("/jobs");
  const row = page.getByRole("row").filter({ has: page.getByRole("link", { name: title, exact: true }) }).first();
  const code = (await row.textContent())?.match(/[A-Z]{2}-\d{4}/)?.[0];
  if (!code) throw new Error(`no job code shown for ${title}`);
  return code;
}

test("connect the test inbox, email a CV, see it added to the job", async ({ page, request }) => {
  test.setTimeout(180_000);
  await signIn(page);
  const code = await jobCode(page, "Data Analyst");

  await page.goto("/inbox");
  const connect = page.getByRole("button", { name: "Connect the test inbox" });
  if (await connect.isVisible()) await connect.click();
  await expect(page.getByRole("region", { name: /Mailbox test inbox/ })).toBeVisible();

  const run = Math.random().toString(36).slice(2, 8);
  const person = `Quentin Zarbo${run.replace(/\d/g, "")}`;
  const sent = await request.post(`${MAILPIT}/api/v1/send`, {
    data: {
      From: { Email: `quentin.${run}@example.test`, Name: person },
      To: [{ Email: "careers@northwind.example" }],
      Subject: `Application ${code} from ${person}`,
      Text: "Please find my CV attached.",
      Tags: ["Applications"],
      Attachments: [
        {
          Filename: "cv.pdf",
          Content: pdf([
            person,
            "Data Analyst",
            "Profile",
            "Data analyst with six years of reporting and analysis work in insurance and retail.",
            "Experience",
            "Data Analyst, Molonglo Analytics, March 2019 to present",
            "Wrote SQL queries for weekly loss reporting and built Power BI dashboards.",
            "Presented monthly findings to the operations leadership group.",
            "Education",
            "Bachelor of Science (Statistics)",
            "Skills",
            "SQL, Power BI, Python, Excel",
          ]),
        },
      ],
    },
  });
  expect(sent.ok(), await sent.text()).toBeTruthy();

  // Check now, then wait for the worker to read it.
  await page.getByRole("button", { name: "Check now" }).click();
  const row = page.getByRole("row").filter({ hasText: `Application ${code} from [name]` });
  for (let i = 0; i < 40 && !(await row.isVisible()); i++) {
    await page.waitForTimeout(1500);
    await page.goto("/inbox");
  }
  await expect(row).toBeVisible();
  await expect(row).toContainText(`Job code ${code} in the subject`);
  await expect(row).toContainText("Data Analyst");
  const html = await page.content();
  expect(html).not.toContain(person);
  expect(html).not.toContain(`quentin.${run}@example.test`);

  // The candidate opens in the workbench, under the job from the code.
  await row.getByRole("link").first().click();
  await page.waitForURL(/\/candidates\//);
  await expect(page.getByRole("heading", { level: 2 }).first()).toContainText(/Applicant \d+/);
  await expect(page.getByText(person)).toHaveCount(0);
  await page.screenshot({ path: "test-results/inbox-candidate.png", fullPage: true });
});
