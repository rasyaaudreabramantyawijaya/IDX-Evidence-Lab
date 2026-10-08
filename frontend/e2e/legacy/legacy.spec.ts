import { expect, test } from "@playwright/test";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { PAGES, VIEWPORTS, dump, fingerprint, type PageFingerprint } from "./snapshot";

// LEGACY_BASE_URL: a backend serving the legacy page (python tests/golden_master.py serve prints one).
// UPDATE_LEGACY=1 rewrites legacy-fingerprints.json; LEGACY_DUMP=<dir> writes full DOM/text/styles for diffing.
const base = process.env.LEGACY_BASE_URL;
const FILE = join(import.meta.dirname, "legacy-fingerprints.json");
const update = process.env.UPDATE_LEGACY === "1";
const stored: Record<string, PageFingerprint> = existsSync(FILE) ? JSON.parse(readFileSync(FILE, "utf8")) : {};
const seen: Record<string, PageFingerprint> = {};

test.skip(!base, "set LEGACY_BASE_URL to run the legacy-UI fingerprint tests");
test.describe.configure({ mode: "serial" });

for (const [vpName, viewport] of Object.entries(VIEWPORTS)) {
  test.describe(vpName, () => {
    for (const name of PAGES) {
      test(`${name} renders as recorded`, async ({ browser }) => {
        // bypassCSP lets the test freeze animations; CSP behavior is covered by csp.spec.ts.
        const context = await browser.newContext({ viewport, bypassCSP: true, reducedMotion: "reduce", locale: "id-ID", timezoneId: "Asia/Jakarta" });
        const page = await context.newPage();
        await page.clock.install({ time: new Date("2026-10-08T03:00:00Z") });
        await page.addInitScript(() => {
          try { sessionStorage.clear(); localStorage.clear(); } catch { /* storage unavailable */ }
        });
        const failed: string[] = [];
        page.on("response", (r) => { if (r.status() >= 400) failed.push(`${r.status()} ${new URL(r.url()).pathname}`); });
        await page.goto(base + "/");
        await page.addStyleTag({ content: "*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important}" });
        await page.click(`.nav-item[data-page="${name}"]`);
        await page.clock.runFor(2000);
        const fp = await fingerprint(page, failed);
        const key = `${vpName}/${name}`;
        seen[key] = fp;
        if (process.env.LEGACY_DUMP) {
          const out = join(process.env.LEGACY_DUMP, key);
          mkdirSync(dirname(out), { recursive: true });
          const d = await dump(page);
          writeFileSync(out + ".dom.html", d.dom);
          writeFileSync(out + ".text.txt", d.text);
          writeFileSync(out + ".styles.txt", d.styles);
          await page.screenshot({ path: out + ".png", fullPage: true });
        }
        await context.close();
        if (!update) expect(fp).toEqual(stored[key]);
      });
    }
  });
}

test.afterAll(() => {
  if (update) writeFileSync(FILE, JSON.stringify(Object.fromEntries(Object.entries(seen).sort()), null, 2) + "\n");
});
