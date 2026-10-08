import { expect, test } from "@playwright/test";

test("shell loads and reaches the backend through the dev proxy", async ({ page }) => {
  await page.goto("/app/");
  await expect(page.getByRole("heading", { name: "IDX Evidence Lab" })).toBeVisible();
  await expect(page.getByText(/dokumen lokal/)).toBeVisible();
});
