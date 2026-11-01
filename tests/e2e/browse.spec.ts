import { expect, test } from "@playwright/test";

test("browse: keyword search, filters and empty state", async ({ page }) => {
  await page.goto("/items");
  await expect(page.getByText(/\d+ items?/).first()).toBeVisible();
  await page.getByLabel("Search").fill("wallet");
  await expect(page).toHaveURL(/q=wallet/);
  await expect(page.getByRole("link", { name: /wallet/i }).first()).toBeVisible();
  await page.getByLabel("Search").fill("qqqzzznothingmatchesthis");
  await expect(page.getByText("Nothing matches those filters")).toBeVisible();
  await page.getByRole("button", { name: "Clear" }).click();
  await expect(page.getByText(/\d+ items?/).first()).toBeVisible();
});

test("item pages show matches only to the reporter and staff", async ({ page }) => {
  await page.goto("/items?item_type=lost");
  await page.getByRole("link").filter({ hasText: /Lost/ }).first().click();
  await expect(page.getByRole("heading", { name: "Suggested matches" })).toHaveCount(0);   // anonymous visitor
});
