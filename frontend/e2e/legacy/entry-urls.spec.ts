import { expect, test } from "@playwright/test";
import { PAGES, VIEWPORTS } from "./snapshot";

// The app must work from either entry URL: every request it makes to its own server succeeds, and the issuer
// dossier (loaded from a JSON file) opens. Regression for relative ./file.json paths that 404ed when opened at "/".
const base = process.env.LEGACY_BASE_URL;
test.skip(!base, "set LEGACY_BASE_URL to run the legacy-UI entry URL test");

for (const entry of ["/", "/docs/prototypes/idx-evidence-lab-user-journey.html"]) {
  test(`no failed requests and no missing-data panels from ${entry}`, async ({ browser }) => {
    const context = await browser.newContext({ viewport: VIEWPORTS.desktop });
    const page = await context.newPage();
    const failed: string[] = [];
    page.on("response", (r) => {
      if (r.status() >= 400) failed.push(`${r.status()} ${new URL(r.url()).pathname}`);
    });
    await page.goto(base + entry);
    const dataRequired: Record<string, number> = {};
    for (const name of PAGES) {
      await page.click(`.nav-item[data-page="${name}"]`);
      await page.waitForTimeout(1500);
      const text = await page.innerText("#idxel-main");
      dataRequired[name] = text.split("DATA REQUIRED").length - 1;
    }
    expect(failed).toEqual([]);
    // Dashboard and Market overview have no panel that is missing only because of a wrong path.
    expect(dataRequired["dashboard"]).toBe(0);
    expect(dataRequired["market"]).toBe(0);
    await context.close();
  });
}

test("issuer dossier opens from the Screener", async ({ browser }) => {
  const context = await browser.newContext({ viewport: VIEWPORTS.desktop });
  const page = await context.newPage();
  const failed: string[] = [];
  page.on("response", (r) => {
    if (r.status() >= 400) failed.push(`${r.status()} ${new URL(r.url()).pathname}`);
  });
  await page.goto(base + "/");
  await page.click('.nav-item[data-page="screener"]');
  await page.waitForTimeout(2500);
  await page.locator('#idxel-main tr[data-action="open-issuer"]').first().click();
  await page.waitForTimeout(3000);
  const text = await page.innerText("#idxel-main");
  expect(text).toContain("Issuer dossier");
  expect(text).not.toMatch(/HTTP 4\d\d/);
  expect(failed).toEqual([]);
  await context.close();
});
