import { expect, type Page } from "@playwright/test";

export const PASSWORD = "Passw0rd!demo";
const USER_MENU = /Owner|Finder|Claimant|Staff|Admin|Reviewer|E2E/;
export const API = process.env.E2E_API_URL ?? "http://localhost:8000";

export async function login(page: Page, email: string, password = PASSWORD) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).not.toHaveURL(/\/login/);                      // wait for the sign-in request to finish before navigating away
  await expect(page.locator("header").getByRole("button", { name: USER_MENU })).toBeVisible();
}

export async function logout(page: Page) {
  await page.locator("header").getByRole("button", { name: USER_MENU }).click();
  await page.getByRole("menuitem", { name: "Sign out" }).click();
  await expect(page.locator("header").getByRole("link", { name: "Sign in" })).toBeVisible();
}

/** Fill and submit the report form; returns the new item's id. */
export async function report(page: Page, kind: "lost" | "found", title: string, description: string) {
  await page.goto(`/report?type=${kind}`);
  await page.getByLabel("Title").fill(title);
  await page.getByLabel("Description").fill(description);
  await page.getByLabel("Category").click();
  await page.getByRole("option", { name: "Other" }).click();
  await page.getByLabel(/Where did you/).click();
  await page.getByRole("option").first().click();
  await page.getByRole("button", { name: new RegExp(`Submit ${kind} report`) }).click();
  await page.waitForURL(/\/items\/\d+/);
  return Number(page.url().match(/items\/(\d+)/)![1]);
}

/** Matching runs in the worker: poll the page until the suggested-matches list shows something. */
export async function waitForMatch(page: Page, itemId: number, withTitle: string) {
  await expect(async () => {
    await page.goto(`/items/${itemId}`);
    await expect(page.locator("li", { hasText: withTitle }).getByRole("button", { name: "Why this match?" })).toBeVisible({ timeout: 2_000 });
  }).toPass({ timeout: 45_000, intervals: [2_000] });
}
