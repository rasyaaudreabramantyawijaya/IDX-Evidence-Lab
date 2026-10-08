import { expect, test } from "@playwright/test";
import { PAGES, VIEWPORTS } from "./snapshot";

// The legacy page must run under the enforced Content-Security-Policy (no bypass): every workspace opens
// without a single violation or script error.
const base = process.env.LEGACY_BASE_URL;
test.skip(!base, "set LEGACY_BASE_URL to run the legacy-UI CSP test");

test("legacy page raises no CSP violations in any workspace", async ({ browser }) => {
  const context = await browser.newContext({ viewport: VIEWPORTS.desktop });
  const page = await context.newPage();
  const problems: string[] = [];
  await page.addInitScript(() => {
    document.addEventListener("securitypolicyviolation", (e) => {
      console.error(`CSP-VIOLATION ${e.violatedDirective} ${e.blockedURI} ${e.sample ?? ""}`);
    });
  });
  page.on("console", (m) => {
    if (/CSP-VIOLATION|Content Security Policy/.test(m.text())) problems.push(m.text().slice(0, 200));
  });
  page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
  const response = await page.goto(base + "/");
  expect(response?.headers()["content-security-policy"]).toContain("script-src 'self'");
  for (const name of PAGES) {
    await page.click(`.nav-item[data-page="${name}"]`);
    await page.waitForTimeout(1500);
  }
  expect(problems).toEqual([]);
  await context.close();
});
